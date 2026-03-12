"""Main orchestrator that dispatches webhook events to the appropriate engine."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from claudedev.core.state import (
    IssueStatus,
    Repo,
    TrackedIssue,
    get_session,
)
from claudedev.engines.issue_engine import IssueEngine
from claudedev.engines.pr_engine import PREngine
from claudedev.engines.team_engine import TeamEngine
from claudedev.github.models import CommentEvent, IssueEvent, PREvent, WebhookEvent

if TYPE_CHECKING:
    from claudedev.config import Settings
    from claudedev.engines.steering_manager import SteeringManager
    from claudedev.engines.websocket_manager import WebSocketManager
    from claudedev.github.gh_client import GHClient
    from claudedev.integrations.claude_sdk import ClaudeSDKClient

logger = structlog.get_logger(__name__)


@dataclass
class FailedEvent:
    """A webhook event that failed processing and is queued for retry."""

    event: WebhookEvent
    attempts: int = 0
    next_retry: float = field(default_factory=time.monotonic)


class Orchestrator:
    """Central event dispatcher that routes webhook events to engines."""

    def __init__(
        self,
        settings: Settings,
        gh_client: GHClient,
        claude_client: ClaudeSDKClient,
        ws_manager: WebSocketManager | None = None,
        steering_manager: SteeringManager | None = None,
    ) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.claude_client = claude_client
        self.issue_engine = IssueEngine(settings, gh_client, claude_client)
        self.team_engine = TeamEngine(
            settings,
            gh_client,
            claude_client,
            ws_manager=ws_manager,
            steering_manager=steering_manager,
        )
        self.pr_engine = PREngine(settings, gh_client, claude_client)
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_sessions)
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._retry_queue: deque[FailedEvent] = deque(maxlen=100)
        self._retry_task: asyncio.Task[None] | None = None

    async def dispatch(self, event: WebhookEvent) -> None:
        """Route an incoming webhook event to the appropriate handler."""
        log = logger.bind(event_type=type(event).__name__)

        if isinstance(event, IssueEvent):
            await self._handle_issue_event(event, log)
        elif isinstance(event, PREvent):
            await self._handle_pr_event(event, log)
        elif isinstance(event, CommentEvent):
            await self._handle_comment_event(event, log)
        else:
            log.warning("unhandled_event_type")

    async def _handle_issue_event(
        self, event: IssueEvent, log: structlog.stdlib.BoundLogger
    ) -> None:
        """Handle issue opened/edited/labeled events."""
        if event.action in ("closed", "reopened"):
            await self._handle_issue_state_change(event, log)
            return

        if event.action not in ("opened", "labeled"):
            log.debug("skipping_issue_action", action=event.action)
            return

        repo_full_name = event.repository.full_name
        issue_number = event.issue.number
        task_key = f"issue:{repo_full_name}#{issue_number}"

        if task_key in self._active_tasks:
            log.info("issue_already_processing", task_key=task_key)
            return

        log.info("dispatching_issue", repo=repo_full_name, issue=issue_number)

        task = asyncio.create_task(self._process_issue(repo_full_name, issue_number, task_key))
        self._active_tasks[task_key] = task
        task.add_done_callback(lambda _t: self._active_tasks.pop(task_key, None))

    async def _handle_issue_state_change(
        self, event: IssueEvent, log: structlog.stdlib.BoundLogger
    ) -> None:
        """Handle issue closed/reopened events by updating local status.

        Errors propagate to the caller (dispatch -> webhook handler) so that
        GitHub receives a 5xx response and retries delivery.
        """
        repo_full_name = event.repository.full_name
        issue_number = event.issue.number
        async with get_session() as session:
            tracked = await self.issue_engine.get_or_create_tracked_issue(
                session, repo_full_name, issue_number
            )
            if event.action == "closed":
                tracked.status = IssueStatus.CLOSED
                log.info("issue_closed", issue=issue_number)
            elif event.action == "reopened":
                tracked.status = IssueStatus.NEW
                log.info("issue_reopened", issue=issue_number)
            await session.commit()

    async def _process_issue(self, repo_full_name: str, issue_number: int, task_key: str) -> None:
        """Full issue processing pipeline: enhance -> classify -> optionally implement."""
        log = logger.bind(task_key=task_key)
        async with self._semaphore:
            try:
                async with get_session() as session:
                    tracked = await self.issue_engine.get_or_create_tracked_issue(
                        session, repo_full_name, issue_number
                    )
                    if tracked.status != IssueStatus.NEW:
                        log.info("issue_not_new", status=tracked.status)
                        return

                    if self.settings.auto_enhance_issues:
                        log.info("enhancing_issue")
                        await self.issue_engine.enhance_issue(session, tracked)

                    if self.settings.auto_implement and tracked.tier is not None:
                        log.info("auto_implementing", tier=tracked.tier)
                        await self.team_engine.run_implementation(session, tracked)

                    await session.commit()
            except Exception as exc:
                log.error(
                    "issue_processing_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

    async def _handle_pr_event(self, event: PREvent, log: structlog.stdlib.BoundLogger) -> None:
        """Handle PR opened/synchronize/review_requested events."""
        if event.action not in ("opened", "synchronize", "review_requested"):
            log.debug("skipping_pr_action", action=event.action)
            return

        if not self.settings.review_on_pr:
            return

        repo_full_name = event.repository.full_name
        pr_number = event.pull_request.number
        task_key = f"pr:{repo_full_name}#{pr_number}"

        if task_key in self._active_tasks:
            log.info("pr_already_processing", task_key=task_key)
            return

        log.info("dispatching_pr_review", repo=repo_full_name, pr=pr_number)

        task = asyncio.create_task(self._process_pr(repo_full_name, pr_number, task_key))
        self._active_tasks[task_key] = task
        task.add_done_callback(lambda _t: self._active_tasks.pop(task_key, None))

    async def _process_pr(self, repo_full_name: str, pr_number: int, task_key: str) -> None:
        """Review a PR using the review engine."""
        log = logger.bind(task_key=task_key)
        async with self._semaphore:
            try:
                async with get_session() as session:
                    await self.pr_engine.review_pr(session, repo_full_name, pr_number)
                    await session.commit()
            except Exception as exc:
                log.error(
                    "pr_review_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

    async def _handle_comment_event(
        self, event: CommentEvent, log: structlog.stdlib.BoundLogger
    ) -> None:
        """Handle issue/PR comment events (for slash commands like /implement)."""
        body = event.comment.body.strip().lower()
        if not body.startswith("/"):
            return

        command = body.split()[0]
        repo_full_name = event.repository.full_name

        if command == "/implement" and event.issue is not None:
            log.info("implement_command", issue=event.issue.number)
            task_key = f"implement:{repo_full_name}#{event.issue.number}"
            if task_key not in self._active_tasks:
                task = asyncio.create_task(
                    self._implement_issue(repo_full_name, event.issue.number, task_key)
                )
                self._active_tasks[task_key] = task
                task.add_done_callback(lambda _t: self._active_tasks.pop(task_key, None))

        elif command == "/review" and event.issue is not None:
            pr_number = event.issue.number
            log.info("review_command", pr=pr_number)
            task_key = f"pr:{repo_full_name}#{pr_number}"
            if task_key not in self._active_tasks:
                task = asyncio.create_task(self._process_pr(repo_full_name, pr_number, task_key))
                self._active_tasks[task_key] = task
                task.add_done_callback(lambda _t: self._active_tasks.pop(task_key, None))

    async def _implement_issue(self, repo_full_name: str, issue_number: int, task_key: str) -> None:
        """Spawn an implementation team for an issue."""
        log = logger.bind(task_key=task_key)
        async with self._semaphore:
            try:
                async with get_session() as session:
                    tracked = await self.issue_engine.get_or_create_tracked_issue(
                        session, repo_full_name, issue_number
                    )
                    if tracked.status == IssueStatus.NEW:
                        await self.issue_engine.enhance_issue(session, tracked)
                    elif tracked.status not in (IssueStatus.ENHANCED, IssueStatus.TRIAGED):
                        log.warning("unexpected_status_for_implement", status=tracked.status)
                        return
                    await self.team_engine.run_implementation(session, tracked)
                    await session.commit()
            except Exception as exc:
                log.error(
                    "implementation_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                try:
                    owner, _, repo_name = repo_full_name.partition("/")
                    async with get_session() as err_session:
                        err_result = await err_session.execute(
                            select(TrackedIssue)
                            .join(Repo)
                            .where(
                                Repo.github_owner == owner,
                                Repo.github_repo == repo_name,
                                TrackedIssue.github_issue_number == issue_number,
                            )
                        )
                        failed_issue = err_result.scalars().first()
                        if failed_issue:
                            failed_issue.status = IssueStatus.FAILED
                            await err_session.commit()
                except Exception:
                    log.exception("failed_to_update_status_on_error")

    def dispatch_enhance(self, repo_full_name: str, issue_number: int) -> str | None:
        """Dispatch issue enhancement as a background task.

        Returns the task key on success, or None if the issue is already being processed.
        """
        task_key = f"issue:{repo_full_name}#{issue_number}"
        if task_key in self._active_tasks:
            return None
        task = asyncio.create_task(self._process_issue(repo_full_name, issue_number, task_key))
        self._active_tasks[task_key] = task
        task.add_done_callback(lambda _t: self._active_tasks.pop(task_key, None))
        return task_key

    def dispatch_implement(self, repo_full_name: str, issue_number: int) -> str | None:
        """Dispatch issue implementation as a background task.

        Returns the task key on success, or None if already being processed.
        """
        task_key = f"implement:{repo_full_name}#{issue_number}"
        if task_key in self._active_tasks:
            return None
        task = asyncio.create_task(self._implement_issue(repo_full_name, issue_number, task_key))
        self._active_tasks[task_key] = task
        task.add_done_callback(lambda _t: self._active_tasks.pop(task_key, None))
        return task_key

    async def start_retry_loop(self) -> None:
        """Start the background retry processor."""
        self._retry_task = asyncio.create_task(self._process_retries())

    async def _process_retries(self) -> None:
        """Process failed events with exponential backoff (30s, 60s, 120s)."""
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            retryable: list[FailedEvent] = []
            remaining: deque[FailedEvent] = deque()
            while self._retry_queue:
                fe = self._retry_queue.popleft()
                if fe.next_retry <= now:
                    retryable.append(fe)
                else:
                    remaining.append(fe)
            self._retry_queue = remaining
            for fe in retryable:
                try:
                    await self.dispatch(fe.event)
                    logger.info("retry_succeeded", attempt=fe.attempts + 1)
                except Exception as exc:
                    fe.attempts += 1
                    if fe.attempts < 3:
                        delay = 30 * (2**fe.attempts)  # 60s, 120s
                        fe.next_retry = time.monotonic() + delay
                        self._retry_queue.append(fe)
                        logger.warning(
                            "retry_scheduled",
                            attempt=fe.attempts,
                            next_delay=delay,
                            error=str(exc),
                        )
                    else:
                        logger.error(
                            "retry_exhausted",
                            attempts=fe.attempts,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )

    def enqueue_retry(self, event: WebhookEvent) -> None:
        """Add a failed event to the retry queue with initial 30s delay."""
        fe = FailedEvent(event=event, next_retry=time.monotonic() + 30)
        self._retry_queue.append(fe)
        logger.info("event_queued_for_retry", queue_size=len(self._retry_queue))

    async def shutdown(self) -> None:
        """Cancel all active tasks and wait for them to finish."""
        logger.info("orchestrator_shutting_down", active_tasks=len(self._active_tasks))
        if self._retry_task is not None:
            self._retry_task.cancel()
            self._retry_task = None
        for task in self._active_tasks.values():
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
        self._active_tasks.clear()
