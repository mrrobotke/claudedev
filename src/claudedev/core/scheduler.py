"""APScheduler setup for periodic tasks: polling, cleanup, and health checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from claudedev.core.state import AgentSession, IssueStatus, SessionStatus, TrackedIssue, get_session

if TYPE_CHECKING:
    from claudedev.config import Settings
    from claudedev.github.gh_client import GHClient

logger = structlog.get_logger(__name__)


class SchedulerManager:
    """Manages periodic background tasks via APScheduler."""

    def __init__(self, settings: Settings, gh_client: GHClient) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        """Register jobs and start the scheduler."""
        self.scheduler.add_job(
            self._poll_repos,
            "interval",
            seconds=self.settings.poll_interval_seconds,
            id="poll_repos",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._cleanup_stale_sessions,
            "interval",
            minutes=30,
            id="cleanup_stale",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._health_check,
            "interval",
            minutes=5,
            id="health_check",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("scheduler_started")

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    async def _poll_repos(self) -> None:
        """Poll tracked repos for new issues and sync closed status."""
        logger.debug("polling_repos")
        try:
            async with get_session() as session:
                from claudedev.core.state import Repo

                result = await session.execute(select(Repo))
                repos = result.scalars().all()
                for repo in repos:
                    try:
                        # --- Forward sync: discover new open issues ---
                        issues = await self.gh_client.list_issues(
                            repo.full_name, state="open", limit=10
                        )
                        open_numbers = {i.number for i in issues}
                        for issue in issues:
                            existing = await session.execute(
                                select(TrackedIssue).where(
                                    TrackedIssue.repo_id == repo.id,
                                    TrackedIssue.github_issue_number == issue.number,
                                )
                            )
                            if existing.scalar_one_or_none() is None:
                                tracked = TrackedIssue(
                                    repo_id=repo.id,
                                    github_issue_number=issue.number,
                                )
                                session.add(tracked)

                        # --- Reverse sync: close issues that GitHub says are closed ---
                        tracked_open_result = await session.execute(
                            select(TrackedIssue).where(
                                TrackedIssue.repo_id == repo.id,
                                TrackedIssue.status != IssueStatus.CLOSED,
                            )
                        )
                        tracked_open = tracked_open_result.scalars().all()
                        for tracked in tracked_open:
                            if tracked.github_issue_number not in open_numbers:
                                # Not in GitHub's open list — verify it's actually closed
                                try:
                                    gh_issue = await self.gh_client.get_issue(
                                        repo.full_name, tracked.github_issue_number
                                    )
                                    if gh_issue.state == "closed":
                                        tracked.status = IssueStatus.CLOSED
                                        logger.info(
                                            "poll_issue_synced_closed",
                                            repo=repo.full_name,
                                            issue=tracked.github_issue_number,
                                        )
                                except Exception:
                                    logger.warning(
                                        "poll_issue_check_failed",
                                        issue=tracked.github_issue_number,
                                    )

                        await session.commit()
                    except Exception:
                        logger.exception("poll_repo_failed", repo=repo.full_name)
        except Exception:
            logger.exception("poll_repos_failed")

    async def _cleanup_stale_sessions(self) -> None:
        """Mark sessions running for over 2 hours as failed."""
        cutoff = datetime.now(UTC) - timedelta(hours=2)
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(AgentSession).where(
                        AgentSession.status == SessionStatus.RUNNING,
                        AgentSession.started_at < cutoff,
                    )
                )
                stale = result.scalars().all()
                for agent_session in stale:
                    agent_session.status = SessionStatus.FAILED
                    agent_session.summary = "Automatically marked as failed (stale)"
                    logger.warning(
                        "stale_session_cleaned",
                        session_id=agent_session.id,
                        started_at=agent_session.started_at,
                    )
                    # Revert linked issue status when session is marked failed
                    if agent_session.issue_id:
                        issue_result = await session.execute(
                            select(TrackedIssue).where(TrackedIssue.id == agent_session.issue_id)
                        )
                        linked_issue = issue_result.scalar_one_or_none()
                        if linked_issue and linked_issue.status in (
                            IssueStatus.IMPLEMENTING, IssueStatus.ENHANCING
                        ):
                            linked_issue.status = (
                                IssueStatus.ENHANCED if linked_issue.enhanced_at else IssueStatus.NEW
                            )
                            logger.info(
                                "issue_reverted_stale_session",
                                issue_id=linked_issue.id,
                                new_status=linked_issue.status,
                            )
                await session.commit()
        except Exception:
            logger.exception("cleanup_stale_failed")

    async def _health_check(self) -> None:
        """Basic health check: verify DB connectivity and gh auth."""
        try:
            async with get_session() as session:
                await session.execute(select(TrackedIssue).limit(1))
            auth = await self.gh_client.auth_status()
            if not auth.logged_in:
                logger.warning("gh_auth_expired")
            else:
                logger.debug("health_check_ok", gh_user=auth.username)
        except Exception:
            logger.exception("health_check_failed")
