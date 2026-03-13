"""Typer CLI application for ClaudeDev.

Provides commands for daemon management, project configuration,
issue tracking, PR management, and system monitoring.
"""

from __future__ import annotations

import asyncio
import os
import signal

import structlog
import typer
from rich.console import Console
from rich.table import Table

from claudedev import __version__
from claudedev.config import LOG_DIR, Settings, ensure_dirs, load_settings

app = typer.Typer(
    name="claudedev",
    help="Autonomous development tool powered by Claude Agent SDK.",
    no_args_is_help=True,
)
console = Console()

# --- Sub-command groups ---

daemon_app = typer.Typer(help="Manage the ClaudeDev daemon.")
project_app = typer.Typer(help="Manage tracked projects.")
issue_app = typer.Typer(help="Manage tracked issues.")
pr_app = typer.Typer(help="Manage pull requests.")
config_app = typer.Typer(help="View and modify configuration.")
cred_app = typer.Typer(help="Manage test credentials for Playwright UI testing.")

app.add_typer(daemon_app, name="daemon")
app.add_typer(project_app, name="project")
app.add_typer(issue_app, name="issue")
app.add_typer(pr_app, name="pr")
app.add_typer(config_app, name="config")
app.add_typer(cred_app, name="credentials")


# --- Daemon commands ---


@daemon_app.command("start")
def daemon_start(
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground"),
) -> None:
    """Start the ClaudeDev daemon."""
    ensure_dirs()
    settings = load_settings()
    pid_file = settings.daemon_pid_file

    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            console.print(f"[yellow]Daemon already running (PID {pid})[/yellow]")
            raise typer.Exit(1)
        except OSError:
            pid_file.unlink(missing_ok=True)

    if foreground:
        _run_daemon(settings)
    else:
        console.print("[green]Starting daemon...[/green]")
        _run_daemon(settings)


