"""Tests for the issue enhancement pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from claudedev.core.state import IssueTier
from claudedev.engines.issue_engine import IssueEngine


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.enhancement_max_turns = 50
    return settings


@pytest.fixture
def mock_gh_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_claude_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def engine(
    mock_settings: MagicMock,
    mock_gh_client: AsyncMock,
    mock_claude_client: AsyncMock,
) -> IssueEngine:
    return IssueEngine(
        settings=mock_settings,
        gh_client=mock_gh_client,
        claude_client=mock_claude_client,
    )


class TestClassifyTier:
    def test_classify_tier_1_single_file(self, engine: IssueEngine) -> None:
        text = """## Analysis
This is a small bug fix affecting one file.
Affected files: src/utils/helper.py

TIER: 1"""
        result = engine.classify_tier(text)
        assert result == "1"

    def test_classify_tier_2_multi_file(self, engine: IssueEngine) -> None:
        text = """## Analysis
Medium feature spanning 5 files across the service layer.
Affected: models.py, views.py, serializers.py, urls.py, tests.py

TIER: 2"""
        result = engine.classify_tier(text)
        assert result == "2"

    def test_classify_tier_3_major_refactor(self, engine: IssueEngine) -> None:
        text = """## Analysis
Major refactoring of the authentication module. 15+ files affected.
Complete rewrite of the auth flow with new middleware.

TIER: 3"""
        result = engine.classify_tier(text)
        assert result == "3"

    def test_classify_tier_4_cross_domain(self, engine: IssueEngine) -> None:
        text = """## Analysis
Full-stack feature requiring backend API + frontend UI changes.
Backend: new endpoints, models, migrations
Frontend: new screens, components, state management

TIER: 4"""
        result = engine.classify_tier(text)
        assert result == "4"

    def test_classify_tier_default_when_missing(self, engine: IssueEngine) -> None:
        text = """## Analysis
Some analysis without a tier line at the end."""
        result = engine.classify_tier(text)
        assert result == IssueTier.TIER_2

    def test_classify_tier_case_insensitive(self, engine: IssueEngine) -> None:
        text = """Analysis done.
TIER: 3"""
        result = engine.classify_tier(text)
        assert result == "3"

    def test_classify_tier_with_extra_whitespace(self, engine: IssueEngine) -> None:
        text = """Analysis done.
Tier:   1  """
        result = engine.classify_tier(text)
        assert result == "1"

    def test_classify_tier_invalid_value_returns_default(self, engine: IssueEngine) -> None:
        text = """Analysis.
Tier: 5"""
        result = engine.classify_tier(text)
        assert result == IssueTier.TIER_2

    def test_classify_tier_from_last_occurrence(self, engine: IssueEngine) -> None:
        text = """Tier: 1
