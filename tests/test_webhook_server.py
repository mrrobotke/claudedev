"""Tests for the FastAPI webhook server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from tests.conftest import TEST_WEBHOOK_SECRET, make_api_client, make_signature

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "claudedev"


class TestWebhookSignatureVerification:
    async def test_missing_signature_returns_401(
        self, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """POST /webhook without X-Hub-Signature-256 returns 401."""
        response = await client.post(
            "/webhook",
            content=json.dumps(issue_event_payload),
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-1",
            },
        )
        assert response.status_code == 401
        assert "Missing signature" in response.json()["detail"]

    async def test_invalid_signature_returns_401(
        self, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """POST /webhook with wrong HMAC returns 401."""
        body = json.dumps(issue_event_payload).encode()
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid_signature_value",
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-2",
            },
        )
        assert response.status_code == 401
        assert "Invalid signature" in response.json()["detail"]

    async def test_valid_signature_returns_200(
        self, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """POST /webhook with correct HMAC returns 200."""
        body = json.dumps(issue_event_payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-3",
            },
        )
        assert response.status_code == 200

    async def test_signature_without_sha256_prefix_fails(
        self, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """Signature without sha256= prefix is invalid."""
        body = json.dumps(issue_event_payload).encode()
        import hashlib
        import hmac

        digest = hmac.new(TEST_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": digest,  # missing sha256= prefix
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-4",
            },
        )
        assert response.status_code == 401


class TestWebhookEventRouting:
    async def test_issue_opened_accepted(
        self, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """Verify issue.opened event is routed correctly and returns accepted."""
        body = json.dumps(issue_event_payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-5",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    async def test_pr_opened_accepted(
        self, client: AsyncClient, pr_event_payload: dict[str, Any]
    ) -> None:
        """Verify pull_request.opened event is routed correctly."""
        body = json.dumps(pr_event_payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "pull_request",
                "X-GitHub-Delivery": "test-delivery-6",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    async def test_comment_event_accepted(
        self, client: AsyncClient, comment_event_payload: dict[str, Any]
    ) -> None:
        """Verify issue_comment event is routed correctly."""
        body = json.dumps(comment_event_payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issue_comment",
                "X-GitHub-Delivery": "test-delivery-7",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    async def test_unknown_event_ignored(self, client: AsyncClient) -> None:
        """Unknown event type returns 200 with status=ignored."""
        payload = {"action": "something", "data": "test"}
        body = json.dumps(payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "deployment_status",
                "X-GitHub-Delivery": "test-delivery-8",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    async def test_ping_event_accepted(self, client: AsyncClient) -> None:
        """Ping event (sent on webhook creation) returns accepted."""
        payload = {
            "zen": "Anything added dilutes everything else.",
            "hook_id": 12345,
            "repository": {
                "id": 99999,
                "name": "repo",
                "full_name": "test/repo",
                "private": False,
                "default_branch": "main",
                "owner": {"login": "test", "id": 11111},
            },
        }
        body = json.dumps(payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "ping",
                "X-GitHub-Delivery": "test-delivery-9",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


class TestWebhookOrchestratorDispatch:
    async def test_orchestrator_dispatch_called_on_issue_event(
        self, webhook_app, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """When an orchestrator is attached, it receives dispatched events."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.dispatch = AsyncMock()
        webhook_app.state.orchestrator = mock_orchestrator

        body = json.dumps(issue_event_payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-10",
            },
        )
        assert response.status_code == 200
        mock_orchestrator.dispatch.assert_awaited_once()

    async def test_no_orchestrator_still_succeeds(
        self, client: AsyncClient, issue_event_payload: dict[str, Any]
    ) -> None:
        """Without an orchestrator, webhook still returns 200."""
        body = json.dumps(issue_event_payload).encode()
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-11",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"


class TestWebhookInvalidPayload:
    async def test_invalid_json_returns_400(self, client: AsyncClient) -> None:
        """Invalid JSON body returns 400."""
        body = b"not valid json {"
        sig = make_signature(body)
        response = await client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "test-delivery-12",
            },
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]


class TestWebhookNoSecret:
    async def test_no_secret_configured_rejects_with_503(self) -> None:
        """When no secret is configured, all requests are rejected with 503."""
        from httpx import ASGITransport

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {"action": "opened", "zen": "test"}
            response = await ac.post(
                "/webhook",
                content=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "ping",
                },
            )
            assert response.status_code == 503


