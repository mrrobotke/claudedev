"""Issue enhancement pipeline: investigate, classify tier, and update issue on GitHub."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from claudedev.core.credentials import discover_test_credentials
from claudedev.core.state import (
    AgentSession,
    IssueStatus,
    IssueTier,
    Repo,
    SessionStatus,
    SessionType,
    TrackedIssue,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from claudedev.config import Settings
    from claudedev.github.gh_client import GHClient
    from claudedev.integrations.claude_sdk import ClaudeSDKClient

logger = structlog.get_logger(__name__)

ENHANCEMENT_SYSTEM_PROMPT = """You are a senior software engineer triaging GitHub issues.

Rules you must follow at all times:
- Write output that reads as if authored by a human engineer, not an AI assistant.
- Never include phrases like "As an AI", "I've analyzed", "ClaudeDev Enhancement",
  or any other AI self-references in the issue body.
- Use Playwright MCP tools to validate reported behavior when a web UI is present.
  Navigate to the relevant URL and confirm whether the issue reproduces.
- Output TIER: and VALIDATION_FAILED: / CROSS_REPO: metadata lines ONLY at the end of
  your response, never inside the rewritten issue body.
- The rewritten issue body must be clean, professional markdown with no meta-commentary.
"""

ENHANCEMENT_PROMPT_TEMPLATE = """You are a senior software engineer triaging a GitHub issue.

Repository: {repo_full_name}
Domain: {repo_domain}
Issue #{issue_number}: {issue_title}

Issue body:
{issue_body}

Recent comments (newest first):
{issue_comments}

Issue history:
{issue_timeline}

Sibling repositories in the same project:
{sibling_repos}

Your task:
1. Investigate the issue thoroughly by exploring the repository codebase.
   Pay special attention to the most recent comments — they may contain updated
   context, reproduction steps, or corrections from the original reporter.
2. Review the issue timeline to understand the full lifecycle: was this issue
   previously closed and reopened? Was it referenced in PRs? Use this context
   to inform your analysis.
3. Identify the root cause, affected files, and a concrete implementation approach.
4. If the repository has a running web application or service, use Playwright MCP tools to
   navigate to the relevant page or endpoint and verify the reported behavior actually exists.
   - If you confirm the behavior: include a brief note at the bottom of the issue body:
     "Validated: Confirmed via automated testing."
   - If you CANNOT reproduce it: output on its own line (NOT in the body):
     VALIDATION_FAILED: <brief reason>
5. If this issue requires changes in a sibling domain (e.g., a backend API change that
   also needs a frontend UI update), output one or more lines (NOT in the body):
     CROSS_REPO: owner/repo - <title of follow-up issue to create>
6. Rewrite the issue body as if authored by a senior engineer who has done the investigation.
   Write clean, professional markdown. Do NOT include any AI markers, tool names,
   or meta-commentary. Do NOT include a "## ClaudeDev Enhancement" header or any similar
   annotation. The rewritten body REPLACES the original body entirely.

The rewritten issue body must contain:
- A clear, professional problem statement
- Root cause analysis
- Affected files/modules with specific paths
- Implementation approach (numbered steps)
- Acceptance criteria
- Edge cases and risks

As the VERY LAST LINE of your entire output (after the rewritten body), include:
TIER: <1|2|3|4>