Some more analysis here.
Tier: 3"""
        result = engine.classify_tier(text)
        assert result == "3"


class TestStripMetadata:
    def test_strips_tier_line(self, engine: IssueEngine) -> None:
        text = "Some clean body.\n\nMore content.\n\nTIER: 2"
        clean_body, tier, validation_failed, cross_repo_items = engine._strip_metadata(text)
        assert "TIER:" not in clean_body
        assert tier == "2"
        assert validation_failed is False
        assert cross_repo_items == []

    def test_strips_validation_failed(self, engine: IssueEngine) -> None:
        text = "Body content here.\n\nVALIDATION_FAILED: Could not reproduce.\nTIER: 1"
        clean_body, tier, validation_failed, _cross_repo_items = engine._strip_metadata(text)
        assert "VALIDATION_FAILED" not in clean_body
        assert validation_failed is True
        assert tier == "1"

    def test_strips_cross_repo(self, engine: IssueEngine) -> None:
        text = "Body content.\n\nCROSS_REPO: owner/frontend - Add login redirect UI\nTIER: 4"
        clean_body, tier, _validation_failed, cross_repo_items = engine._strip_metadata(text)
        assert "CROSS_REPO" not in clean_body
        assert tier == "4"
        assert cross_repo_items == [("owner/frontend", "Add login redirect UI")]

    def test_strips_multiple_cross_repo(self, engine: IssueEngine) -> None:
        text = (
            "Body.\n\n"
            "CROSS_REPO: org/frontend - Frontend change\n"
            "CROSS_REPO: org/mobile - Mobile change\n"
            "TIER: 4"
        )
        _, _, _, cross_repo_items = engine._strip_metadata(text)
        assert len(cross_repo_items) == 2
        assert ("org/frontend", "Frontend change") in cross_repo_items
        assert ("org/mobile", "Mobile change") in cross_repo_items

    def test_clean_body_preserves_content(self, engine: IssueEngine) -> None:
        body = (
            "## Problem\n\nThe login page is broken.\n\n## Steps\n1. Go to /login\n2. Click submit"
        )
        text = f"{body}\n\nTIER: 1"
        clean_body, _, _, _ = engine._strip_metadata(text)
        assert clean_body == body

    def test_default_tier_when_missing(self, engine: IssueEngine) -> None:
        text = "Just some body text with no tier."
        _, tier, _, _ = engine._strip_metadata(text)
        assert tier == IssueTier.TIER_2


class TestStripThinkingText:
    def test_strips_preamble_before_heading(self, engine: IssueEngine) -> None:
        text = (
            "Now I have a complete picture of the issue. Let me write the rewritten issue.\n"
            "Looking at the codebase more carefully.\n"
            "\n"
            "## Problem\n"
            "\n"
            "The login page redirects to the wrong URL.\n"
        )
        result = IssueEngine._strip_thinking_text(text)
        assert result.startswith("## Problem")
        assert "Now I have" not in result
        assert "Looking at" not in result

    def test_strips_with_h1_heading(self, engine: IssueEngine) -> None:
        text = (
            "Let me analyze this carefully.\n"
            "# Bug Report\n"
            "Something is broken.\n"
        )
        result = IssueEngine._strip_thinking_text(text)
        assert result.startswith("# Bug Report")
        assert "Let me" not in result

    def test_no_heading_filters_thinking_lines(self, engine: IssueEngine) -> None:
        # "Alright" was removed from the prefix list (too generic — could appear in
        # legitimate issue content).  Use a Claude-specific pattern instead.
        text = (
            "Now I need to look at the codebase.\n"
            "Let me check the files.\n"
            "The login redirect is broken.\n"
            "I've analyzed the codebase thoroughly.\n"
            "This affects users who log in.\n"
        )
        result = IssueEngine._strip_thinking_text(text)
        assert "Now I need" not in result
        assert "Let me check" not in result
        assert "I've analyzed" not in result
        # Non-thinking line should be preserved
        assert "The login redirect is broken." in result

    def test_clean_text_unchanged(self, engine: IssueEngine) -> None:
        text = (
            "## Problem\n\n"
            "The API endpoint returns 500 on invalid input.\n\n"
            "## Root Cause\n\n"
            "Missing input validation in the handler.\n"
        )
        result = IssueEngine._strip_thinking_text(text)
        assert result == text.strip()

    def test_mixed_thinking_in_preamble_only(self, engine: IssueEngine) -> None:
        text = (
            "I've analyzed the issue thoroughly.\n"
            "Based on my investigation:\n"
            "\n"
            "## Summary\n"
            "\n"
            "I've analyzed the root cause correctly.\n"
        )
        result = IssueEngine._strip_thinking_text(text)
        # Heading-based stripping: everything from ## Summary onward is kept
        assert result.startswith("## Summary")
        # The "I've analyzed" line AFTER the heading is preserved (it's body content)
        assert "I've analyzed the root cause correctly." in result

    def test_strips_leading_trailing_blank_lines(self, engine: IssueEngine) -> None:
        text = "\n\n## Problem\n\nSomething is wrong.\n\n"
        result = IssueEngine._strip_thinking_text(text)
        assert not result.startswith("\n")
        assert not result.endswith("\n")

    def test_all_thinking_prefixes_filtered_without_heading(self, engine: IssueEngine) -> None:
        # Only Claude-specific thinking patterns are filtered.  Generic phrases like
        # "the issue", "this is a", "looking at", "alright", "i have" (broad),
        # "based on" (broad), and "i notice" (broad) were removed from the prefix
        # list to avoid stripping legitimate issue content.
        thinking_lines = [
            "Now I understand the problem.",
            "Let me check the code.",
            "I'll implement a fix.",
            "I need to look further.",
            "I have a complete picture now.",
            "I can see the issue.",
            "I should review this.",
            "First, I will check.",
            "Next, I need to verify.",
            "Based on my analysis, the bug is clear.",
            "After reviewing the PR.",
            "Having analyzed the issue.",
            "I want to confirm this.",
            "I've analyzed the code.",
            "I notice that the value is wrong.",
        ]
        for line in thinking_lines:
            result = IssueEngine._strip_thinking_text(line)
            assert result == "", f"Expected empty result for thinking line: {line!r}"

    def test_non_thinking_generic_phrases_preserved(self, engine: IssueEngine) -> None:
        # These phrases were previously over-filtered; they must now be preserved.
        preserved_lines = [
            "The issue affects all users with expired sessions.",
            "This is a regression introduced in v2.3.1.",
            "Looking at the dashboard, the chart shows incorrect totals.",
            "Alright, here are the reproduction steps.",
            "I have a reproduction case ready.",
            "Based on the error logs, the timeout occurs at line 42.",
            "I notice the dropdown does not close on outside click.",
        ]
        for line in preserved_lines:
            result = IssueEngine._strip_thinking_text(line)
            assert result != "", f"Generic phrase should NOT be stripped: {line!r}"


class TestEnhanceIssue:
    async def test_enhance_issue_formats_output(
        self,
        engine: IssueEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            Repo,
            TrackedIssue,
        )

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=42,
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Fix login redirect"
        mock_gh_issue.body = "Login page redirects wrong"
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.update_issue = AsyncMock()

        enhancement_text = """## Problem