def _run_daemon(settings: Settings) -> None:
    """Run the daemon event loop.

    Threading model
    ---------------
    macOS AppKit (NSStatusBar, NSWindow) **must** be created and driven on
    the main thread.  Therefore:

    * The **background thread** owns the asyncio event loop (uvicorn +
      scheduler + tunnel + orchestrator).
    * The **main thread** calls ``menubar.run_on_main_thread()`` which
      blocks until the user quits.

    When the menubar exits the background event loop is stopped gracefully
    and the thread is joined.
    """
    import threading

    from claudedev.core.orchestrator import Orchestrator
    from claudedev.core.scheduler import SchedulerManager
    from claudedev.core.state import close_db, init_db
    from claudedev.github.gh_client import GHClient
    from claudedev.github.webhook_server import create_webhook_app
    from claudedev.integrations.claude_sdk import ClaudeSDKClient
    from claudedev.integrations.tunnel_manager import TunnelManager
    from claudedev.ui.dashboard import router as dashboard_router
    from claudedev.ui.menubar import ClaudeDevMenubar
    from claudedev.utils.logging import setup_logging

    setup_logging(level=settings.log_level)

    # Initialise the menubar *before* the background thread starts so that
    # update_status / update_tunnel_url calls are safe from the async side.
    menubar = ClaudeDevMenubar(dashboard_port=settings.webhook_port)
    menubar.start()

    # Keep a reference to the running loop so the main thread can stop it.
    _loop: asyncio.AbstractEventLoop | None = None

    async def _update_webhook_urls(
        gh_client: GHClient,
        tunnel_url: str,
    ) -> None:
        """Update webhook URLs for all tracked repos.

        Quick tunnels generate a new URL on every restart, so we always
        update every repo that has a webhook_id, not just those flagged
        with ``webhook_needs_url_update``.
        """
        import tomllib

        import tomli_w

        log = structlog.get_logger(__name__)
        webhook_url = f"{tunnel_url}/webhook"

        for project_dir in settings.projects_dir.iterdir():
            config_path = project_dir / "project.toml"
            if not config_path.exists():
                continue

            with open(config_path, "rb") as f:
                config = tomllib.load(f)

            updated = False
            for repo_conf in config.get("repos", []):
                hook_id: int | None = repo_conf.get("webhook_id")
                owner: str = repo_conf.get("github_owner", "")
                repo_name: str = repo_conf.get("github_repo", "")
                secret: str = repo_conf.get("webhook_secret", "")

                if not hook_id or not owner or not repo_name:
                    continue

                full_repo = f"{owner}/{repo_name}"
                try:
                    await gh_client.update_webhook(
                        repo=full_repo,
                        hook_id=hook_id,
                        url=webhook_url,
                        secret=secret or None,
                    )
                    repo_conf["webhook_needs_url_update"] = False
                    updated = True
                    console.print(f"[green]  Updated webhook for {full_repo}[/green]")
                except Exception:
                    console.print(f"[yellow]  Failed to update webhook for {full_repo}[/yellow]")
                    log.exception("webhook_url_update_failed", repo=full_repo)

            if updated:
                with open(config_path, "wb") as f:
                    tomli_w.dump(config, f)

    async def _main() -> None:
        await init_db(settings.db_url)

        # Sync project configs from TOML files into the database on every startup.
        from claudedev.core.state import sync_projects_from_config

        synced = await sync_projects_from_config(settings.projects_dir)
        if synced:
            console.print(f"[green]Synced {synced} project(s) from config[/green]")

        gh_client = GHClient()
        from claudedev.auth import AuthManager

        auth_mgr = AuthManager()
        claude_client = ClaudeSDKClient(
            auth_manager=auth_mgr,
            max_concurrent=settings.max_concurrent_sessions,
        )

        webhook_app = create_webhook_app(settings.webhook_secret_default)
        orchestrator = Orchestrator(
            settings,
            gh_client,
            claude_client,
            ws_manager=getattr(webhook_app.state, "ws_manager", None),
            steering_manager=getattr(webhook_app.state, "steering_manager", None),
            hook_secret=getattr(webhook_app.state, "hook_secret", ""),
        )
        await orchestrator.start_retry_loop()
        scheduler = SchedulerManager(settings, gh_client)

        from datetime import UTC, datetime

        webhook_app.state.orchestrator = orchestrator
        webhook_app.state.gh_client = gh_client
        webhook_app.state.settings = settings
        webhook_app.state.daemon_started_at = datetime.now(UTC)
        webhook_app.include_router(dashboard_router)

        tunnel = TunnelManager(
            local_port=settings.webhook_port,
            hostname=settings.tunnel_hostname,
        )
        webhook_app.state.tunnel_manager = tunnel

        pid_file = settings.daemon_pid_file
        pid_file.write_text(str(os.getpid()))

        try:
            scheduler.start()

            if settings.tunnel_enabled:
                tunnel_info = await tunnel.start()
                if tunnel_info.public_url:
                    menubar.update_tunnel_url(tunnel_info.public_url)
                    console.print(f"[green]Tunnel: {tunnel_info.public_url}[/green]")
                    await _update_webhook_urls(gh_client, tunnel_info.public_url)
                elif tunnel_info.error:
                    console.print(f"[yellow]Tunnel: {tunnel_info.error}[/yellow]")

            # Signal menubar that the daemon is up (thread-safe).
            menubar.update_status("running")

            import uvicorn

            reload_enabled = os.environ.get("CLAUDEDEV_DEV", "").lower() in ("1", "true")
            if reload_enabled:
                config = uvicorn.Config(
                    "claudedev.github.webhook_server:create_webhook_app",
                    factory=True,
                    host=settings.webhook_host,
                    port=settings.webhook_port,
                    log_level="warning",
                    reload=True,
                    reload_dirs=["src/claudedev"],
                )
            else:
                config = uvicorn.Config(
                    webhook_app,
                    host=settings.webhook_host,
                    port=settings.webhook_port,
                    log_level="warning",
                )
            server = uvicorn.Server(config)

            console.print(
                f"[green]ClaudeDev daemon started on "
                f"{settings.webhook_host}:{settings.webhook_port}[/green]"
            )

            await server.serve()

        finally:
            scheduler.stop()
            await tunnel.stop()
            await orchestrator.shutdown()
            await close_db()
            pid_file.unlink(missing_ok=True)

    def _run_event_loop() -> None:
        """Run the async event loop in a background daemon thread.

        Uses ``asyncio.run()`` instead of manual loop management so that
        SQLAlchemy's aiosqlite driver gets the proper greenlet context it
        needs for async DB operations within uvicorn request handlers.
        """
        nonlocal _loop

        async def _wrapper() -> None:
            nonlocal _loop
            _loop = asyncio.get_running_loop()
            await _main()

        asyncio.run(_wrapper())

    # Start the async event loop on a background thread so the main thread
    # remains free for the macOS run loop.
    event_loop_thread = threading.Thread(
        target=_run_event_loop,
        name="claudedev-event-loop",
        daemon=True,
    )
    event_loop_thread.start()

    # Block the main thread on the macOS run loop (AppKit requirement).
    menubar.run_on_main_thread()

    # When the menubar exits, stop the event loop and wait for cleanup.
    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
    event_loop_thread.join(timeout=10)