Tier guide:
- Tier 1: Small fix, 1-3 files, single domain
- Tier 2: Medium feature, 4-10 files, single domain
- Tier 3: Large feature/refactor, 10+ files, single domain
- Tier 4: Cross-domain (backend + frontend), multiple repos
"""


class IssueEngine:
    """Handles issue investigation, enhancement, and tier classification."""

    def __init__(
        self,
        settings: Settings,
        gh_client: GHClient,
        claude_client: ClaudeSDKClient,
    ) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.claude_client = claude_client

    async def get_or_create_tracked_issue(
        self,
        session: AsyncSession,
        repo_full_name: str,
        issue_number: int,
    ) -> TrackedIssue:
        """Find or create a tracked issue record in the database.

        The returned ``TrackedIssue`` always has its ``repo`` relationship
        eagerly loaded so that callers can access ``tracked.repo`` without
        triggering lazy loading (which raises ``MissingGreenlet`` in async
        SQLAlchemy).
        """
        owner, repo_name = repo_full_name.split("/")
        repo_result = await session.execute(
            select(Repo).where(
                Repo.github_owner == owner,
                Repo.github_repo == repo_name,
            )
        )
        repo = repo_result.scalar_one_or_none()
        if repo is None:
            raise ValueError(f"Repository {repo_full_name} not tracked by any project")

        issue_result = await session.execute(
            select(TrackedIssue)
            .where(
                TrackedIssue.repo_id == repo.id,
                TrackedIssue.github_issue_number == issue_number,
            )
            .options(selectinload(TrackedIssue.repo))
        )
        tracked = issue_result.scalar_one_or_none()
        if tracked is not None:
            return tracked

        new_tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=issue_number,
        )
        # Eagerly set the relationship so callers can access it without
        # triggering async lazy loading.
        new_tracked.repo = repo
        session.add(new_tracked)
        await session.flush()
        return new_tracked

    async def enhance_issue(
        self,
        session: AsyncSession,
        tracked: TrackedIssue,
    ) -> TrackedIssue:
        """Run the enhancement pipeline: investigate with Claude, then update GitHub."""
        log = logger.bind(issue_id=tracked.id, issue_number=tracked.github_issue_number)
        tracked.status = IssueStatus.ENHANCING
        await session.flush()

        agent_session = AgentSession(
            issue_id=tracked.id,
            session_type=SessionType.ENHANCEMENT,
        )
        session.add(agent_session)
        await session.flush()

        try:
            gh_issue, comments, timeline = await self.gh_client.get_issue_full_context(
                self._get_repo_full_name(tracked), tracked.github_issue_number
            )

            sibling_repos = await self._get_sibling_repos(session, tracked)
            repo = tracked.repo

            sibling_repos_text = (
                "\n".join(f"- {r.full_name} ({r.domain})" for r in sibling_repos)
                if sibling_repos
                else "(none)"
            )

            if comments:
                comments_text = "\n\n".join(
                    f"**@{c.user.login}** ({c.created_at.strftime('%Y-%m-%d') if c.created_at else 'unknown'}):\n{c.body[:500]}"
                    for c in comments[:5]
                )
            else:
                comments_text = "(no comments)"

            if timeline:
                timeline_parts = []
                for ev in timeline:
                    actor_name = ev.actor.login if ev.actor else "unknown"
                    date_str = ev.created_at.strftime("%Y-%m-%d") if ev.created_at else ""
                    if ev.event == "closed":
                        if ev.commit_id:
                            timeline_parts.append(
                                f"- Closed by commit {ev.commit_id[:8]} ({actor_name}, {date_str})"
                            )
                        elif ev.source:
                            pr_info = ev.source.get("issue", {})
                            timeline_parts.append(
                                f"- Closed by PR #{pr_info.get('number', '?')} ({actor_name}, {date_str})"
                            )
                        else:
                            timeline_parts.append(f"- Closed ({actor_name}, {date_str})")
                    elif ev.event == "reopened":
                        timeline_parts.append(f"- Reopened ({actor_name}, {date_str})")
                    elif ev.event == "cross-referenced":
                        source_info = ev.source or {}
                        issue_info = source_info.get("issue", {})
                        timeline_parts.append(
                            f"- Referenced in #{issue_info.get('number', '?')}: {issue_info.get('title', '')[:80]}"
                        )
                    elif ev.event == "renamed" and ev.rename:
                        timeline_parts.append(
                            f"- Renamed: '{ev.rename.get('from', '')}' \u2192 '{ev.rename.get('to', '')}'"
                        )
                timeline_text = (
                    "\n".join(timeline_parts) if timeline_parts else "(no notable events)"
                )
            else:
                timeline_text = "(no notable events)"

            prompt = ENHANCEMENT_PROMPT_TEMPLATE.format(
                repo_full_name=self._get_repo_full_name(tracked),
                repo_domain=repo.domain,
                issue_number=tracked.github_issue_number,
                issue_title=gh_issue.title,
                issue_body=gh_issue.body or "(no description)",
                issue_comments=comments_text,
                issue_timeline=timeline_text,
                sibling_repos=sibling_repos_text,
            )

            # Discover test credentials for Playwright authentication
            db_credentials = (
                repo.test_credentials
                if hasattr(repo, "test_credentials") and repo.test_credentials
                else {}
            )
            discovered_credentials = discover_test_credentials(repo.local_path)
            # DB credentials take precedence over freshly discovered
            merged_credentials = {**discovered_credentials, **db_credentials}

            if merged_credentials:
                creds_text = "\n".join(f"  {k}={v}" for k, v in merged_credentials.items())
                prompt += f"""

