"""Team spawner: classifies tier and runs implementation via Claude Agent SDK."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from claudedev.brain.autoresponder import (
    AutoResponder,
    DecisionLogger,
    QuestionClassifier,
    StreamAnalyzer,
)
from claudedev.core.state import (
    AgentSession,
    IssueStatus,
    PRStatus,
    SessionStatus,
    SessionType,
    TrackedIssue,
    TrackedPR,
)
from claudedev.engines.worktree_manager import WorktreeManager
from claudedev.utils.paths import escape_path_for_claude

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from claudedev.brain.config import BrainConfig
    from claudedev.brain.integration.claude_bridge import ClaudeBridge
    from claudedev.brain.memory.episodic import EpisodicStore
    from claudedev.config import Settings
    from claudedev.engines.steering_manager import SteeringManager
    from claudedev.engines.websocket_manager import WebSocketManager
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

IMPORTANT: After creating the pull request, output the following metadata
as the VERY LAST LINES of your response:

PR_NUMBER: <the PR number>
BRANCH: claudedev/issue-{issue_number}
"""


class TeamEngine:
    """Spawns Claude Agent SDK teams based on issue tier classification."""

    def __init__(
        self,
        settings: Settings,
        gh_client: GHClient,
        claude_client: ClaudeSDKClient,
        ws_manager: WebSocketManager | None = None,
        steering_manager: SteeringManager | None = None,
        hook_secret: str = "",
        brain_config: BrainConfig | None = None,
        claude_bridge: ClaudeBridge | None = None,
        episodic_store: EpisodicStore | None = None,
    ) -> None:
        self.settings = settings
        self.gh_client = gh_client
        self.claude_client = claude_client
        self.ws_manager = ws_manager
        self.steering_manager = steering_manager
        self.hook_secret = hook_secret
        self._brain_config = brain_config
        self._claude_bridge = claude_bridge
        self._episodic_store = episodic_store

    async def run_implementation(
        self,
        session: AsyncSession,
        tracked: TrackedIssue,
    ) -> AgentSession:
        """Run Claude to implement the given issue.

        Creates an isolated git worktree for the implementation, invokes Claude
        via ``run_query()``, collects output, extracts a PR number from metadata
        lines, creates a ``TrackedPR`` record, updates the tracked issue, and
        posts a GitHub comment with the implementation summary.
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

        agent_session = AgentSession(
            issue_id=tracked.id,
            session_type=SessionType.IMPLEMENTATION,
            started_at=datetime.now(UTC),  # Python-side default avoids None until DB refresh
        )
        session.add(agent_session)
        await session.flush()  # assign agent_session.id before commit

        tracked.status = IssueStatus.IMPLEMENTING
        tracked.implementation_started_at = datetime.now(UTC)
        tracked.session_id = agent_session.id
        await session.commit()

        stream_session_id = str(agent_session.id)
        if self.steering_manager:
            self.steering_manager.register_session(stream_session_id)

        try:
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
                timeline_text = (
                    "\n".join(timeline_parts) if timeline_parts else "(no notable events)"
                )
            else:
                timeline_text = "(no notable events)"

            # Create isolated worktree for implementation
            wt_manager = WorktreeManager()
            working_dir = repo.local_path
            try:
                wt_info = await wt_manager.create_worktree(
                    Path(repo.local_path),
                    tracked.github_issue_number,
                    repo.default_branch or "main",
                )
                working_dir = str(wt_info.path)
                tracked.worktree_path = working_dir
                await wt_manager.write_hook_config(
                    wt_info.path,
                    stream_session_id,
                    tracked.github_issue_number,
                    hook_secret=self.hook_secret,
                )
                log.info("worktree_ready", worktree_path=working_dir)
            except Exception as exc:
                logger.warning(
                    "worktree_creation_failed",
                    error=str(exc),
                    issue=tracked.github_issue_number,
                )
                working_dir = repo.local_path  # Fallback to main checkout

            prompt = IMPLEMENTATION_PROMPT_TEMPLATE.format(
                issue_number=tracked.github_issue_number,
                repo_full_name=repo_full_name,
                issue_title=gh_issue.title,
                tier=tier,
                enhancement=enhancement[:3000],
                issue_comments=comments_text,
                issue_timeline=timeline_text,
                agent_list=agent_list,
                working_dir=working_dir,
            )

            implementation_text = ""
            use_stream_json = self.ws_manager is not None
            output_format = "stream-json" if use_stream_json else "text"

            # Auto-respond setup
            stream_analyzer = StreamAnalyzer() if use_stream_json else None
            auto_responder = None
            decision_logger = None
            max_loops = 1  # Default: no auto-response

            if (
                self._brain_config
                and self._brain_config.auto_respond_enabled
                and self._claude_bridge
                and use_stream_json
            ):
                auto_responder = AutoResponder(
                    self._brain_config,
                    self._claude_bridge,
                    self._episodic_store,
                )
                decision_logger = DecisionLogger(
                    episodic_store=self._episodic_store,
                    ws_manager=self.ws_manager,
                )
                max_loops = self._brain_config.max_auto_responses + 1

            claude_session_id: str | None = None
            is_resume = False
            resume_prompt = ""

            for attempt in range(max_loops):
                if is_resume and claude_session_id:
                    stream_source = self.claude_client.resume_session(
                        session_id=claude_session_id,
                        prompt=resume_prompt,
                        cwd=working_dir,
                        ws_session_id=stream_session_id,
                        ws_manager=self.ws_manager,
                    )
                else:
                    stream_source = self.claude_client.run_query(
                        prompt,
                        cwd=working_dir,
                        max_turns=30,
                        output_format=output_format,
                        session_id=stream_session_id,
                        ws_manager=self.ws_manager,
                    )

                async for chunk in stream_source:
                    if use_stream_json:
                        stripped = chunk.strip()
                        if not stripped:
                            continue
                        if stream_analyzer:
                            stream_analyzer.feed(stripped)
                        try:
                            event = json.loads(stripped)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        event_type = event.get("type", "")
                        if event_type == "assistant":
                            content_blocks = (
                                event.get("message", {}).get("content")
                                or event.get("content")
                                or []
                            )
                            for block in content_blocks:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    implementation_text += block.get("text", "")
                        elif event_type == "result":
                            result = event.get("result", "")
                            if isinstance(result, str):
                                implementation_text += result
                    else:
                        implementation_text += chunk

                # Check for detected question
                if (
                    stream_analyzer
                    and stream_analyzer.detected_question()
                    and auto_responder
                    and attempt < max_loops - 1
                ):
                    question = stream_analyzer.get_question()
                    if question:
                        log.info(
                            "auto_response_question_detected",
                            question=question.question_text[:200],
                            attempt=attempt,
                        )

                        if self.ws_manager:
                            await self.ws_manager.broadcast_activity(
                                stream_session_id,
                                "auto_response_thinking",
                                {"question": question.question_text[:200]},
                            )

                        classification = QuestionClassifier.classify(
                            question.question_text,
                        )
                        issue_context = {
                            "number": tracked.github_issue_number,
                            "title": gh_issue.title,
                            "body": gh_issue.body or "",
                        }
                        response = await auto_responder.respond(
                            question,
                            issue_context,
                            classification,
                        )

                        if decision_logger:
                            await decision_logger.log(
                                question=question,
                                response=response,
                                issue_number=tracked.github_issue_number,
                                session_id=stream_session_id,
                            )

                        # Prepare for resume
                        claude_session_id = (
                            stream_analyzer.claude_session_id
                            or self._find_claude_session_id(
                                working_dir,
                                agent_session.started_at,
                            )
                        )
                        resume_prompt = response.answer
                        stream_analyzer.reset_for_resume()
                        is_resume = True

                        if self.ws_manager:
                            await self.ws_manager.broadcast_activity(
                                stream_session_id,
                                "auto_response_resumed",
                                {
                                    "answer": response.answer[:200],
                                    "risk_score": response.risk_score,
                                },
                            )

                        continue  # Next loop iteration will resume

                break  # Normal completion -- exit the loop

            # Guard against CLI error output being treated as a successful implementation
            if not implementation_text.strip():
                raise RuntimeError(
                    "Claude CLI produced no output — the process likely failed immediately"
                )
            if implementation_text.strip().startswith("Error:"):
                raise RuntimeError(
                    f"Claude CLI returned an error: {implementation_text.strip()[:200]}"
                )

            claude_sid = self._find_claude_session_id(working_dir, agent_session.started_at)
            if claude_sid:
                agent_session.claude_session_id = claude_sid

            pr_number = self._extract_pr_number(implementation_text)

            # Fallback: find PR by well-known branch name when metadata extraction fails
            if pr_number is None:
                branch_name = f"claudedev/issue-{tracked.github_issue_number}"
                pr_number = await self.gh_client.find_pr_by_branch(repo_full_name, branch_name)

            if pr_number is not None:
                tracked.pr_number = pr_number
                tracked.status = IssueStatus.IN_REVIEW

                # Create TrackedPR record linking the PR to the issue
                tracked_pr = TrackedPR(
                    issue_id=tracked.id,
                    repo_id=repo.id,
                    pr_number=pr_number,
                    status=PRStatus.OPEN,
                    review_iteration=0,
                )
                session.add(tracked_pr)

                # Best-effort worktree cleanup after PR creation
                try:
                    wt_manager = WorktreeManager()
                    cleaned = await wt_manager.cleanup_worktree(
                        Path(repo.local_path),
                        tracked.github_issue_number,
                    )
                    if cleaned:
                        tracked.worktree_path = None
                        log.info(
                            "worktree_cleaned_after_pr",
                            issue=tracked.github_issue_number,
                        )
                except Exception:
                    log.warning(
                        "worktree_cleanup_after_pr_failed",
                        issue=tracked.github_issue_number,
                        exc_info=True,
                    )
            else:
                tracked.status = IssueStatus.DONE

            agent_session.status = SessionStatus.COMPLETED
            agent_session.ended_at = datetime.now(UTC)
            agent_session.summary = (
                f"Implemented issue #{tracked.github_issue_number}, tier={tier}, pr={pr_number}"
            )

            log.info(
                "implementation_complete",
                pr_number=pr_number,
                agent_count=len(agents),
            )

            if tracked.pr_number:
                await self.gh_client.comment_on_issue(
                    repo_full_name,
                    tracked.github_issue_number,
                    f"## Implementation Complete\n\n"
                    f"Pull request opened: #{tracked.pr_number}\n"
                    f"Branch: `claudedev/issue-{tracked.github_issue_number}`",
                )

            return agent_session

        except Exception:
            agent_session.status = SessionStatus.FAILED
            agent_session.ended_at = datetime.now(UTC)

            # Fallback: check if a PR was created despite the error
            if not tracked.pr_number:
                try:
                    branch_name = f"claudedev/issue-{tracked.github_issue_number}"
                    fallback_pr = await self.gh_client.find_pr_by_branch(
                        repo_full_name,
                        branch_name,
                    )
                    if fallback_pr is not None:
                        tracked.pr_number = fallback_pr
                        log.info(
                            "fallback_pr_found",
                            pr_number=fallback_pr,
                            issue=tracked.github_issue_number,
                        )
                except Exception:
                    log.debug("fallback_pr_check_failed", exc_info=True)

            if tracked.pr_number:
                # PR was created before the error — preserve progress
                tracked.status = IssueStatus.IN_REVIEW
                log.warning(
                    "implementation_partial_success",
                    pr_number=tracked.pr_number,
                    msg="PR created but post-implementation step failed",
                )
            else:
                tracked.status = IssueStatus.FAILED
                tracked.implementation_started_at = None
            await session.commit()  # Persist failure status before propagating
            log.exception("implementation_failed")
            raise
        finally:
            if self.steering_manager:
                self.steering_manager.unregister_session(stream_session_id)
            if self.ws_manager:
                self.ws_manager.cleanup_session(stream_session_id)

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

    @staticmethod
    def _extract_pr_number(text: str) -> int | None:
        """Extract a PR number from Claude's implementation output.

        Tries three strategies in order:
        1. A ``PR_NUMBER: <N>`` metadata line.
        2. A line containing "pull request" or "created pull request" with ``#<N>``.
        3. A ``/pull/<N>`` URL pattern.

        Returns the PR number as an integer, or ``None`` if not found.
        """
        # Strategy 1: explicit metadata line
        for line in text.splitlines():
            m = re.match(r"^\s*PR_NUMBER:\s*(\d+)", line, re.IGNORECASE)
            if m:
                return int(m.group(1))

        # Strategy 2: "pull request #N" pattern (tighter — requires verb prefix)
        pr_pattern = re.search(
            r"(?:created|opened|merged)?\s*pull\s+request\s+#(\d+)", text, re.IGNORECASE
        )
        if pr_pattern:
            return int(pr_pattern.group(1))

        # Strategy 3: /pull/<N> URL
        m = re.search(r"/pull/(\d+)", text)
        if m:
            return int(m.group(1))

        return None

    def _find_claude_session_id(self, repo_local_path: str, started_after: datetime) -> str | None:
        """Find the Claude Code session ID by scanning JSONL files in the project dir.

        Claude Code's ``claude -p`` mode creates JSONL session files but does NOT
        update sessions-index.json. We therefore scan .jsonl files sorted by mtime
        (newest first), read the first event's timestamp, and return the session
        whose start is closest to ``started_after`` within a 120-second window.
        """
        try:
            escaped = escape_path_for_claude(repo_local_path)
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
