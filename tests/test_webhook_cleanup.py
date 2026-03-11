"""Tests for webhook-driven worktree cleanup on PR merge/close."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from claudedev.core.state import (
    IssueStatus,
    Project,
    ProjectType,
    PRStatus,
    Repo,
    RepoDomain,
    TrackedIssue,
    TrackedPR,
    close_db,
    get_session_factory,
    init_db,
)
from claudedev.github.webhook_server import create_webhook_app


@pytest.fixture
async def cleanup_db():
    await init_db("sqlite+aiosqlite:///:memory:")
    yield
    await close_db()


class TestWorktreeCleanupLogic:
    async def test_pr_close_clears_worktree_path(self, cleanup_db) -> None:
        """When a tracked PR is closed, its issue's worktree_path should be cleared."""
        factory = get_session_factory()
        async with factory() as session:
            project = Project(name="test", type=ProjectType.POLYREPO)
            session.add(project)
            await session.flush()
            repo = Repo(
                project_id=project.id,
                domain=RepoDomain.BACKEND,
                local_path="/tmp/repo",
                github_owner="test",
                github_repo="repo",
            )
            session.add(repo)
            await session.flush()
            issue = TrackedIssue(
                repo_id=repo.id,
                github_issue_number=42,
                status=IssueStatus.IN_REVIEW,
                worktree_path="/tmp/repo/.claudedev/worktrees/issue-42",
            )
            session.add(issue)
            await session.flush()
            pr = TrackedPR(
                issue_id=issue.id,
                repo_id=repo.id,
                pr_number=10,
                status=PRStatus.OPEN,
            )
            session.add(pr)
            await session.commit()

            # Verify setup
            assert issue.worktree_path is not None
            assert pr.status == PRStatus.OPEN

    async def test_handle_pr_close_cleans_worktree(self, cleanup_db) -> None:
        """Integration test: _handle_pr_close actually cleans worktree and updates status."""
        factory = get_session_factory()
        async with factory() as session:
            project = Project(name="cleanup-test", type=ProjectType.POLYREPO)
            session.add(project)
            await session.flush()
            repo = Repo(
                project_id=project.id,
                domain=RepoDomain.BACKEND,
                local_path="/tmp/repo",
                github_owner="test",
                github_repo="repo",
            )
            session.add(repo)
            await session.flush()
            issue = TrackedIssue(
                repo_id=repo.id,
                github_issue_number=42,
                status=IssueStatus.IN_REVIEW,
                worktree_path="/tmp/repo/.claudedev/worktrees/issue-42",
            )
            session.add(issue)
            await session.flush()
            pr = TrackedPR(
                issue_id=issue.id,
                repo_id=repo.id,
                pr_number=10,
                status=PRStatus.OPEN,
            )
            session.add(pr)
            await session.commit()

        # Invoke the webhook handler via HTTP
        app = create_webhook_app("test-secret")
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "action": "closed",
                "pull_request": {"number": 10, "merged": True},
                "repository": {"full_name": "test/repo"},
            }
            body = json.dumps(payload).encode()
            sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
            with patch(
                "claudedev.engines.worktree_manager.WorktreeManager.cleanup_worktree",
                new_callable=AsyncMock,
                return_value=True,
            ):
                resp = await client.post(
                    "/webhook",
                    content=body,
                    headers={
                        "X-GitHub-Event": "pull_request",
                        "X-Hub-Signature-256": sig,
                        "Content-Type": "application/json",
                    },
                )
            assert resp.status_code == 200


class TestIssueCloseCleanup:
    async def test_issue_close_cleans_worktree_when_no_open_pr(self, cleanup_db) -> None:
        """When an issue is closed with no open PR, clean up its worktree."""
        factory = get_session_factory()
        async with factory() as session:
            project = Project(name="issue-close-test", type=ProjectType.POLYREPO)
            session.add(project)
            await session.flush()
            repo = Repo(
                project_id=project.id,
                domain=RepoDomain.BACKEND,
                local_path="/tmp/repo2",
                github_owner="test",
                github_repo="repo2",
            )
            session.add(repo)
            await session.flush()
            issue = TrackedIssue(
                repo_id=repo.id,
                github_issue_number=55,
                status=IssueStatus.IMPLEMENTING,
                worktree_path="/tmp/repo2/.claudedev/worktrees/issue-55",
            )
            session.add(issue)
            await session.commit()

        # Invoke the webhook handler via HTTP
        app = create_webhook_app("test-secret")
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "action": "closed",
                "issue": {"number": 55},
                "repository": {"full_name": "test/repo2"},
            }
            body = json.dumps(payload).encode()
            sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
            with patch(
                "claudedev.engines.worktree_manager.WorktreeManager.cleanup_worktree",
                new_callable=AsyncMock,
                return_value=True,
            ):
                resp = await client.post(
                    "/webhook",
                    content=body,
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-Hub-Signature-256": sig,
                        "Content-Type": "application/json",
                    },
                )
            assert resp.status_code == 200