Test credentials (for Playwright authentication):
{creds_text}

When validating behavior via Playwright:
- If the page requires login, use the test credentials above to authenticate first.
- Navigate to the login page, fill in the credentials, and submit before testing the reported issue.
- Do not include credentials in the rewritten issue body.
"""

            playwright_tools = [
                "mcp__plugin_playwright_playwright__browser_navigate",
                "mcp__plugin_playwright_playwright__browser_snapshot",
                "mcp__plugin_playwright_playwright__browser_click",
                "mcp__plugin_playwright_playwright__browser_type",
                "mcp__plugin_playwright_playwright__browser_take_screenshot",
            ]

            enhancement_text = ""
            async for chunk in self.claude_client.run_query(
                prompt,
                cwd=repo.local_path,
                allowed_tools=playwright_tools,
                max_turns=self.settings.enhancement_max_turns,
                system_prompt=ENHANCEMENT_SYSTEM_PROMPT,
            ):
                enhancement_text += chunk

            # Guard against CLI error output being saved as the issue body
            if enhancement_text.strip().startswith("Error:"):
                raise RuntimeError(
                    f"Claude CLI returned an error: {enhancement_text.strip()[:200]}"
                )

            clean_body, tier, validation_failed, cross_repo_items = self._strip_metadata(
                enhancement_text
            )

            claude_sid = self._find_claude_session_id(repo.local_path, agent_session.started_at)
            if claude_sid:
                agent_session.claude_session_id = claude_sid

            tracked.tier = tier
            tracked.enhanced_at = datetime.now(UTC)
            tracked.issue_metadata = {
                "enhancement": clean_body[:5000],
                "original_title": gh_issue.title,
            }

            agent_session.ended_at = datetime.now(UTC)
            agent_session.summary = f"Enhanced issue #{tracked.github_issue_number}, tier={tier}"

            if validation_failed:
                tracked.status = IssueStatus.ENHANCED
                agent_session.status = SessionStatus.COMPLETED
                await self.gh_client.comment_on_issue(
                    self._get_repo_full_name(tracked),
                    tracked.github_issue_number,
                    body=(
                        "Thanks for the report! We were unable to reproduce the reported "
                        "behavior with our automated testing. Could you provide more details "
                        "or step-by-step reproduction steps? Any additional context (browser "
                        "version, environment, example data) would help."
                    ),
                )
                log.info("issue_validation_failed", tier=tier)
            else:
                tracked.status = IssueStatus.ENHANCED
                agent_session.status = SessionStatus.COMPLETED
                await self.gh_client.update_issue(
                    self._get_repo_full_name(tracked),
                    tracked.github_issue_number,
                    body=clean_body,
                )
                log.info("issue_enhanced", tier=tier)

            for sibling_full_name, follow_up_title in cross_repo_items:
                await self.gh_client.create_issue(
                    sibling_full_name,
                    title=follow_up_title,
                    body=(
                        f"Follow-up from {self._get_repo_full_name(tracked)}"
                        f"#{tracked.github_issue_number}.\n\n"
                        f"The parent issue requires corresponding changes in this repository."
                    ),
                )
                log.info(
                    "cross_repo_issue_created",
                    repo=sibling_full_name,
                    title=follow_up_title,
                )

            return tracked

        except Exception:
            agent_session.status = SessionStatus.FAILED
            agent_session.ended_at = datetime.now(UTC)
            tracked.status = IssueStatus.NEW
            log.exception("enhancement_failed")
            raise

    def classify_tier(self, enhanced_text: str) -> str:
        """Extract tier classification from enhanced issue text."""
        return self._extract_tier(enhanced_text)

    def _extract_tier(self, text: str) -> str:
        """Parse the tier line from enhancement output."""
        for line in reversed(text.strip().splitlines()):
            stripped = line.strip().lower()
            if stripped.startswith("tier:"):
                tier_val = stripped.replace("tier:", "").strip()
                if tier_val in ("1", "2", "3", "4"):
                    return tier_val
        return IssueTier.TIER_2

    def _get_repo_full_name(self, tracked: TrackedIssue) -> str:
        """Get the full repo name (owner/repo) from a tracked issue."""
        repo = tracked.repo
        return f"{repo.github_owner}/{repo.github_repo}"

    def _strip_metadata(
        self,
        text: str,
    ) -> tuple[str, IssueTier, bool, list[tuple[str, str]]]:
        """Strip TIER:, VALIDATION_FAILED:, and CROSS_REPO: lines from enhancement output.

        Returns:
            (clean_body, tier, validation_failed, cross_repo_items)
            where cross_repo_items is a list of (repo_full_name, issue_title) tuples.
        """
        lines = text.strip().splitlines()
        body_lines: list[str] = []
        tier: IssueTier = IssueTier.TIER_2
        validation_failed = False
        cross_repo_items: list[tuple[str, str]] = []

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if lower.startswith("tier:"):
                tier_val = lower.replace("tier:", "").strip()
                if tier_val in ("1", "2", "3", "4"):
                    tier = IssueTier(tier_val)
                continue

            if lower.startswith("validation_failed:"):
                validation_failed = True
                continue

            if lower.startswith("cross_repo:"):
                raw = stripped[len("cross_repo:") :].strip()
                # Expected format: "owner/repo - title of issue"
                if " - " in raw:
                    repo_part, title_part = raw.split(" - ", 1)
                    cross_repo_items.append((repo_part.strip(), title_part.strip()))
                continue

            body_lines.append(line)

        clean_body = "\n".join(body_lines).strip()
        return clean_body, tier, validation_failed, cross_repo_items

    async def _get_sibling_repos(
        self,
        session: AsyncSession,
        tracked: TrackedIssue,
    ) -> list[Repo]:
        """Return other repos in the same project."""
        repo = tracked.repo
        result = await session.execute(
            select(Repo).where(
                Repo.project_id == repo.project_id,
                Repo.id != repo.id,
            )
        )
        return list(result.scalars().all())

    def _find_claude_session_id(self, repo_local_path: str, started_after: datetime) -> str | None:
        """Find the Claude Code session ID by scanning JSONL files in the project dir.

        Claude Code's ``claude -p`` mode creates JSONL session files but does NOT
        update sessions-index.json. We therefore scan .jsonl files sorted by mtime
        (newest first), read the first event's timestamp, and return the session
        whose start is closest to ``started_after`` within a 120-second window.
        """
        try:
            escaped = repo_local_path.replace("/", "-")
            claude_dir = Path.home() / ".claude" / "projects" / escaped
            if not claude_dir.is_dir():
                return None
            jsonl_files = sorted(
                claude_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
            )
            started_aware = (
                started_after if started_after.tzinfo else started_after.replace(tzinfo=UTC)
            )
            best_id: str | None = None
            best_delta: float = float("inf")
            for jf in jsonl_files[:20]:  # Only check 20 most recent files
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
                    best_id = jf.stem  # filename without .jsonl is the session ID
            return best_id
        except Exception:
            logger.exception("find_claude_session_id_failed", repo_path=repo_local_path)
            return None