@daemon_app.command("stop")
def daemon_stop() -> None:
    """Stop the ClaudeDev daemon."""
    settings = load_settings()
    pid_file = settings.daemon_pid_file
    if not pid_file.exists():
        console.print("[yellow]Daemon not running.[/yellow]")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Daemon stopped (PID {pid})[/green]")
    except OSError:
        console.print(f"[yellow]Daemon process {pid} not found. Cleaning up.[/yellow]")
    finally:
        pid_file.unlink(missing_ok=True)


@daemon_app.command("status")
def daemon_status() -> None:
    """Check daemon status."""
    settings = load_settings()
    pid_file = settings.daemon_pid_file
    if not pid_file.exists():
        console.print("[red]Daemon is not running.[/red]")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, 0)
        console.print(f"[green]Daemon is running (PID {pid})[/green]")
    except OSError:
        console.print(f"[yellow]Daemon PID {pid} is stale. Cleaning up.[/yellow]")
        pid_file.unlink(missing_ok=True)


# --- Project commands ---


def _sync_project_to_db(projects_dir: object) -> None:
    """Attempt to sync projects from TOML config into the database.

    Called after onboarding completes while the daemon may or may not be
    running. Initialises the DB engine, syncs, then closes it.  Failures are
    non-fatal: the daemon will sync on its next startup.
    """
    from pathlib import Path

    from claudedev.core.state import close_db, init_db, sync_projects_from_config

    resolved_dir = Path(str(projects_dir))

    async def _run() -> None:
        settings = load_settings()
        await init_db(settings.db_url)
        try:
            await sync_projects_from_config(resolved_dir)
        finally:
            await close_db()

    try:
        asyncio.run(_run())
    except Exception:
        console.print("[yellow]Note: restart the daemon to sync project to database.[/yellow]")


@project_app.command("add")
def project_add() -> None:
    """Add a new project interactively."""
    from claudedev.ui.onboarding import run_onboarding

    result = run_onboarding()
    if result:
        console.print(f"[green]Project '{result['name']}' added successfully.[/green]")
        _sync_project_to_db(load_settings().projects_dir)
    else:
        console.print("[yellow]Project setup cancelled.[/yellow]")


@project_app.command("list")
def project_list() -> None:
    """List all tracked projects."""

    async def _list() -> None:
        from claudedev.core.state import Project, init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from sqlalchemy import select

        from claudedev.core.state import get_session

        async with get_session() as session:
            result = await session.execute(select(Project).order_by(Project.name))
            projects = result.scalars().all()

        if not projects:
            console.print("[yellow]No projects configured.[/yellow]")
            return

        table = Table(title="Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Created")
        for p in projects:
            table.add_row(
                p.name,
                p.type,
                str(p.created_at) if p.created_at else "-",
            )
        console.print(table)

    asyncio.run(_list())


@project_app.command("show")
def project_show(name: str = typer.Argument(..., help="Project name")) -> None:
    """Show details for a specific project."""

    async def _show() -> None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from claudedev.core.state import Project, init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session

        async with get_session() as session:
            result = await session.execute(
                select(Project).where(Project.name == name).options(selectinload(Project.repos))
            )
            project = result.scalar_one_or_none()

        if project is None:
            console.print(f"[red]Project '{name}' not found.[/red]")
            raise typer.Exit(1)

        console.print(f"[bold]{project.name}[/bold] ({project.type})")
        for repo in project.repos:
            console.print(f"  [{repo.domain}] {repo.full_name} @ {repo.local_path}")

    asyncio.run(_show())


