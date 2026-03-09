"""FastAPI webhook server with HMAC-SHA256 signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from claudedev.core.state import (
    AgentSession,
    IssueStatus,
    Project,
    Repo,
    SessionStatus,
    TrackedIssue,
    TrackedPR,
    get_session,
)
from claudedev.github.models import (
    CommentEvent,
    IssueEvent,
    PingEvent,
    PREvent,
    WebhookEvent,
)

if TYPE_CHECKING:
    from claudedev.core.orchestrator import Orchestrator

logger = structlog.get_logger(__name__)


def create_webhook_app(default_secret: str = "") -> FastAPI:
    """Create the FastAPI application for handling GitHub webhooks."""
    app = FastAPI(title="ClaudeDev Webhook Server", version="0.1.0")
    app.state.orchestrator = None
    app.state.default_secret = default_secret

    @app.post("/webhook")
    async def handle_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(None),
        x_github_event: str | None = Header(None),
        x_github_delivery: str | None = Header(None),
    ) -> JSONResponse:
        """Handle incoming GitHub webhook events."""
        body = await request.body()
        log = logger.bind(
            event=x_github_event,
            delivery=x_github_delivery,
        )

        secret = app.state.default_secret
        if secret and x_hub_signature_256:
            if not _verify_signature(body, secret, x_hub_signature_256):
                log.warning("webhook_signature_invalid")
                raise HTTPException(status_code=401, detail="Invalid signature")
        elif secret and not x_hub_signature_256:
            log.warning("webhook_missing_signature")
            raise HTTPException(status_code=401, detail="Missing signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from None

        try:
            event = _parse_event(x_github_event or "", payload)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to parse event") from None
        if event is None:
            log.debug("unhandled_webhook_event", event_type=x_github_event)
            return JSONResponse({"status": "ignored"})

        log.info("webhook_received", event_type=type(event).__name__)

        orchestrator: Orchestrator | None = app.state.orchestrator
        if orchestrator is not None:
            try:
                await orchestrator.dispatch(event)
            except Exception:
                log.exception("webhook_dispatch_failed")
                orchestrator.enqueue_retry(event)
                return JSONResponse(
                    {"status": "accepted_for_retry"},
                    status_code=202,
                )

        return JSONResponse({"status": "accepted"})

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "claudedev"}

    @app.get("/api/projects")
    async def list_projects() -> list[dict[str, str | int | None]]:
        """List all tracked projects."""
        async with get_session() as session:
            result = await session.execute(select(Project).order_by(Project.created_at.desc()))
            projects = result.scalars().all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "type": p.type,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in projects
            ]

    @app.get("/api/issues")
    async def list_issues() -> list[dict[str, str | int | None]]:
        """List tracked issues, filtered by display setting."""
        settings = getattr(app.state, "settings", None)
        filter_mode = settings.issues_display_filter if settings else "open"

        async with get_session() as session:
            query = select(TrackedIssue).order_by(TrackedIssue.created_at.desc()).limit(50)
            if filter_mode == "open":
                query = query.where(TrackedIssue.status != IssueStatus.CLOSED)
            result = await session.execute(query)
            issues = result.scalars().all()
            return [
                {
                    "id": i.id,
                    "repo_id": i.repo_id,
                    "issue_number": i.github_issue_number,
                    "status": i.status,
                    "tier": i.tier,
                    "pr_number": i.pr_number,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                }
                for i in issues
            ]

    @app.get("/api/prs")
    async def list_prs() -> list[dict[str, str | int | None]]:
        """List all tracked pull requests."""
        async with get_session() as session:
            result = await session.execute(
                select(TrackedPR).order_by(TrackedPR.created_at.desc()).limit(50)
            )
            prs = result.scalars().all()
            return [
                {
                    "id": pr.id,
                    "repo_id": pr.repo_id,
                    "pr_number": pr.pr_number,
                    "status": pr.status,
                    "review_iteration": pr.review_iteration,
                    "created_at": pr.created_at.isoformat() if pr.created_at else None,
                }
                for pr in prs
            ]

    @app.get("/api/sessions")
    async def list_sessions() -> list[dict[str, str | int | float | None]]:
        """List agent sessions."""
        async with get_session() as session:
            result = await session.execute(
                select(AgentSession).order_by(AgentSession.started_at.desc()).limit(50)
            )
            sessions = result.scalars().all()
            return [
                {
                    "id": s.id,
                    "issue_id": s.issue_id,
                    "session_type": s.session_type,
                    "status": s.status,
                    "cost_usd": s.cost_usd,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                    "summary": s.summary,
                }
                for s in sessions
            ]

    @app.get("/api/costs")
    async def cost_summary() -> dict[str, float | int]:
        """Get cost summary across all sessions."""
        async with get_session() as session:
            result = await session.execute(
                select(
                    func.sum(AgentSession.cost_usd).label("total_cost"),
                    func.count(AgentSession.id).label("total_sessions"),
                ).where(AgentSession.status == SessionStatus.COMPLETED)
            )
            row = result.one()
            return {
                "total_cost_usd": float(row.total_cost or 0),
                "total_sessions": int(row.total_sessions or 0),
            }

    @app.get("/api/dashboard/enriched")
    async def dashboard_enriched() -> dict[str, Any]:
        """Return all dashboard data in a single enriched response with server-side JOINs."""
        now = datetime.now(UTC)

        # --- Runtime state from app.state (safe defaults for test context) ---
        settings = getattr(app.state, "settings", None)
        daemon_started_at: datetime | None = getattr(app.state, "daemon_started_at", None)
        tunnel_mgr = getattr(app.state, "tunnel_manager", None)

        uptime_seconds = int((now - daemon_started_at).total_seconds()) if daemon_started_at else 0

        tunnel_info = tunnel_mgr.info if tunnel_mgr is not None else None
        tunnel_url = tunnel_info.public_url if tunnel_info else ""
        if tunnel_info and hasattr(tunnel_info, "status"):
            tunnel_status_val = str(tunnel_info.status.value) if tunnel_info.status else "unknown"
        else:
            tunnel_status_val = "unknown"

        max_concurrent = settings.max_concurrent_sessions if settings else 3
        feature_flags = {
            "auto_enhance_issues": settings.auto_enhance_issues if settings else True,
            "auto_implement": settings.auto_implement if settings else False,
            "review_on_pr": settings.review_on_pr if settings else True,
            "issues_display_filter": settings.issues_display_filter if settings else "open",
        }

        # Budget config
        max_per_issue = settings.max_budget_per_issue if settings else 2.0
        max_per_project_daily = settings.max_budget_per_project_daily if settings else 20.0
        max_total_daily = settings.max_budget_total_daily if settings else 50.0

        async with get_session() as db:
            # --- Counts ---
            project_count = await db.scalar(select(func.count(Project.id))) or 0
            repo_count = await db.scalar(select(func.count(Repo.id))) or 0
            total_issues = await db.scalar(select(func.count(TrackedIssue.id))) or 0
            active_issues = (
                await db.scalar(
                    select(func.count(TrackedIssue.id)).where(
                        TrackedIssue.status.not_in(["done", "closed"])
                    )
                )
                or 0
            )
            total_prs = await db.scalar(select(func.count(TrackedPR.id))) or 0
            open_prs = (
                await db.scalar(
                    select(func.count(TrackedPR.id)).where(
                        TrackedPR.status.not_in(["merged", "closed"])
                    )
                )
                or 0
            )
            total_cost = (
                await db.scalar(
                    select(func.sum(AgentSession.cost_usd)).where(
                        AgentSession.status == SessionStatus.COMPLETED
                    )
                )
                or 0.0
            )
            completed_sessions = (
                await db.scalar(
                    select(func.count(AgentSession.id)).where(
                        AgentSession.status == SessionStatus.COMPLETED
                    )
                )
                or 0
            )

            # --- Today's cost ---
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_cost = (
                await db.scalar(
                    select(func.sum(AgentSession.cost_usd)).where(
                        AgentSession.started_at >= today_start
                    )
                )
                or 0.0
            )

            # --- Pipeline stage counts ---
            pipeline_result = await db.execute(
                select(TrackedIssue.status, func.count(TrackedIssue.id)).group_by(
                    TrackedIssue.status
                )
            )
            pipeline_raw: dict[str, int] = {
                str(row[0]): int(row[1]) for row in pipeline_result.all()
            }
            pipeline = {
                "new": pipeline_raw.get("new", 0),
                "enhancing": pipeline_raw.get("enhancing", 0),
                "enhanced": pipeline_raw.get("enhanced", 0),
                "triaged": pipeline_raw.get("triaged", 0),
                "implementing": pipeline_raw.get("implementing", 0),
                "in_review": pipeline_raw.get("in_review", 0),
                "fixing": pipeline_raw.get("fixing", 0),
                "done": pipeline_raw.get("done", 0),
            }

            # --- Projects with repos ---
            projects_result = await db.execute(
                select(Project)
                .options(selectinload(Project.repos))
                .order_by(Project.created_at.desc())
            )
            all_projects = projects_result.scalars().all()

            # Per-project issue and PR counts (keyed by repo_id)
            repo_issue_counts_result = await db.execute(
                select(TrackedIssue.repo_id, func.count(TrackedIssue.id)).group_by(
                    TrackedIssue.repo_id
                )
            )
            repo_issue_counts: dict[int, int] = {
                int(row[0]): int(row[1]) for row in repo_issue_counts_result.all()
            }

            repo_open_pr_counts_result = await db.execute(
                select(TrackedPR.repo_id, func.count(TrackedPR.id))
                .where(TrackedPR.status.not_in(["merged", "closed"]))
                .group_by(TrackedPR.repo_id)
            )
            repo_open_pr_counts: dict[int, int] = {
                int(row[0]): int(row[1]) for row in repo_open_pr_counts_result.all()
            }

            # Per-project today cost (via sessions -> issues -> repos -> projects)
            project_today_cost_result = await db.execute(
                select(Repo.project_id, func.sum(AgentSession.cost_usd))
                .join(TrackedIssue, TrackedIssue.repo_id == Repo.id)
                .join(AgentSession, AgentSession.issue_id == TrackedIssue.id)
                .where(AgentSession.started_at >= today_start)
                .group_by(Repo.project_id)
            )
            project_today_cost: dict[int, float] = {
                pid: float(cost or 0.0) for pid, cost in project_today_cost_result.all()
            }

            # Per-project total cost
            project_total_cost_result = await db.execute(
                select(Repo.project_id, func.sum(AgentSession.cost_usd))
                .join(TrackedIssue, TrackedIssue.repo_id == Repo.id)
                .join(AgentSession, AgentSession.issue_id == TrackedIssue.id)
                .where(AgentSession.status == SessionStatus.COMPLETED)
                .group_by(Repo.project_id)
            )
            project_total_cost: dict[int, float] = {
                pid: float(cost or 0.0) for pid, cost in project_total_cost_result.all()
            }

            projects_payload: list[dict[str, Any]] = []
            per_project_daily: list[dict[str, Any]] = []
            for proj in all_projects:
                proj_issue_count = sum(repo_issue_counts.get(r.id, 0) for r in proj.repos)
                repos_payload = [
                    {
                        "id": r.id,
                        "full_name": r.full_name,
                        "domain": r.domain,
                        "tech_stack": list(r.tech_stack or []),
                        "issue_count": repo_issue_counts.get(r.id, 0),
                        "open_pr_count": repo_open_pr_counts.get(r.id, 0),
                    }
                    for r in proj.repos
                ]
                proj_total = project_total_cost.get(proj.id, 0.0)
                projects_payload.append(
                    {
                        "id": proj.id,
                        "name": proj.name,
                        "type": proj.type,
                        "repos": repos_payload,
                        "total_issues": proj_issue_count,
                        "total_cost_usd": proj_total,
                        "created_at": proj.created_at.isoformat() if proj.created_at else None,
                    }
                )
                proj_today = project_today_cost.get(proj.id, 0.0)
                pct = (proj_today / max_per_project_daily * 100) if max_per_project_daily else 0.0
                per_project_daily.append(
                    {
                        "project_name": proj.name,
                        "spend": proj_today,
                        "limit": max_per_project_daily,
                        "pct": pct,
                    }
                )

            # --- Issues (enriched with repo + project) ---
            issues_filter = feature_flags.get("issues_display_filter", "open")
            _issues_q = (
                select(TrackedIssue)
                .options(selectinload(TrackedIssue.repo).selectinload(Repo.project))
                .order_by(TrackedIssue.created_at.desc())
                .limit(50)
            )
            if issues_filter == "open":
                _issues_q = _issues_q.where(TrackedIssue.status != IssueStatus.CLOSED)
            issues_result = await db.execute(_issues_q)
            all_issues = issues_result.scalars().all()

            issues_payload: list[dict[str, Any]] = []
            for iss in all_issues:
                repo_full_name = iss.repo.full_name if iss.repo else ""
                project_name = iss.repo.project.name if (iss.repo and iss.repo.project) else ""
                github_url = (
                    f"https://github.com/{repo_full_name}/issues/{iss.github_issue_number}"
                    if repo_full_name
                    else ""
                )
                pr_url = (
                    f"https://github.com/{repo_full_name}/pull/{iss.pr_number}"
                    if (repo_full_name and iss.pr_number)
                    else None
                )
                issues_payload.append(
                    {
                        "id": iss.id,
                        "issue_number": iss.github_issue_number,
                        "repo_full_name": repo_full_name,
                        "project_name": project_name,
                        "github_url": github_url,
                        "status": iss.status,
                        "tier": iss.tier,
                        "pr_number": iss.pr_number,
                        "pr_url": pr_url,
                        "created_at": iss.created_at.isoformat() if iss.created_at else None,
                        "enhanced_at": iss.enhanced_at.isoformat() if iss.enhanced_at else None,
                    }
                )

            # --- PRs (enriched with repo and linked issue) ---
            prs_result = await db.execute(
                select(TrackedPR)
                .options(
                    selectinload(TrackedPR.repo),
                    selectinload(TrackedPR.issue),
                )
                .order_by(TrackedPR.created_at.desc())
                .limit(50)
            )
            all_prs = prs_result.scalars().all()

            prs_payload: list[dict[str, Any]] = []
            for pr in all_prs:
                pr_repo_name = pr.repo.full_name if pr.repo else ""
                pr_github_url = (
                    f"https://github.com/{pr_repo_name}/pull/{pr.pr_number}" if pr_repo_name else ""
                )
                linked_issue_number: int | None = pr.issue.github_issue_number if pr.issue else None
                findings = pr.findings or {}
                items = findings.get("items", []) if isinstance(findings, dict) else []
                findings_summary = {"critical": 0, "high": 0, "medium": 0}
                for item in items:
                    if isinstance(item, dict):
                        sev = str(item.get("severity", "")).lower()
                        if sev in findings_summary:
                            findings_summary[sev] += 1
                prs_payload.append(
                    {
                        "id": pr.id,
                        "pr_number": pr.pr_number,
                        "repo_full_name": pr_repo_name,
                        "github_url": pr_github_url,
                        "status": pr.status,
                        "review_iteration": pr.review_iteration,
                        "linked_issue_number": linked_issue_number,
                        "findings_summary": findings_summary,
                        "created_at": pr.created_at.isoformat() if pr.created_at else None,
                    }
                )

            # --- Sessions (enriched with issue + repo) ---
            sessions_result = await db.execute(
                select(AgentSession)
                .options(
                    selectinload(AgentSession.issue).selectinload(TrackedIssue.repo),
                )
                .order_by(AgentSession.started_at.desc())
                .limit(50)
            )
            all_sessions = sessions_result.scalars().all()

            # Count currently running sessions
            active_session_count = (
                await db.scalar(
                    select(func.count(AgentSession.id)).where(
                        AgentSession.status == SessionStatus.RUNNING
                    )
                )
                or 0
            )

            sessions_payload: list[dict[str, Any]] = []
            for s in all_sessions:
                s_issue_number: int | None = s.issue.github_issue_number if s.issue else None
                s_repo_name: str | None = (
                    s.issue.repo.full_name if (s.issue and s.issue.repo) else None
                )
                duration: int | None = None
                if s.started_at and s.ended_at:
                    duration = int((s.ended_at - s.started_at).total_seconds())
                sessions_payload.append(
                    {
                        "id": s.id,
                        "issue_number": s_issue_number,
                        "repo_full_name": s_repo_name,
                        "session_type": s.session_type,
                        "status": s.status,
                        "cost_usd": s.cost_usd,
                        "duration_seconds": duration,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                        "summary": s.summary,
                        "claude_session_id": s.claude_session_id,
                    }
                )

        # --- Activity feed (built in Python from collected events) ---
        activity_events: list[tuple[datetime, str, str, str | None]] = []

        for iss in all_issues:
            repo_name_act = iss.repo.full_name if iss.repo else None
            if iss.created_at:
                activity_events.append(
                    (
                        iss.created_at,
                        "issue_created",
                        f"Issue #{iss.github_issue_number} created",
                        repo_name_act,
                    )
                )
            if iss.enhanced_at:
                activity_events.append(
                    (
                        iss.enhanced_at,
                        "issue_enhanced",
                        f"Issue #{iss.github_issue_number} enhanced",
                        repo_name_act,
                    )
                )
            if iss.implementation_started_at:
                activity_events.append(
                    (
                        iss.implementation_started_at,
                        "implementation_started",
                        f"Implementation started for issue #{iss.github_issue_number}",
                        repo_name_act,
                    )
                )

        for pr in all_prs:
            pr_repo_act = pr.repo.full_name if pr.repo else None
            if pr.created_at:
                activity_events.append(
                    (pr.created_at, "pr_opened", f"PR #{pr.pr_number} opened", pr_repo_act)
                )

        for s in all_sessions:
            s_repo_act: str | None = s.issue.repo.full_name if (s.issue and s.issue.repo) else None
            if s.started_at:
                activity_events.append(
                    (
                        s.started_at,
                        "session_started",
                        f"Agent session ({s.session_type}) started",
                        s_repo_act,
                    )
                )
            if s.ended_at and s.status == SessionStatus.COMPLETED:
                activity_events.append(
                    (
                        s.ended_at,
                        "session_completed",
                        f"Agent session ({s.session_type}) completed",
                        s_repo_act,
                    )
                )

        activity_events.sort(key=lambda e: e[0], reverse=True)
        activity_payload = [
            {
                "timestamp": ts.isoformat(),
                "type": ev_type,
                "message": msg,
                "repo": repo_ref,
            }
            for ts, ev_type, msg, repo_ref in activity_events[:30]
        ]

        # --- Budget summary ---
        today_spend_pct = (today_cost / max_total_daily * 100) if max_total_daily else 0.0

        return {
            "system": {
                "uptime_seconds": uptime_seconds,
                "tunnel_url": tunnel_url,
                "tunnel_status": tunnel_status_val,
                "active_sessions": active_session_count,
                "max_concurrent_sessions": max_concurrent,
                "feature_flags": feature_flags,
            },
            "stats": {
                "projects": project_count,
                "repos": repo_count,
                "total_issues": total_issues,
                "active_issues": active_issues,
                "total_prs": total_prs,
                "open_prs": open_prs,
                "total_cost_usd": float(total_cost),
                "today_cost_usd": float(today_cost),
                "completed_sessions": completed_sessions,
            },
            "budget": {
                "max_per_issue": max_per_issue,
                "max_per_project_daily": max_per_project_daily,
                "max_total_daily": max_total_daily,
                "today_spend": float(today_cost),
                "today_spend_pct": today_spend_pct,
                "per_project_daily": per_project_daily,
            },
            "pipeline": pipeline,
            "projects": projects_payload,
            "issues": issues_payload,
            "prs": prs_payload,
            "sessions": sessions_payload,
            "activity": activity_payload,
            "server_time": now.isoformat(),
        }

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        """Get current configurable settings."""
        settings = getattr(app.state, "settings", None)
        if settings is None:
            return {
                "issues_display_filter": "open",
                "auto_enhance_issues": True,
                "auto_implement": False,
                "review_on_pr": True,
                "enhancement_max_turns": 50,
            }
        return {
            "issues_display_filter": settings.issues_display_filter,
            "auto_enhance_issues": settings.auto_enhance_issues,
            "auto_implement": settings.auto_implement,
            "review_on_pr": settings.review_on_pr,
            "enhancement_max_turns": settings.enhancement_max_turns,
        }

    @app.post("/api/settings")
    async def update_settings(request: Request) -> JSONResponse:
        """Update configurable settings. Persists to config.toml."""
        import tomllib

        import tomli_w

        from claudedev.config import CONFIG_FILE

        body = await request.json()

        valid_filters = {"open", "all"}
        if "issues_display_filter" in body and body["issues_display_filter"] not in valid_filters:
            raise HTTPException(
                status_code=422,
                detail=f"issues_display_filter must be one of: {valid_filters}",
            )

        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "rb") as f:
                data: dict[str, Any] = tomllib.load(f)
        else:
            data = {}

        allowed_keys = {
            "issues_display_filter",
            "auto_enhance_issues",
            "auto_implement",
            "review_on_pr",
            "enhancement_max_turns",
        }
        updated: dict[str, Any] = {}
        for key in allowed_keys:
            if key in body:
                data[key] = body[key]
                updated[key] = body[key]

        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(data, f)

        settings = getattr(app.state, "settings", None)
        if settings:
            for key, value in updated.items():
                if hasattr(settings, key):
                    object.__setattr__(settings, key, value)

        return JSONResponse({"status": "updated", "updated": updated})

    @app.post("/api/issues/{issue_id}/enhance")
    async def trigger_enhance(issue_id: int, request: Request) -> Response:
        """Trigger issue enhancement from the dashboard."""
        orchestrator = getattr(request.app.state, "orchestrator", None)
        if orchestrator is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Orchestrator not available"},
            )

        async with get_session() as session:
            result = await session.execute(
                select(TrackedIssue)
                .where(TrackedIssue.id == issue_id)
                .options(selectinload(TrackedIssue.repo))
            )
            tracked = result.scalar_one_or_none()
            if tracked is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Issue not found"},
                )
            if tracked.status != IssueStatus.NEW:
                return JSONResponse(
                    status_code=409,
                    content={"error": f"Cannot enhance issue with status '{tracked.status}'"},
                )
            if tracked.repo is None:
                return JSONResponse(
                    status_code=500,
                    content={"error": "Issue has no associated repository"},
                )
            repo_full_name = tracked.repo.full_name
            issue_number = tracked.github_issue_number

        task_key = orchestrator.dispatch_enhance(repo_full_name, issue_number)
        if task_key is None:
            return JSONResponse(
                status_code=409,
                content={"error": "Issue is already being processed"},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "dispatched", "action": "enhance", "task_key": task_key},
        )

    @app.post("/api/issues/{issue_id}/implement")
    async def trigger_implement(issue_id: int, request: Request) -> Response:
        """Trigger issue implementation from the dashboard."""
        orchestrator = getattr(request.app.state, "orchestrator", None)
        if orchestrator is None:
            return JSONResponse(
                status_code=503,
                content={"error": "Orchestrator not available"},
            )

        async with get_session() as session:
            result = await session.execute(
                select(TrackedIssue)
                .where(TrackedIssue.id == issue_id)
                .options(selectinload(TrackedIssue.repo))
            )
            tracked = result.scalar_one_or_none()
            if tracked is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Issue not found"},
                )
            allowed = (IssueStatus.NEW, IssueStatus.ENHANCED, IssueStatus.TRIAGED)
            if tracked.status not in allowed:
                return JSONResponse(
                    status_code=409,
                    content={"error": f"Cannot implement issue with status '{tracked.status}'"},
                )
            if tracked.repo is None:
                return JSONResponse(
                    status_code=500,
                    content={"error": "Issue has no associated repository"},
                )
            repo_full_name = tracked.repo.full_name
            issue_number = tracked.github_issue_number

        task_key = orchestrator.dispatch_implement(repo_full_name, issue_number)
        if task_key is None:
            return JSONResponse(
                status_code=409,
                content={"error": "Issue is already being processed"},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "dispatched", "action": "implement", "task_key": task_key},
        )

    @app.post("/api/sessions/{session_id}/terminate")
    async def terminate_session(session_id: int) -> Response:
        """Terminate a running agent session."""
        async with get_session() as db:
            result = await db.execute(select(AgentSession).where(AgentSession.id == session_id))
            agent_session = result.scalar_one_or_none()
            if agent_session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            if agent_session.status != SessionStatus.RUNNING:
                return JSONResponse(
                    status_code=409,
                    content={"error": f"Session is not running (status: {agent_session.status})"},
                )
            agent_session.status = SessionStatus.CANCELLED
            agent_session.ended_at = datetime.now(UTC)

            # Update the linked issue status when session is cancelled
            if agent_session.issue_id:
                issue_result = await db.execute(
                    select(TrackedIssue).where(TrackedIssue.id == agent_session.issue_id)
                )
                linked_issue = issue_result.scalar_one_or_none()
                if linked_issue:
                    if agent_session.session_type == "implementation":
                        # Revert to enhanced if it was enhanced before, otherwise new
                        linked_issue.status = (
                            IssueStatus.ENHANCED if linked_issue.enhanced_at else IssueStatus.NEW
                        )
                        logger.info(
                            "issue_reverted_on_terminate",
                            issue_id=linked_issue.id,
                            new_status=linked_issue.status,
                        )
                    elif agent_session.session_type == "enhancement":
                        linked_issue.status = IssueStatus.NEW
                        logger.info(
                            "issue_reverted_on_terminate",
                            issue_id=linked_issue.id,
                            new_status=linked_issue.status,
                        )

            await db.commit()

        # Cancel in the orchestrator if an active task exists
        orchestrator: Any | None = getattr(app.state, "orchestrator", None)
        if orchestrator is not None:
            active_tasks: dict[str, Any] = getattr(orchestrator, "_active_tasks", {})
            for key, task in list(active_tasks.items()):
                if hasattr(task, "cancel"):
                    # Match by checking if the key relates to this session's issue
                    task.cancel()
                    active_tasks.pop(key, None)
                    break

        return JSONResponse(content={"status": "terminated", "session_id": session_id})

    @app.get("/api/repos/{repo_id}/credentials")
    async def get_repo_credentials(repo_id: int) -> dict[str, Any]:
        """Get test credentials for a repo (passwords masked)."""
        from claudedev.core.credentials import mask_credential_value

        async with get_session() as db:
            result = await db.execute(select(Repo).where(Repo.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise HTTPException(status_code=404, detail="Repository not found")

            creds = repo.test_credentials or {}
            masked = {k: mask_credential_value(k, v) for k, v in creds.items()}
            return {"repo_id": repo_id, "repo": repo.full_name, "credentials": masked}

    @app.post("/api/repos/{repo_id}/credentials")
    async def set_repo_credentials(repo_id: int, request: Request) -> dict[str, Any]:
        """Set or update test credentials for a repo."""
        import re

        from claudedev.core.credentials import mask_credential_value

        env_key_re = re.compile(r"^[A-Z][A-Z0-9_]*$")

        body = await request.json()
        new_creds: dict[str, str] = body.get("credentials", {})
        if not isinstance(new_creds, dict) or not new_creds:
            raise HTTPException(status_code=422, detail="credentials must be a non-empty object")
        for k, v in new_creds.items():
            if not env_key_re.match(k):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid key format: {k}. Must be UPPER_SNAKE_CASE.",
                )
            if not isinstance(v, str) or not v.strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"Value for {k} must be a non-empty string.",
                )

        async with get_session() as db:
            result = await db.execute(select(Repo).where(Repo.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise HTTPException(status_code=404, detail="Repository not found")

            existing = repo.test_credentials or {}
            existing.update(new_creds)
            repo.test_credentials = existing
            await db.commit()

            masked = {k: mask_credential_value(k, v) for k, v in existing.items()}
            return {"status": "updated", "credentials": masked}

    @app.post("/api/repos/{repo_id}/credentials/discover")
    async def discover_repo_credentials(repo_id: int) -> dict[str, Any]:
        """Auto-discover test credentials from repo .env files."""
        from claudedev.core.credentials import discover_test_credentials, mask_credential_value

        async with get_session() as db:
            result = await db.execute(select(Repo).where(Repo.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise HTTPException(status_code=404, detail="Repository not found")

            discovered = discover_test_credentials(repo.local_path)
            if discovered:
                existing = repo.test_credentials or {}
                # Only add newly discovered, don't overwrite manually set
                for k, v in discovered.items():
                    if k not in existing:
                        existing[k] = v
                repo.test_credentials = existing
                await db.commit()

            masked = {k: mask_credential_value(k, v) for k, v in (repo.test_credentials or {}).items()}
            return {
                "status": "discovered",
                "discovered_count": len(discovered),
                "credentials": masked,
            }

    @app.post("/api/repos/{repo_id}/sync-issues")
    async def sync_repo_issues(repo_id: int) -> JSONResponse:
        """Sync issue statuses from GitHub for a repo."""
        async with get_session() as session:
            repo = await session.get(Repo, repo_id)
            if repo is None:
                return JSONResponse(status_code=404, content={"error": "Repo not found"})

            orchestrator: Orchestrator | None = app.state.orchestrator
            if orchestrator is None:
                return JSONResponse(
                    status_code=503, content={"error": "Orchestrator not initialized"}
                )

            result = await session.execute(
                select(TrackedIssue).where(
                    TrackedIssue.repo_id == repo_id,
                    TrackedIssue.status != IssueStatus.CLOSED,
                )
            )
            tracked_issues = result.scalars().all()

            synced = 0
            for tracked in tracked_issues:
                try:
                    gh_issue = await orchestrator.gh_client.get_issue(
                        repo.full_name,
                        tracked.github_issue_number,
                    )
                    if gh_issue.state == "closed":
                        tracked.status = IssueStatus.CLOSED
                        synced += 1
                        logger.info(
                            "issue_synced_closed", issue=tracked.github_issue_number
                        )
                except Exception as exc:
                    logger.warning(
                        "issue_sync_failed",
                        issue=tracked.github_issue_number,
                        error=str(exc),
                    )

            await session.commit()
            return JSONResponse(
                {
                    "status": "synced",
                    "synced_count": synced,
                    "total_checked": len(tracked_issues),
                }
            )

    @app.delete("/api/repos/{repo_id}/credentials")
    async def clear_repo_credentials(repo_id: int) -> dict[str, str]:
        """Clear all test credentials for a repo."""
        async with get_session() as db:
            result = await db.execute(select(Repo).where(Repo.id == repo_id))
            repo = result.scalar_one_or_none()
            if repo is None:
                raise HTTPException(status_code=404, detail="Repository not found")

            repo.test_credentials = {}
            await db.commit()
            return {"status": "cleared"}

    @app.get("/api/sessions/{session_id}/history")
    async def get_session_history(session_id: int) -> dict[str, Any]:
        """Return the full Claude Code conversation history for an agent session."""
        async with get_session() as db:
            result = await db.execute(
                select(AgentSession)
                .where(AgentSession.id == session_id)
                .options(selectinload(AgentSession.issue).selectinload(TrackedIssue.repo))
            )
            agent_session = result.scalar_one_or_none()

        if agent_session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        s_issue = agent_session.issue
        s_repo = s_issue.repo if s_issue else None
        repo_local_path: str | None = s_repo.local_path if s_repo else None
        issue_number: int | None = s_issue.github_issue_number if s_issue else None
        repo_full_name: str | None = s_repo.full_name if s_repo else None

        claude_session_id = agent_session.claude_session_id
        if claude_session_id is None and repo_local_path and agent_session.started_at:
            claude_session_id = _find_claude_session_id_for_path(
                repo_local_path, agent_session.started_at
            )

        session_info: dict[str, Any] = {
            "id": agent_session.id,
            "session_type": agent_session.session_type,
            "status": agent_session.status,
            "cost_usd": agent_session.cost_usd,
            "started_at": agent_session.started_at.isoformat()
            if agent_session.started_at
            else None,
            "ended_at": agent_session.ended_at.isoformat() if agent_session.ended_at else None,
            "summary": agent_session.summary,
            "claude_session_id": claude_session_id,
            "issue_number": issue_number,
            "repo_full_name": repo_full_name,
        }

        if claude_session_id is None or repo_local_path is None:
            return {
                "session_info": session_info,
                "events": [],
                "event_count": 0,
                "message": "No Claude Code session found",
            }

        events, total_count = _parse_jsonl_history(repo_local_path, claude_session_id)

        return {
            "session_info": session_info,
            "events": events,
            "event_count": total_count,
        }

    return app


def _find_claude_session_id_for_path(repo_local_path: str, started_after: datetime) -> str | None:
    """Find the Claude Code session ID by scanning JSONL files in the project dir.

    Claude Code's ``claude -p`` mode creates JSONL files but does NOT update
    sessions-index.json. We scan .jsonl files sorted by mtime (newest first),
    read each file's first event timestamp, and match within a 120-second window.
    """
    import json
    from pathlib import Path

    try:
        escaped = repo_local_path.replace("/", "-")
        claude_dir = Path.home() / ".claude" / "projects" / escaped
        if not claude_dir.is_dir():
            return None
        jsonl_files = sorted(
            claude_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        started_aware = started_after if started_after.tzinfo else started_after.replace(tzinfo=UTC)
        best_id: str | None = None
        best_delta: float = float("inf")
        for jf in jsonl_files[:20]:
            with jf.open("r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            if not first_line:
                continue
            try:
                event = json.loads(first_line)
            except json.JSONDecodeError:
                continue
            ts_str = event.get("timestamp")
            if not ts_str:
                continue
            try:
                event_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=UTC)
            delta = abs((event_dt - started_aware).total_seconds())
            if delta <= 120 and delta < best_delta:
                best_delta = delta
                best_id = jf.stem
        return best_id
    except Exception:
        logger.exception("find_claude_session_id_failed", repo_path=repo_local_path)
        return None


def _parse_jsonl_history(
    repo_local_path: str, claude_session_id: str
) -> tuple[list[dict[str, Any]], int]:
    """Parse a Claude Code JSONL session file into displayable events.

    Returns (events, total_count). Events are capped at 100 (last 100 if more).
    Tool inputs are truncated to 500 chars.
    """
    import json
    from pathlib import Path

    max_events = 100
    max_tool_input_chars = 500
    max_parse = 200

    escaped = repo_local_path.replace("/", "-")
    jsonl_path = Path.home() / ".claude" / "projects" / escaped / f"{claude_session_id}.jsonl"

    parsed_events: list[dict[str, Any]] = []

    try:
        if not jsonl_path.exists():
            return [], 0

        raw_lines: list[str] = []
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    raw_lines.append(line)
                    if len(raw_lines) >= max_parse:
                        break

        for line in raw_lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            timestamp = event.get("timestamp")

            if event_type == "user":
                msg = event.get("message", {})
                content = msg.get("content", "") if isinstance(msg, dict) else ""
                if isinstance(content, list):
                    text_parts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and block.get("type") == "text"
                    ]
                    content = "\n".join(text_parts)
                parsed_events.append(
                    {
                        "type": "user",
                        "content": str(content),
                        "timestamp": timestamp,
                    }
                )

            elif event_type == "assistant":
                msg = event.get("message", {})
                content_blocks = msg.get("content", []) if isinstance(msg, dict) else []
                if not isinstance(content_blocks, list):
                    continue
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")
                    if block_type == "text":
                        text = block.get("text", "")
                        if text:
                            parsed_events.append(
                                {
                                    "type": "assistant_text",
                                    "content": str(text),
                                    "timestamp": timestamp,
                                }
                            )
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        tool_input_str = (
                            json.dumps(tool_input)
                            if isinstance(tool_input, (dict, list))
                            else str(tool_input)
                        )
                        if len(tool_input_str) > max_tool_input_chars:
                            tool_input_str = tool_input_str[:max_tool_input_chars] + "..."
                        parsed_events.append(
                            {
                                "type": "tool_use",
                                "tool_name": str(tool_name),
                                "tool_input": tool_input_str,
                                "timestamp": timestamp,
                            }
                        )
            # Skip "system" and "progress" events

    except Exception:
        logger.exception("parse_jsonl_history_failed", session_id=claude_session_id)
        return [], 0

    total_count = len(parsed_events)
    if total_count > max_events:
        parsed_events = parsed_events[-max_events:]
    return parsed_events, total_count


def _verify_signature(payload: bytes, secret: str, signature_header: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature_header.startswith("sha256="):
        return False
    expected = signature_header[7:]
    computed = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, expected)


def _parse_event(event_type: str, payload: dict[str, object]) -> WebhookEvent | None:
    """Parse a webhook payload into a typed event model."""
    try:
        if event_type == "issues":
            return IssueEvent.model_validate(payload)
        elif event_type == "pull_request":
            return PREvent.model_validate(payload)
        elif event_type in ("issue_comment", "pull_request_review_comment"):
            return CommentEvent.model_validate(payload)
        elif event_type == "ping":
            return PingEvent.model_validate(payload)
        else:
            return None
    except Exception:
        logger.exception("event_parse_failed", event_type=event_type)
        raise
