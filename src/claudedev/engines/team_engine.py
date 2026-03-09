"""Team spawner: classifies tier and creates Claude Agent SDK sessions with subagents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from claudedev.core.state import (
    AgentSession,
    IssueStatus,
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

TIER_1_AGENTS = [
    {"name": "implementer", "role": "Primary implementer"},
    {"name": "sr-quality-reviewer", "role": "Code quality reviewer"},
    {"name": "sr-security-reviewer", "role": "Security auditor"},
    {"name": "sr-test-reviewer", "role": "Test coverage reviewer"},
]

TIER_2_AGENTS = [
    {"name": "architect", "role": "Solution architect"},
    {"name": "implementer-1", "role": "Primary implementer"},
    {"name": "implementer-2", "role": "Secondary implementer"},
    {"name": "sr-quality-reviewer", "role": "Code quality reviewer"},
    {"name": "sr-security-reviewer", "role": "Security auditor"},
    {"name": "sr-test-reviewer", "role": "Test coverage reviewer"},
    {"name": "sr-performance-reviewer", "role": "Performance analyst"},
    {"name": "sr-type-reviewer", "role": "Type design reviewer"},
]

TIER_3_AGENTS = [
    {"name": "architect", "role": "Solution architect"},
    {"name": "implementer-1", "role": "Primary implementer"},
    {"name": "implementer-2", "role": "Secondary implementer"},
    {"name": "implementer-3", "role": "Tertiary implementer"},
    {"name": "sr-quality-reviewer", "role": "Code quality reviewer"},
    {"name": "sr-security-reviewer", "role": "Security auditor"},
    {"name": "sr-test-reviewer", "role": "Test coverage reviewer"},
    {"name": "sr-performance-reviewer", "role": "Performance analyst"},
    {"name": "sr-type-reviewer", "role": "Type design reviewer"},
    {"name": "sr-atomic-reviewer", "role": "Atomic design reviewer"},
    {"name": "sr-silent-failure-hunter", "role": "Error handling reviewer"},
    {"name": "sr-simplicity-reviewer", "role": "Simplicity reviewer"},
]

TIER_4_AGENTS = [
    {"name": "sr-backend-lead", "role": "Backend domain lead"},
    {"name": "sr-frontend-lead", "role": "Frontend domain lead"},
    {"name": "sr-integration-reviewer", "role": "Cross-domain integration reviewer"},
]

TIER_AGENT_MAP: dict[str, list[dict[str, str]]] = {
    "1": TIER_1_AGENTS,
    "2": TIER_2_AGENTS,
    "3": TIER_3_AGENTS,
    "4": TIER_4_AGENTS,
}

IMPLEMENTATION_PROMPT_TEMPLATE = """You are working on GitHub issue #{issue_number} in {repo_full_name}.

Issue title: {issue_title}
Issue tier: {tier}

Enhancement analysis:
{enhancement}

Latest issue comments:
{issue_comments}

Issue timeline:
{issue_timeline}

Your team consists of:
{agent_list}

Instructions:
1. If there is an architect, wait for the architecture plan before implementing.
2. Implement the changes following project conventions.
3. Create a feature branch: claudedev/issue-{issue_number}
4. Make focused, well-tested commits.
5. When implementation is complete, create a PR and request review.
6. Address reviewer findings iteratively until all CRITICAL/HIGH issues are resolved.
7. Run quality gates (lint, typecheck, tests) before marking as done.
8. Review the latest comments and timeline — the most recent comment may contain
   updated requirements or context that supersedes the original issue body.

Working directory: {working_dir}
"""


class TeamEngine:
    """Spawns Claude Agent SDK teams based on issue tier classification."""

    def __init__(
        self,
        settings: Settings,
        gh_client: GHClient,
        claude_client: ClaudeSDKClient,
    ) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.claude_client = claude_client

    async def spawn_team(
        self,
        session: AsyncSession,
        tracked: TrackedIssue,
    ) -> AgentSession:
        """Spawn an implementation team for the given issue.

        Creates a Claude Agent SDK session with the appropriate number of
        subagents based on the issue's tier classification.
        """
        tier = tracked.tier or "2"
        log = logger.bind(
            issue_id=tracked.id,
            issue_number=tracked.github_issue_number,
            tier=tier,
        )

        agents = TIER_AGENT_MAP.get(tier, TIER_2_AGENTS)
        agent_list = "\n".join(f"- {a['name']}: {a['role']}" for a in agents)

        repo = tracked.repo
        repo_full_name = f"{repo.github_owner}/{repo.github_repo}"
        enhancement = tracked.issue_metadata.get("enhancement", "No enhancement available")

        gh_issue, comments, timeline = await self.gh_client.get_issue_full_context(
            repo_full_name, tracked.github_issue_number
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
            timeline_text = "\n".join(timeline_parts) if timeline_parts else "(no notable events)"
        else:
            timeline_text = "(no notable events)"

        prompt = IMPLEMENTATION_PROMPT_TEMPLATE.format(
            issue_number=tracked.github_issue_number,
            repo_full_name=repo_full_name,
            issue_title=gh_issue.title,
            tier=tier,
            enhancement=enhancement[:3000],
            issue_comments=comments_text,
            issue_timeline=timeline_text,
            agent_list=agent_list,
            working_dir=repo.local_path,
        )

        agent_session = AgentSession(
            issue_id=tracked.id,
            session_type=SessionType.IMPLEMENTATION,
        )
        session.add(agent_session)
        await session.flush()

        tracked.status = IssueStatus.IMPLEMENTING
        tracked.implementation_started_at = datetime.now(UTC)
        tracked.session_id = agent_session.id
        await session.flush()

        try:
            claude_session_id = await self.claude_client.create_session(
                prompt=prompt,
                working_dir=repo.local_path,
                subagents=[a["name"] for a in agents],
                max_cost_usd=self.settings.max_budget_per_issue,
            )
            agent_session.claude_session_id = claude_session_id
            log.info(
                "team_spawned",
                session_id=claude_session_id,
                agent_count=len(agents),
            )

            await self.gh_client.comment_on_issue(
                repo_full_name,
                tracked.github_issue_number,
                f"## ClaudeDev Implementation Started\n\n"
                f"Tier {tier} team spawned with {len(agents)} agents.\n"
                f"Session: `{claude_session_id}`",
            )

            return agent_session

        except Exception:
            agent_session.status = SessionStatus.FAILED
            agent_session.ended_at = datetime.now(UTC)
            tracked.status = IssueStatus.ENHANCED
            tracked.implementation_started_at = None
            log.exception("team_spawn_failed")
            raise

    async def check_session_status(
        self,
        session: AsyncSession,
        agent_session: AgentSession,
    ) -> SessionStatus:
        """Check the status of an active Claude Agent SDK session."""
        if agent_session.claude_session_id is None:
            return SessionStatus.FAILED

        status = await self.claude_client.get_session_status(agent_session.claude_session_id)

        if status == "completed":
            agent_session.status = SessionStatus.COMPLETED
            agent_session.ended_at = datetime.now(UTC)
            cost = await self.claude_client.get_session_cost(agent_session.claude_session_id)
            agent_session.cost_usd = cost
        elif status == "failed":
            agent_session.status = SessionStatus.FAILED
            agent_session.ended_at = datetime.now(UTC)
        elif status == "running":
            agent_session.status = SessionStatus.RUNNING

        await session.flush()
        return agent_session.status