@project_app.command("remove")
def project_remove(name: str = typer.Argument(..., help="Project name")) -> None:
    """Remove a project."""
    if not typer.confirm(f"Remove project '{name}'?"):
        return

    async def _remove() -> None:
        from sqlalchemy import select

        from claudedev.core.state import Project, init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session

        async with get_session() as session:
            result = await session.execute(select(Project).where(Project.name == name))
            project = result.scalar_one_or_none()
            if project is None:
                console.print(f"[red]Project '{name}' not found.[/red]")
                return
            await session.delete(project)
            await session.commit()
        console.print(f"[green]Project '{name}' removed.[/green]")

    asyncio.run(_remove())


# --- Issue commands ---


@issue_app.command("list")
def issue_list(
    limit: int = typer.Option(20, help="Max issues to show"),
) -> None:
    """List tracked issues."""

    async def _list() -> None:
        from sqlalchemy import select

        from claudedev.core.state import TrackedIssue, init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session

        async with get_session() as session:
            result = await session.execute(
                select(TrackedIssue).order_by(TrackedIssue.created_at.desc()).limit(limit)
            )
            issues = result.scalars().all()

        if not issues:
            console.print("[yellow]No tracked issues.[/yellow]")
            return

        table = Table(title="Tracked Issues")
        table.add_column("#", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Tier")
        table.add_column("PR")
        for i in issues:
            table.add_row(
                str(i.github_issue_number),
                i.status,
                i.tier or "-",
                str(i.pr_number) if i.pr_number else "-",
            )
        console.print(table)

    asyncio.run(_list())


@issue_app.command("enhance")
def issue_enhance(
    repo: str = typer.Argument(..., help="Repository (owner/name)"),
    number: int = typer.Argument(..., help="Issue number"),
) -> None:
    """Manually trigger issue enhancement."""
    console.print(f"Enhancing {repo}#{number}...")

    async def _enhance() -> None:
        from claudedev.core.state import init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session
        from claudedev.engines.issue_engine import IssueEngine
        from claudedev.github.gh_client import GHClient
        from claudedev.integrations.claude_sdk import ClaudeSDKClient

        gh = GHClient()
        from claudedev.auth import AuthManager

        auth_mgr = AuthManager()
        claude = ClaudeSDKClient(auth_manager=auth_mgr)
        engine = IssueEngine(settings, gh, claude)

        async with get_session() as session:
            tracked = await engine.get_or_create_tracked_issue(session, repo, number)
            await engine.enhance_issue(session, tracked)
            await session.commit()
            console.print(f"[green]Issue #{number} enhanced. Tier: {tracked.tier}[/green]")

    asyncio.run(_enhance())


@issue_app.command("implement")
def issue_implement(
    repo: str = typer.Argument(..., help="Repository (owner/name)"),
    number: int = typer.Argument(..., help="Issue number"),
) -> None:
    """Spawn implementation team for an issue."""
    console.print(f"Implementing {repo}#{number}...")

    async def _implement() -> None:
        from claudedev.core.state import init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session
        from claudedev.engines.issue_engine import IssueEngine
        from claudedev.engines.team_engine import TeamEngine
        from claudedev.github.gh_client import GHClient
        from claudedev.integrations.claude_sdk import ClaudeSDKClient

        gh = GHClient()
        from claudedev.auth import AuthManager

        auth_mgr = AuthManager()
        claude = ClaudeSDKClient(auth_manager=auth_mgr)
        issue_engine = IssueEngine(settings, gh, claude)
        team_engine = TeamEngine(settings, gh, claude)

        async with get_session() as session:
            tracked = await issue_engine.get_or_create_tracked_issue(session, repo, number)
            agent_session = await team_engine.run_implementation(session, tracked)
            await session.commit()
            console.print(
                f"[green]Team spawned for #{number}. "
                f"Session: {agent_session.claude_session_id}[/green]"
            )

    asyncio.run(_implement())


@issue_app.command("pause")
def issue_pause(issue_id: int = typer.Argument(..., help="Tracked issue ID")) -> None:
    """Pause processing for an issue."""
    console.print(f"[yellow]Pausing issue {issue_id} (not yet implemented)[/yellow]")


@issue_app.command("skip")
def issue_skip(issue_id: int = typer.Argument(..., help="Tracked issue ID")) -> None:
    """Skip an issue (mark as done without implementation)."""
    console.print(f"[yellow]Skipping issue {issue_id} (not yet implemented)[/yellow]")


@issue_app.command("sync")
def issue_sync(
    repo: str = typer.Argument(..., help="Repository (owner/repo format)"),
) -> None:
    """Sync issue statuses from GitHub API."""
    import httpx

    settings = load_settings()
    base_url = f"http://localhost:{settings.webhook_port}"

    try:
        repos_resp = httpx.get(f"{base_url}/api/issues", timeout=10)
        repos_resp.raise_for_status()
    except Exception as exc:
        console.print(f"[red]Failed to reach daemon: {exc}[/red]")
        raise typer.Exit(1) from exc

    # Find repo_id by querying all repos via the projects endpoint
    try:
        projects_resp = httpx.get(f"{base_url}/api/projects", timeout=10)
        projects_resp.raise_for_status()
    except Exception as exc:
        console.print(f"[red]Failed to list projects: {exc}[/red]")
        raise typer.Exit(1) from exc

    # Look up the repo_id from the enriched dashboard endpoint
    try:
        dash_resp = httpx.get(f"{base_url}/api/dashboard/enriched", timeout=15)
        dash_resp.raise_for_status()
        dashboard = dash_resp.json()
    except Exception as exc:
        console.print(f"[red]Failed to reach dashboard API: {exc}[/red]")
        raise typer.Exit(1) from exc

    repo_id: int | None = None
    for project in dashboard.get("projects", []):
        for r in project.get("repos", []):
            if r.get("full_name") == repo:
                repo_id = r["id"]
                break
        if repo_id is not None:
            break

    if repo_id is None:
        console.print(f"[red]Repository {repo} not found[/red]")
        raise typer.Exit(1)

    try:
        sync_resp = httpx.post(f"{base_url}/api/repos/{repo_id}/sync-issues", timeout=30)
        sync_resp.raise_for_status()
        data = sync_resp.json()
        console.print(
            f"[green]Synced {data['synced_count']}/{data['total_checked']} issues[/green]"
        )
    except Exception as exc:
        console.print(f"[red]Sync failed: {exc}[/red]")
        raise typer.Exit(1) from exc


# --- PR commands ---


@pr_app.command("list")
def pr_list(limit: int = typer.Option(20, help="Max PRs to show")) -> None:
    """List tracked pull requests."""

    async def _list() -> None:
        from sqlalchemy import select

        from claudedev.core.state import TrackedPR, init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session

        async with get_session() as session:
            result = await session.execute(
                select(TrackedPR).order_by(TrackedPR.created_at.desc()).limit(limit)
            )
            prs = result.scalars().all()

        if not prs:
            console.print("[yellow]No tracked PRs.[/yellow]")
            return

        table = Table(title="Tracked PRs")
        table.add_column("#", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Reviews")
        for pr in prs:
            table.add_row(str(pr.pr_number), pr.status, str(pr.review_iteration))
        console.print(table)

    asyncio.run(_list())


@pr_app.command("review")
def pr_review(
    repo: str = typer.Argument(..., help="Repository (owner/name)"),
    number: int = typer.Argument(..., help="PR number"),
) -> None:
    """Manually trigger PR review."""
    console.print(f"Reviewing {repo}#{number}...")

    async def _review() -> None:
        from claudedev.core.state import init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session
        from claudedev.engines.pr_engine import PREngine
        from claudedev.github.gh_client import GHClient
        from claudedev.integrations.claude_sdk import ClaudeSDKClient

        gh = GHClient()
        from claudedev.auth import AuthManager

        auth_mgr = AuthManager()
        claude = ClaudeSDKClient(auth_manager=auth_mgr)
        engine = PREngine(settings, gh, claude)

        async with get_session() as session:
            tracked = await engine.review_pr(session, repo, number)
            await session.commit()
            findings = tracked.findings or {}
            console.print(
                f"[green]PR #{number} reviewed. Findings: {len(findings.get('items', []))}[/green]"
            )

    asyncio.run(_review())


@pr_app.command("status")
def pr_status(
    repo: str = typer.Argument(..., help="Repository (owner/name)"),
    number: int = typer.Argument(..., help="PR number"),
) -> None:
    """Check PR status."""
    console.print(f"[yellow]PR status for {repo}#{number} (not yet implemented)[/yellow]")


# --- Top-level commands ---


@app.command("dashboard")
def open_dashboard() -> None:
    """Open the web dashboard in the default browser."""
    import webbrowser

    settings = load_settings()
    url = f"http://localhost:{settings.webhook_port}/dashboard"
    console.print(f"Opening {url}")
    webbrowser.open(url)


@app.command("logs")
def show_logs(
    lines: int = typer.Option(50, "-n", help="Number of lines to show"),
    follow: bool = typer.Option(False, "-f", help="Follow log output"),
) -> None:
    """Show recent log output."""
    log_file = LOG_DIR / "claudedev.log"
    if not log_file.exists():
        console.print("[yellow]No logs found.[/yellow]")
        return

    from collections import deque

    with open(log_file) as f:
        tail = deque(f, maxlen=lines)
    for line in tail:
        console.print(line.rstrip())


@app.command("costs")
def show_costs() -> None:
    """Show cost summary for all agent sessions."""

    async def _costs() -> None:
        from sqlalchemy import func, select

        from claudedev.core.state import AgentSession, SessionStatus, init_db

        settings = load_settings()
        await init_db(settings.db_url)

        from claudedev.core.state import get_session

        async with get_session() as session:
            result = await session.execute(
                select(
                    func.sum(AgentSession.cost_usd).label("total"),
                    func.count(AgentSession.id).label("session_count"),
                ).where(AgentSession.status == SessionStatus.COMPLETED)
            )
            row = result.one()
            total = float(row.total or 0)
            count = int(row.session_count or 0)

        console.print(f"Total cost: [bold]${total:.2f}[/bold] across {count} sessions")

    asyncio.run(_costs())


@app.command("tunnel")
def tunnel_status() -> None:
    """Show tunnel status."""
    settings = load_settings()
    if not settings.tunnel_enabled:
        console.print("[yellow]Tunnel is disabled in config.[/yellow]")
        return
    console.print("[yellow]Tunnel status requires running daemon.[/yellow]")


# --- Config commands ---


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    settings = load_settings()
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    for key, value in settings.model_dump().items():
        display_value = str(value)
        if "key" in key.lower() or "secret" in key.lower():
            display_value = "***" if value else "(not set)"
        table.add_row(key, display_value)

    console.print(table)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key"),
    value: str = typer.Argument(..., help="Config value"),
) -> None:
    """Set a configuration value."""
    import tomli_w

    from claudedev.config import CONFIG_FILE

    if CONFIG_FILE.exists():
        import tomllib

        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    else:
        data = {}

    if value.lower() in ("true", "false"):
        data[key] = value.lower() == "true"
    elif value.isdigit():
        data[key] = int(value)
    else:
        try:
            data[key] = float(value)
        except ValueError:
            data[key] = value

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(data, f)

    console.print(f"[green]Set {key} = {value}[/green]")


@cred_app.command("discover")
def cred_discover(
    repo: str = typer.Argument(..., help="Repository (owner/repo format)"),
) -> None:
    """Auto-discover test credentials from .env files."""
    import asyncio

    from sqlalchemy import select

    from claudedev.core.credentials import discover_test_credentials, mask_credential_value
    from claudedev.core.state import Repo, init_db

    owner, repo_name = repo.split("/")

    async def _run() -> None:
        from claudedev.core.state import get_session

        settings = load_settings()
        await init_db(settings.db_url)

        async with get_session() as db:
            result = await db.execute(
                select(Repo).where(Repo.github_owner == owner, Repo.github_repo == repo_name)
            )
            db_repo = result.scalar_one_or_none()
            if db_repo is None:
                console.print(f"[red]Repository {repo} not found in database[/red]")
                raise typer.Exit(1)

            discovered = discover_test_credentials(db_repo.local_path)
            if not discovered:
                console.print("[yellow]No test credentials found in .env files[/yellow]")
                return

            # Merge with existing
            existing = db_repo.test_credentials or {}
            original_keys = set(existing.keys())  # Capture BEFORE merge
            added = 0
            for k, v in discovered.items():
                if k not in existing:
                    existing[k] = v
                    added += 1
            db_repo.test_credentials = existing
            await db.commit()

            table = Table(title=f"Discovered Credentials for {repo}")
            table.add_column("Key", style="cyan")
            table.add_column("Value")
            table.add_column("Status")
            for k, v in discovered.items():
                status = "[green]new[/green]" if k not in original_keys else "[dim]exists[/dim]"
                table.add_row(k, mask_credential_value(k, v), status)
            console.print(table)
            console.print(f"[green]Stored {added} new credentials[/green]")

    asyncio.run(_run())


@cred_app.command("list")
def cred_list(
    repo: str = typer.Argument(..., help="Repository (owner/repo format)"),
) -> None:
    """List test credentials for a repo (passwords masked)."""
    import asyncio

    from sqlalchemy import select

    from claudedev.core.credentials import mask_credential_value
    from claudedev.core.state import Repo, init_db

    owner, repo_name = repo.split("/")

    async def _run() -> None:
        from claudedev.core.state import get_session

        settings = load_settings()
        await init_db(settings.db_url)

        async with get_session() as db:
            result = await db.execute(
                select(Repo).where(Repo.github_owner == owner, Repo.github_repo == repo_name)
            )
            db_repo = result.scalar_one_or_none()
            if db_repo is None:
                console.print(f"[red]Repository {repo} not found in database[/red]")
                raise typer.Exit(1)

            creds = db_repo.test_credentials or {}
            if not creds:
                console.print("[yellow]No test credentials configured[/yellow]")
                return

            table = Table(title=f"Test Credentials for {repo}")
            table.add_column("Key", style="cyan")
            table.add_column("Value")
            for k, v in creds.items():
                table.add_row(k, mask_credential_value(k, v))
            console.print(table)

    asyncio.run(_run())


@cred_app.command("set")
def cred_set(
    repo: str = typer.Argument(..., help="Repository (owner/repo format)"),
    key: str = typer.Argument(..., help="Credential key (e.g. TEST_USER)"),
    value: str = typer.Argument(..., help="Credential value"),
) -> None:
    """Set a test credential for a repo."""
    import asyncio

    from sqlalchemy import select

    from claudedev.core.state import Repo, init_db

    owner, repo_name = repo.split("/")

    async def _run() -> None:
        from claudedev.core.state import get_session

        settings = load_settings()
        await init_db(settings.db_url)

        async with get_session() as db:
            result = await db.execute(
                select(Repo).where(Repo.github_owner == owner, Repo.github_repo == repo_name)
            )
            db_repo = result.scalar_one_or_none()
            if db_repo is None:
                console.print(f"[red]Repository {repo} not found in database[/red]")
                raise typer.Exit(1)

            existing = db_repo.test_credentials or {}
            existing[key] = value
            db_repo.test_credentials = existing
            await db.commit()
            console.print(f"[green]Set {key} for {repo}[/green]")

    asyncio.run(_run())


@cred_app.command("clear")
def cred_clear(
    repo: str = typer.Argument(..., help="Repository (owner/repo format)"),
) -> None:
    """Clear all test credentials for a repo."""
    import asyncio

    from sqlalchemy import select

    from claudedev.core.state import Repo, init_db

    owner, repo_name = repo.split("/")

    async def _run() -> None:
        from claudedev.core.state import get_session

        settings = load_settings()
        await init_db(settings.db_url)

        async with get_session() as db:
            result = await db.execute(
                select(Repo).where(Repo.github_owner == owner, Repo.github_repo == repo_name)
            )
            db_repo = result.scalar_one_or_none()
            if db_repo is None:
                console.print(f"[red]Repository {repo} not found in database[/red]")
                raise typer.Exit(1)

            db_repo.test_credentials = {}
            await db.commit()
            console.print(f"[green]Cleared all credentials for {repo}[/green]")

    asyncio.run(_run())


@app.callback()
def main(
    version: bool | None = typer.Option(None, "--version", "-v", help="Show version"),
) -> None:
    """ClaudeDev - Autonomous development tool."""
    if version:
        console.print(f"claudedev {__version__}")
        raise typer.Exit()
