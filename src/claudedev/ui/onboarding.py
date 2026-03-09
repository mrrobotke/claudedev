"""Rich-based interactive onboarding wizard for new projects.

Guides users through project setup: type selection, repo mapping,
GitHub auth validation, webhook installation, and config generation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TypedDict

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from claudedev.config import PROJECTS_DIR, ensure_dirs
from claudedev.core.state import ProjectType, RepoDomain
from claudedev.github.gh_client import GHClient

logger = structlog.get_logger(__name__)
console = Console()


class RepoConfig(TypedDict, total=False):
    """Configuration for a single repository."""

    domain: str
    local_path: str
    github_owner: str
    github_repo: str
    default_branch: str
    tech_stack: list[str]
    webhook_secret: str
    webhook_id: int
    webhook_needs_url_update: bool
    test_credentials: dict[str, str]


class ProjectConfig(TypedDict):
    """Configuration for a ClaudeDev project."""

    name: str
    type: str
    repos: list[RepoConfig]
    project_dir: str


class OnboardingWizard:
    """Interactive onboarding wizard for setting up a new ClaudeDev project."""

    def __init__(self, gh_client: GHClient) -> None:
        self.gh_client = gh_client

    async def run(self) -> ProjectConfig | None:
        """Run the full onboarding wizard and return the project config."""
        ensure_dirs()

        console.print(
            Panel(
                "[bold blue]ClaudeDev Project Setup[/bold blue]\n"
                "This wizard will help you configure a new project.",
                title="Welcome",
                border_style="blue",
            )
        )

        auth = await self.gh_client.auth_status()
        if not auth.logged_in:
            console.print("[red]GitHub CLI not authenticated.[/red]")
            console.print("Run: [bold]gh auth login[/bold]")
            return None
        console.print(f"[green]Authenticated as: {auth.username}[/green]\n")

        project_name = Prompt.ask("Project name", default="my-project")
        project_dir = PROJECTS_DIR / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        setup_mode = Prompt.ask(
            "Setup mode",
            choices=["auto", "manual"],
            default="auto",
        )

        project_type: str = ProjectType.POLYREPO
        repos: list[RepoConfig] = []

        if setup_mode == "auto":
            discovery_result = await self._auto_discover()
            if discovery_result:
                project_type, repos = discovery_result
            else:
                console.print(
                    "[yellow]Auto-discovery didn't find repos. Falling back to manual.[/yellow]"
                )
                setup_mode = "manual"

        if setup_mode == "manual":
            project_type = Prompt.ask(
                "Project type",
                choices=["polyrepo", "monorepo"],
                default="polyrepo",
            )

            if project_type == ProjectType.MONOREPO:
                monorepo_config = await self._configure_repo("monorepo", RepoDomain.SHARED)
                if monorepo_config:
                    repos.append(monorepo_config)
            else:
                domains = self._select_domains()
                for domain in domains:
                    console.print(f"\n[bold]Configure {domain.value} repository:[/bold]")
                    repo_config = await self._configure_repo(project_name, domain)
                    if repo_config:
                        repos.append(repo_config)

        if not repos:
            console.print("[red]No repositories configured. Aborting.[/red]")
            return None

        # Auto-discover test credentials for each repo
        from claudedev.core.credentials import discover_test_credentials, mask_credential_value

        console.print("\n[bold cyan]Discovering test credentials...[/bold cyan]")
        for repo_config in repos:
            local_path = repo_config.get("local_path", "")
            if not local_path:
                continue
            discovered = discover_test_credentials(local_path)
            if discovered:
                repo_config["test_credentials"] = discovered
                repo_name = repo_config.get("github_repo", local_path)
                masked = {k: mask_credential_value(k, v) for k, v in discovered.items()}
                console.print(
                    f"  [green]\U0001f511 {repo_name}:[/green]"
                    f" Found {len(discovered)} credential(s)"
                )
                for key, val in masked.items():
                    console.print(f"    {key} = {val}")
            else:
                repo_name = repo_config.get("github_repo", local_path)
                console.print(f"  [dim]{repo_name}: No test credentials found[/dim]")

        self._show_summary(project_name, project_type, repos)

        if not Confirm.ask("Proceed with this configuration?"):
            console.print("[yellow]Setup cancelled.[/yellow]")
            return None

        install_webhooks = Confirm.ask("Install GitHub webhooks?", default=True)
        if install_webhooks:
            for repo_config in repos:
                await self._install_webhook(repo_config)

        config: ProjectConfig = {
            "name": project_name,
            "type": project_type,
            "repos": repos,
            "project_dir": str(project_dir),
        }

        self._save_config(project_dir, config)

        console.print(
            Panel(
                f"[green]Project '{project_name}' configured successfully![/green]\n"
                f"Config saved to: {project_dir}",
                title="Setup Complete",
                border_style="green",
            )
        )

        return config

    async def _auto_discover(self) -> tuple[str, list[RepoConfig]] | None:
        """Run auto-discovery and convert results to RepoConfigs."""
        from claudedev.core.discovery import RepoDiscovery

        console.print("\n[bold cyan]Scanning current directory...[/bold cyan]")
        discovery = RepoDiscovery()
        try:
            result = await discovery.discover()
        except Exception as exc:
            console.print(f"[red]Auto-discovery failed: {exc}[/red]")
            return None

        if not result.repos:
            console.print("[yellow]No git repositories found in current directory.[/yellow]")
            return None

        console.print(f"\n[green]Found {len(result.repos)} repository(ies):[/green]")
        console.print(f"  Project type: [bold]{result.project_type}[/bold]")

        table = Table(title="Discovered Repositories")
        table.add_column("#", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Domain", style="green")
        table.add_column("GitHub", style="blue")
        table.add_column("Branch")
        table.add_column("Tech Stack")

        for i, repo in enumerate(result.repos, 1):
            github_str = repo.remote.full_name if repo.remote else "[red]No GitHub remote[/red]"
            table.add_row(
                str(i),
                repo.name,
                repo.domain,
                github_str,
                repo.default_branch,
                ", ".join(repo.tech_stack) or "unknown",
            )

        console.print(table)

        if not Confirm.ask("\nUse these discovered settings?", default=True):
            return None

        repo_configs: list[RepoConfig] = []
        for repo in result.repos:
            if not repo.remote:
                console.print(f"  [yellow]Skipping {repo.name}: no GitHub remote[/yellow]")
                continue

            domain = Prompt.ask(
                f"  Domain for {repo.name}",
                choices=["backend", "frontend", "mobile", "shared"],
                default=repo.domain,
            )

            repo_configs.append(
                RepoConfig(
                    domain=domain,
                    local_path=str(repo.path),
                    github_owner=repo.remote.owner,
                    github_repo=repo.remote.repo,
                    default_branch=repo.default_branch,
                    tech_stack=repo.tech_stack,
                )
            )

        if not repo_configs:
            return None

        return result.project_type, repo_configs

    def _select_domains(self) -> list[RepoDomain]:
        """Ask user which domains their project has."""
        console.print("\n[bold]Select project domains:[/bold]")
        domains: list[RepoDomain] = []
        for domain in RepoDomain:
            if Confirm.ask(f"  Include {domain.value}?", default=domain != RepoDomain.SHARED):
                domains.append(domain)
        return domains

    async def _configure_repo(
        self,
        project_name: str,
        domain: RepoDomain,
    ) -> RepoConfig | None:
        """Configure a single repository."""
        local_path = Prompt.ask("  Local path", default=f"~/projects/{project_name}")
        local_path = str(Path(local_path).expanduser().resolve())

        github_repo = Prompt.ask("  GitHub repo (owner/name)")
        parts = github_repo.split("/")
        if len(parts) != 2:
            console.print("[red]Invalid format. Expected owner/name.[/red]")
            return None

        owner, repo_name = parts
        default_branch = Prompt.ask("  Default branch", default="main")

        tech_stack_str = Prompt.ask(
            "  Tech stack (comma-separated)",
            default="python" if domain == RepoDomain.BACKEND else "typescript",
        )
        tech_stack = [t.strip() for t in tech_stack_str.split(",")]

        return {
            "domain": domain.value,
            "local_path": local_path,
            "github_owner": owner,
            "github_repo": repo_name,
            "default_branch": default_branch,
            "tech_stack": tech_stack,
        }

    async def _install_webhook(self, repo_config: RepoConfig) -> None:
        """Install a GitHub webhook for a repository."""
        repo_full_name = f"{repo_config['github_owner']}/{repo_config['github_repo']}"
        console.print(f"  Installing webhook for {repo_full_name}...")

        try:
            from claudedev.utils.security import generate_webhook_secret

            secret = generate_webhook_secret()
            repo_config["webhook_secret"] = secret

            console.print(
                "  [yellow]Note: Webhook URL will be updated when the daemon starts "
                "with a live tunnel.[/yellow]"
            )
            webhook = await self.gh_client.install_webhook(
                repo=repo_full_name,
                url="https://placeholder.trycloudflare.com/webhook",
                secret=secret,
                events=["issues", "pull_request", "issue_comment"],
            )
            repo_config["webhook_id"] = webhook.id
            repo_config["webhook_needs_url_update"] = True
            console.print(f"  [green]Webhook installed (ID: {webhook.id})[/green]")
            console.print("  [dim]URL will auto-update when daemon starts.[/dim]")
        except Exception as exc:
            console.print(f"  [red]Failed to install webhook: {exc}[/red]")

    def _show_summary(
        self,
        project_name: str,
        project_type: str,
        repos: list[RepoConfig],
    ) -> None:
        """Display a summary table of the configuration."""
        table = Table(title=f"Project: {project_name} ({project_type})")
        table.add_column("Domain", style="cyan")
        table.add_column("Repository", style="green")
        table.add_column("Local Path")
        table.add_column("Branch")
        table.add_column("Stack")

        for repo in repos:
            table.add_row(
                repo["domain"],
                f"{repo['github_owner']}/{repo['github_repo']}",
                repo["local_path"],
                repo["default_branch"],
                ", ".join(repo.get("tech_stack", [])),
            )

        console.print()
        console.print(table)

        cred_count = sum(len(r.get("test_credentials", {})) for r in repos)
        if cred_count:
            console.print(
                f"  [green]\U0001f511 {cred_count} test credential(s) discovered[/green]"
            )

        console.print()

    def _save_config(self, project_dir: Path, config: ProjectConfig) -> None:
        """Save the project configuration to a TOML file."""
        import tomli_w

        config_path = project_dir / "project.toml"
        serializable = {
            "project": {
                "name": config["name"],
                "type": config["type"],
            },
            "repos": config["repos"],
        }
        with open(config_path, "wb") as f:
            tomli_w.dump(serializable, f)

        logger.info("config_saved", path=str(config_path))


def run_onboarding() -> ProjectConfig | None:
    """Entry point for running the onboarding wizard synchronously."""
    gh_client = GHClient()
    wizard = OnboardingWizard(gh_client)
    return asyncio.run(wizard.run())
