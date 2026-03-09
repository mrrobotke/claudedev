"""Shared test fixtures for ClaudeDev tests."""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from claudedev.core.state import (
    Project,
    ProjectType,
    Repo,
    RepoDomain,
    close_db,
    get_session_factory,
    init_db,
)
from claudedev.github.gh_client import GHClient
from claudedev.github.webhook_server import create_webhook_app

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

TEST_WEBHOOK_SECRET = "test-secret-12345"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Create an in-memory SQLite database for testing."""
    await init_db("sqlite+aiosqlite:///:memory:")
    factory = get_session_factory()
    async with factory() as session:
        yield session
    await close_db()


@pytest.fixture
def webhook_app():
    """Create a test webhook FastAPI application."""
    return create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)


@pytest.fixture
async def client(webhook_app) -> AsyncGenerator[AsyncClient]:
    """Create an async test client for the webhook app."""
    transport = ASGITransport(app=webhook_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_gh_client() -> GHClient:
    """Create a GHClient with mocked subprocess calls."""
    gh = GHClient()
    gh._run_gh = AsyncMock(return_value="")
    return gh


@pytest.fixture
def issue_event_payload() -> dict[str, Any]:
    """Sample GitHub issue opened event payload."""
    return {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Fix login redirect",
            "body": "The login page redirects to the wrong URL after auth.",
            "state": "open",
            "html_url": "https://github.com/test/repo/issues/42",
            "user": {
                "login": "testuser",
                "id": 12345,
            },
            "labels": [],
            "assignees": [],
        },
        "repository": {
            "id": 99999,
            "name": "repo",
            "full_name": "test/repo",
            "private": False,
            "default_branch": "main",
            "owner": {
                "login": "test",
                "id": 11111,
            },
        },
        "sender": {
            "login": "testuser",
            "id": 12345,
        },
    }


@pytest.fixture
def pr_event_payload() -> dict[str, Any]:
    """Sample GitHub PR opened event payload."""
    return {
        "action": "opened",
        "number": 10,
        "pull_request": {
            "number": 10,
            "title": "Fix login redirect",
            "body": "Fixes #42",
            "state": "open",
            "html_url": "https://github.com/test/repo/pull/10",
            "user": {
                "login": "claudedev-bot",
                "id": 99999,
            },
            "head": {
                "ref": "claudedev/issue-42",
                "sha": "abc123",
                "label": "test:claudedev/issue-42",
            },
            "base": {
                "ref": "main",
                "sha": "def456",
                "label": "test:main",
            },
            "draft": False,
            "labels": [],
        },
        "repository": {
            "id": 99999,
            "name": "repo",
            "full_name": "test/repo",
            "private": False,
            "default_branch": "main",
            "owner": {
                "login": "test",
                "id": 11111,
            },
        },
        "sender": {
            "login": "claudedev-bot",
            "id": 99999,
        },
    }


@pytest.fixture
def comment_event_payload() -> dict[str, Any]:
    """Sample GitHub issue comment event payload."""
    return {
        "action": "created",
        "comment": {
            "id": 777,
            "body": "/implement",
            "user": {
                "login": "testuser",
                "id": 12345,
            },
            "html_url": "https://github.com/test/repo/issues/42#issuecomment-777",
        },
        "issue": {
            "number": 42,
            "title": "Fix login redirect",
            "body": "The login page redirects to the wrong URL after auth.",
            "state": "open",
            "user": {
                "login": "testuser",
                "id": 12345,
            },
            "labels": [],
            "assignees": [],
        },
        "repository": {
            "id": 99999,
            "name": "repo",
            "full_name": "test/repo",
            "private": False,
            "default_branch": "main",
            "owner": {
                "login": "test",
                "id": 11111,
            },
        },
        "sender": {
            "login": "testuser",
            "id": 12345,
        },
    }


@pytest.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    """Database session pre-seeded with a project and repo for FK tests."""
    project = Project(name="test-project", type=ProjectType.POLYREPO)
    db_session.add(project)
    await db_session.flush()

    repo = Repo(
        project_id=project.id,
        domain=RepoDomain.BACKEND,
        local_path="/tmp/test/repo",
        github_owner="test",
        github_repo="repo",
    )
    db_session.add(repo)
    await db_session.flush()
    return db_session


def make_signature(payload: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    """Generate HMAC-SHA256 signature for a webhook payload."""
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