The login page redirects to the wrong URL after authentication.

## Root Cause

The redirect URL is hardcoded in the auth handler.

## Affected Files

- src/auth/redirect.py

## Implementation Approach

1. Replace hardcoded URL with configurable setting.
2. Add tests for redirect behavior.

## Acceptance Criteria

- Login redirects to the correct destination.

TIER: 1"""

        async def mock_query(prompt, **kwargs):
            for chunk in [enhancement_text]:
                yield chunk

        mock_claude_client.run_query = mock_query

        result = await engine.enhance_issue(session, tracked)

        assert result.status == IssueStatus.ENHANCED
        assert result.tier == "1"
        assert result.enhanced_at is not None
        assert result.issue_metadata["enhancement"] is not None
        assert result.issue_metadata["original_title"] == "Fix login redirect"

        mock_gh_client.update_issue.assert_awaited_once()
        update_kwargs = mock_gh_client.update_issue.call_args[1]
        # No "ClaudeDev Enhancement" header
        assert "ClaudeDev Enhancement" not in update_kwargs["body"]
        # Tier line is stripped from body
        assert "TIER:" not in update_kwargs["body"]
        # Content is present
        assert "redirect" in update_kwargs["body"].lower()

    async def test_enhance_issue_validation_failed(
        self,
        engine: IssueEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            Repo,
            TrackedIssue,
        )

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=55,
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Page crashes on load"
        mock_gh_issue.body = "The page crashes when I open it."
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.update_issue = AsyncMock()
        mock_gh_client.comment_on_issue = AsyncMock()

        enhancement_text = (
            "## Problem\n\nCould not identify the reported crash.\n\n"
            "VALIDATION_FAILED: Could not reproduce the crash.\n"
            "TIER: 2"
        )

        async def mock_query(prompt, **kwargs):
            for chunk in [enhancement_text]:
                yield chunk

        mock_claude_client.run_query = mock_query

        result = await engine.enhance_issue(session, tracked)

        assert result.status == IssueStatus.ENHANCED
        # update_issue must NOT be called when validation fails
        mock_gh_client.update_issue.assert_not_awaited()
        # comment_on_issue MUST be called asking for reproduction steps
        mock_gh_client.comment_on_issue.assert_awaited_once()
        comment_args = mock_gh_client.comment_on_issue.call_args
        assert (
            "reproduce" in comment_args[1]["body"].lower()
            or "reproduce" in str(comment_args[0]).lower()
        )

    async def test_enhance_issue_cross_repo(
        self,
        engine: IssueEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            Repo,
            RepoDomain,
            TrackedIssue,
        )

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        # Add a sibling frontend repo
        sibling_repo = Repo(
            project_id=repo.project_id,
            domain=RepoDomain.FRONTEND,
            local_path="/tmp/test/frontend",
            github_owner="test",
            github_repo="frontend",
        )
        session.add(sibling_repo)
        await session.flush()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=77,
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_issue = MagicMock()
        mock_gh_issue.title = "Add user profile API and UI"
        mock_gh_issue.body = "Need both backend endpoints and frontend screens."
        mock_gh_client.get_issue_full_context = AsyncMock(return_value=(mock_gh_issue, [], []))
        mock_gh_client.update_issue = AsyncMock()
        mock_gh_client.create_issue = AsyncMock()

        enhancement_text = (
            "## Problem\n\nUser profile feature requires backend and frontend work.\n\n"
            "CROSS_REPO: test/frontend - Add user profile screens\n"
            "TIER: 4"
        )

        async def mock_query(prompt, **kwargs):
            for chunk in [enhancement_text]:
                yield chunk

        mock_claude_client.run_query = mock_query

        result = await engine.enhance_issue(session, tracked)

        assert result.status == IssueStatus.ENHANCED
        # update_issue called with clean body
        mock_gh_client.update_issue.assert_awaited_once()
        # create_issue called for the cross-repo follow-up
        mock_gh_client.create_issue.assert_awaited_once()
        create_args = mock_gh_client.create_issue.call_args
        assert create_args[0][0] == "test/frontend"
        assert create_args[1]["title"] == "Add user profile screens"

    async def test_enhance_issue_failure_resets_status(
        self,
        engine: IssueEngine,
        mock_gh_client: AsyncMock,
        mock_claude_client: AsyncMock,
        seeded_db,
    ) -> None:
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            Repo,
            TrackedIssue,
        )

        session = seeded_db

        result = await session.execute(select(Repo))
        repo = result.scalar_one()

        tracked = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=99,
        )
        tracked.repo = repo
        session.add(tracked)
        await session.flush()

        mock_gh_client.get_issue_full_context = AsyncMock(side_effect=Exception("GitHub API down"))

        with pytest.raises(Exception, match="GitHub API down"):
            await engine.enhance_issue(session, tracked)

        assert tracked.status == IssueStatus.NEW