class TestSessionHistory:
    """Tests for GET /api/sessions/{session_id}/history."""

    async def test_session_history_not_found(self, seeded_db: AsyncSession) -> None:
        """GET /api/sessions/99999/history returns 404 when session does not exist."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        async with make_api_client(app) as ac:
            response = await ac.get("/api/sessions/99999/history")

        assert response.status_code == 404

    async def test_session_history_no_claude_session(self, seeded_db: AsyncSession) -> None:
        """GET /api/sessions/{id}/history returns empty events when no JSONL file exists."""
        from sqlalchemy import select

        from claudedev.core.state import (
            AgentSession,
            IssueStatus,
            Repo,
            SessionStatus,
            SessionType,
            TrackedIssue,
        )
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=888, status=IssueStatus.ENHANCED)
        seeded_db.add(issue)
        await seeded_db.flush()

        agent_session = AgentSession(
            issue_id=issue.id,
            session_type=SessionType.ENHANCEMENT,
            status=SessionStatus.COMPLETED,
            claude_session_id=None,
        )
        seeded_db.add(agent_session)
        await seeded_db.flush()
        session_id = agent_session.id

        app = create_webhook_app(default_secret="test")
        async with make_api_client(app) as ac:
            response = await ac.get(f"/api/sessions/{session_id}/history")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["event_count"] == 0
        assert "session_info" in data
        assert data["session_info"]["id"] == session_id

    async def test_session_history_with_jsonl(self, seeded_db: AsyncSession, tmp_path: Any) -> None:
        """GET /api/sessions/{id}/history parses JSONL and returns events."""
        import json
        from unittest.mock import patch

        from sqlalchemy import select

        from claudedev.core.state import (
            AgentSession,
            IssueStatus,
            Repo,
            SessionStatus,
            SessionType,
            TrackedIssue,
        )
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=887, status=IssueStatus.ENHANCED)
        seeded_db.add(issue)
        await seeded_db.flush()

        claude_sid = "test-session-abc123"
        agent_session = AgentSession(
            issue_id=issue.id,
            session_type=SessionType.ENHANCEMENT,
            status=SessionStatus.COMPLETED,
            claude_session_id=claude_sid,
        )
        seeded_db.add(agent_session)
        await seeded_db.flush()
        session_id = agent_session.id

        # Build fake JSONL content
        escaped_path = repo.local_path.replace("/", "-")
        claude_proj_dir = tmp_path / ".claude" / "projects" / escaped_path
        claude_proj_dir.mkdir(parents=True)
        jsonl_file = claude_proj_dir / f"{claude_sid}.jsonl"
        events_data = [
            {
                "type": "user",
                "timestamp": "2024-01-01T00:00:01Z",
                "message": {"content": "Please investigate this issue."},
            },
            {
                "type": "assistant",
                "timestamp": "2024-01-01T00:00:05Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "I will look into this."},
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/src/app.py"}},
                    ]
                },
            },
            {
                "type": "system",
                "timestamp": "2024-01-01T00:00:00Z",
                "message": "session_start",
            },
        ]
        with jsonl_file.open("w") as f:
            for ev in events_data:
                f.write(json.dumps(ev) + "\n")

        app = create_webhook_app(default_secret="test")

        with patch("pathlib.Path.home", return_value=tmp_path):
            async with make_api_client(app) as ac:
                response = await ac.get(f"/api/sessions/{session_id}/history")

        assert response.status_code == 200
        data = response.json()
        assert data["event_count"] == 3  # user + assistant_text + tool_use (system skipped)
        event_types = [e["type"] for e in data["events"]]
        assert "user" in event_types
        assert "assistant_text" in event_types
        assert "tool_use" in event_types
        # system event should be skipped
        assert "system" not in event_types
        user_ev = next(e for e in data["events"] if e["type"] == "user")
        assert user_ev["content"] == "Please investigate this issue."
        tool_ev = next(e for e in data["events"] if e["type"] == "tool_use")
        assert tool_ev["tool_name"] == "Read"


class TestIssueActionEndpoints:
    """Tests for POST /api/issues/{id}/enhance and /api/issues/{id}/implement."""

    async def test_enhance_new_issue(self, seeded_db: AsyncSession) -> None:
        """POST /api/issues/{id}/enhance on a NEW issue returns 200 dispatched."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=999, status=IssueStatus.NEW)
        seeded_db.add(issue)
        await seeded_db.flush()
        issue_id = issue.id

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        mock_orchestrator = MagicMock()
        mock_orchestrator.dispatch_enhance.return_value = "issue:test/repo#999"
        app.state.orchestrator = mock_orchestrator

        async with make_api_client(app) as ac:
            response = await ac.post(f"/api/issues/{issue_id}/enhance")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dispatched"
        assert data["action"] == "enhance"
        mock_orchestrator.dispatch_enhance.assert_called_once_with("test/repo", 999)

    async def test_enhance_non_new_issue_returns_409(self, seeded_db: AsyncSession) -> None:
        """POST /api/issues/{id}/enhance on ENHANCED issue returns 409."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=998, status=IssueStatus.ENHANCED)
        seeded_db.add(issue)
        await seeded_db.flush()
        issue_id = issue.id

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        app.state.orchestrator = MagicMock()

        async with make_api_client(app) as ac:
            response = await ac.post(f"/api/issues/{issue_id}/enhance")

        assert response.status_code == 409
        assert "Cannot enhance" in response.json()["error"]

    async def test_enhance_not_found_returns_404(self, seeded_db: AsyncSession) -> None:
        """POST /api/issues/99999/enhance returns 404."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        app.state.orchestrator = MagicMock()

        async with make_api_client(app) as ac:
            response = await ac.post("/api/issues/99999/enhance")

        assert response.status_code == 404

    async def test_implement_enhanced_issue(self, seeded_db: AsyncSession) -> None:
        """POST /api/issues/{id}/implement on ENHANCED issue returns 200."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=997, status=IssueStatus.ENHANCED)
        seeded_db.add(issue)
        await seeded_db.flush()
        issue_id = issue.id

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        mock_orchestrator = MagicMock()
        mock_orchestrator.dispatch_implement.return_value = "implement:test/repo#997"
        app.state.orchestrator = mock_orchestrator

        async with make_api_client(app) as ac:
            response = await ac.post(f"/api/issues/{issue_id}/implement")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "dispatched"
        assert data["action"] == "implement"
        mock_orchestrator.dispatch_implement.assert_called_once_with("test/repo", 997)

    async def test_implement_done_issue_returns_409(self, seeded_db: AsyncSession) -> None:
        """POST /api/issues/{id}/implement on DONE issue returns 409."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=996, status=IssueStatus.DONE)
        seeded_db.add(issue)
        await seeded_db.flush()
        issue_id = issue.id

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        app.state.orchestrator = MagicMock()

        async with make_api_client(app) as ac:
            response = await ac.post(f"/api/issues/{issue_id}/implement")

        assert response.status_code == 409
        assert "Cannot implement" in response.json()["error"]

    async def test_no_orchestrator_returns_503(self, seeded_db: AsyncSession) -> None:
        """POST without orchestrator on app.state returns 503."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        # Don't set app.state.orchestrator — it defaults to None

        async with make_api_client(app) as ac:
            response = await ac.post("/api/issues/1/enhance")

        assert response.status_code == 503
        assert "Orchestrator not available" in response.json()["error"]

    async def test_dedup_active_task_returns_409(self, seeded_db: AsyncSession) -> None:
        """Second POST while first is active returns 409."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=995, status=IssueStatus.NEW)
        seeded_db.add(issue)
        await seeded_db.flush()
        await seeded_db.commit()
        issue_id = issue.id

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        mock_orchestrator = MagicMock()
        # First call returns a task key; second returns None (dedup)
        mock_orchestrator.dispatch_enhance.side_effect = [
            "issue:test/repo#995",
            None,
        ]
        app.state.orchestrator = mock_orchestrator

        async with make_api_client(app) as ac:
            resp1 = await ac.post(f"/api/issues/{issue_id}/enhance")
            resp2 = await ac.post(f"/api/issues/{issue_id}/enhance")

        assert resp1.status_code == 200
        assert resp2.status_code == 409
        assert "already being processed" in resp2.json()["error"]


