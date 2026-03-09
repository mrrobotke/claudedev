"""PR lifecycle engine: create, review, iterate, and track pull requests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

import structlog
from sqlalchemy import select

from claudedev.core.state import (
    AgentSession,
    PRStatus,
    Repo,
    SessionStatus,
    SessionType,
    TrackedPR,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from claudedev.config import Settings
    from claudedev.github.gh_client import GHClient
    from claudedev.integrations.claude_sdk import ClaudeSDKClient

logger = structlog.get_logger(__name__)


class FindingItem(TypedDict):
    """A single review finding."""

    severity: str
    file: str
    description: str


class ReviewFindings(TypedDict):
    """Structured review findings from PR analysis."""

    items: list[FindingItem]
    critical_count: int
    high_count: int
    medium_count: int


REVIEW_PROMPT_TEMPLATE = """You are a senior code reviewer analyzing a pull request.

Repository: {repo_full_name}
PR #{pr_number}: {pr_title}

PR description:
{pr_body}

Diff:
{diff}

Review this PR thoroughly for:
1. **Code Quality**: Logic errors, bugs, naming, DRY, dead code
2. **Security**: OWASP Top 10, injection, auth flaws, secrets
3. **Tests**: Coverage gaps, missing edge cases, flaky patterns
4. **Performance**: N+1 queries, unnecessary renders, memory leaks
5. **Type Safety**: Type holes, unsafe casts, missing narrowing

For each finding, provide:
- Severity: CRITICAL / HIGH / MEDIUM
- File and line number
- Description of the issue
- Suggested fix

Format as a structured review comment suitable for posting on GitHub.
"""


class PREngine:
    """Manages PR review lifecycle with Claude-powered analysis."""

    def __init__(
        self,
        settings: Settings,
        gh_client: GHClient,
        claude_client: ClaudeSDKClient,
    ) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.claude_client = claude_client

    async def review_pr(
        self,
        session: AsyncSession,
        repo_full_name: str,
        pr_number: int,
    ) -> TrackedPR:
        """Run a full review cycle on a pull request."""
        log = logger.bind(repo=repo_full_name, pr=pr_number)

        tracked = await self._get_or_create_tracked_pr(session, repo_full_name, pr_number)
        tracked.status = PRStatus.REVIEWING
        tracked.review_iteration += 1
        await session.flush()

        agent_session = AgentSession(
            issue_id=tracked.issue_id,
            session_type=SessionType.REVIEW,
        )
        session.add(agent_session)
        await session.flush()

        try:
            gh_pr = await self.gh_client.get_pr(repo_full_name, pr_number)
            diff = await self.gh_client.get_pr_diff(repo_full_name, pr_number)

            prompt = REVIEW_PROMPT_TEMPLATE.format(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                pr_title=gh_pr.title,
                pr_body=gh_pr.body or "(no description)",
                diff=diff[:10000],
            )

            review_text = ""
            async for chunk in self.claude_client.run_query(prompt):
                review_text += chunk

            findings = self._parse_findings(review_text)
            tracked.findings = findings  # type: ignore[assignment]

            has_critical = any(f.get("severity") == "CRITICAL" for f in findings.get("items", []))
            has_high = any(f.get("severity") == "HIGH" for f in findings.get("items", []))

            if has_critical or has_high:
                tracked.status = PRStatus.CHANGES_REQUESTED
                request_changes = True
            else:
                tracked.status = PRStatus.APPROVED
                request_changes = False

            agent_session.status = SessionStatus.COMPLETED
            agent_session.ended_at = datetime.now(UTC)
            agent_session.summary = (
                f"Reviewed PR #{pr_number}, iteration {tracked.review_iteration}, "
                f"findings: {len(findings.get('items', []))}"
            )

            review_body = f"## ClaudeDev Review (Iteration {tracked.review_iteration})\n\n"
            review_body += review_text

            await self.gh_client.review_pr(
                repo_full_name,
                pr_number,
                body=review_body,
                event="REQUEST_CHANGES" if request_changes else "APPROVE",
            )

            log.info(
                "pr_reviewed",
                iteration=tracked.review_iteration,
                findings=len(findings.get("items", [])),
                status=tracked.status,
            )
            return tracked

        except Exception:
            agent_session.status = SessionStatus.FAILED
            agent_session.ended_at = datetime.now(UTC)
            tracked.status = PRStatus.OPEN
            log.exception("pr_review_failed")
            raise

    async def _get_or_create_tracked_pr(
        self,
        session: AsyncSession,
        repo_full_name: str,
        pr_number: int,
    ) -> TrackedPR:
        """Find or create a tracked PR record."""
        owner, repo_name = repo_full_name.split("/")
        repo_result = await session.execute(
            select(Repo).where(
                Repo.github_owner == owner,
                Repo.github_repo == repo_name,
            )
        )
        repo = repo_result.scalar_one_or_none()
        if repo is None:
            raise ValueError(f"Repository {repo_full_name} not tracked")

        pr_result = await session.execute(
            select(TrackedPR).where(
                TrackedPR.repo_id == repo.id,
                TrackedPR.pr_number == pr_number,
            )
        )
        tracked = pr_result.scalar_one_or_none()
        if tracked is not None:
            return tracked

        new_tracked = TrackedPR(
            repo_id=repo.id,
            pr_number=pr_number,
        )
        session.add(new_tracked)
        await session.flush()
        return new_tracked

    def _parse_findings(self, review_text: str) -> ReviewFindings:
        """Parse structured findings from review text."""
        items: list[FindingItem] = []
        current_severity = ""
        current_file = ""
        current_desc_lines: list[str] = []

        for line in review_text.splitlines():
            stripped = line.strip()

            if (
                stripped.startswith("- **CRITICAL")
                or stripped.startswith("- **HIGH")
                or stripped.startswith("- **MEDIUM")
            ):
                if current_desc_lines and current_severity:
                    items.append(
                        {
                            "severity": current_severity,
                            "file": current_file,
                            "description": " ".join(current_desc_lines),
                        }
                    )
                    current_desc_lines = []

                if "CRITICAL" in stripped:
                    current_severity = "CRITICAL"
                elif "HIGH" in stripped:
                    current_severity = "HIGH"
                else:
                    current_severity = "MEDIUM"

                parts = stripped.split("**", 3)
                if len(parts) > 2:
                    remaining = parts[2].strip().lstrip(":").strip()
                    current_desc_lines = [remaining] if remaining else []
                current_file = ""

            elif stripped.startswith("File:") or stripped.startswith("- File:"):
                current_file = stripped.split(":", 1)[1].strip().strip("`")

            elif current_severity and stripped:
                current_desc_lines.append(stripped)

        if current_desc_lines and current_severity:
            items.append(
                {
                    "severity": current_severity,
                    "file": current_file,
                    "description": " ".join(current_desc_lines),
                }
            )

        return {
            "items": items,
            "critical_count": sum(1 for i in items if i.get("severity") == "CRITICAL"),
            "high_count": sum(1 for i in items if i.get("severity") == "HIGH"),
            "medium_count": sum(1 for i in items if i.get("severity") == "MEDIUM"),
        }