class TestDashboardAuth:
    """Tests for dashboard API token authentication."""

    async def test_api_endpoint_without_token_returns_401(self, seeded_db: AsyncSession) -> None:
        """GET /api/projects without dashboard token returns 401."""
        from httpx import ASGITransport

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/projects")
        assert response.status_code == 401

    async def test_api_endpoint_with_wrong_token_returns_401(self, seeded_db: AsyncSession) -> None:
        """GET /api/projects with wrong dashboard token returns 401."""
        from httpx import ASGITransport

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/projects",
                headers={"X-Dashboard-Token": "wrong-token"},
            )
        assert response.status_code == 401

    async def test_api_endpoint_with_valid_token_succeeds(self, seeded_db: AsyncSession) -> None:
        """GET /api/projects with valid dashboard token returns 200."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        async with make_api_client(app) as ac:
            response = await ac.get("/api/projects")
        assert response.status_code == 200

    async def test_health_endpoint_no_token_required(self, seeded_db: AsyncSession) -> None:
        """GET /health does not require dashboard token."""
        from httpx import ASGITransport

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")
        assert response.status_code == 200

    async def test_webhook_endpoint_no_token_required(self, seeded_db: AsyncSession) -> None:
        """POST /webhook does not require dashboard token (uses HMAC instead)."""
        from httpx import ASGITransport

        from claudedev.github.webhook_server import create_webhook_app
        from tests.conftest import TEST_WEBHOOK_SECRET, make_signature

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        body = b'{"action":"ping"}'
        sig = make_signature(body)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": sig,
                },
            )
        assert response.status_code == 200
