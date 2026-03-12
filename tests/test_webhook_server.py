"""Tests for the FastAPI webhook server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

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

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/projects")
        assert response.status_code == 401

    async def test_api_endpoint_with_wrong_token_returns_401(self, seeded_db: AsyncSession) -> None:
        """GET /api/projects with wrong dashboard token returns 401."""

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

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/health")
        assert response.status_code == 200

    async def test_api_endpoint_with_valid_cookie_succeeds(self, seeded_db: AsyncSession) -> None:
        """GET /api/projects with valid _claudedev_dash cookie returns 200."""

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.cookies.set("_claudedev_dash", app.state.dashboard_token)
            response = await ac.get("/api/projects")
        assert response.status_code == 200

    async def test_api_endpoint_with_wrong_cookie_returns_401(
        self, seeded_db: AsyncSession
    ) -> None:
        """GET /api/projects with wrong _claudedev_dash cookie returns 401."""

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.cookies.set("_claudedev_dash", "wrong-cookie-value")
            response = await ac.get("/api/projects")
        assert response.status_code == 401

    async def test_dashboard_page_sets_auth_cookie(self, seeded_db: AsyncSession) -> None:
        """GET /dashboard/ sets _claudedev_dash HttpOnly cookie."""

        from claudedev.github.webhook_server import create_webhook_app
        from claudedev.ui.dashboard import router as dashboard_router

        app = create_webhook_app(default_secret="test")
        app.include_router(dashboard_router)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/dashboard/")
        assert response.status_code == 200
        cookie = response.cookies.get("_claudedev_dash")
        assert cookie == app.state.dashboard_token

    async def test_dashboard_cookie_enables_api_access(self, seeded_db: AsyncSession) -> None:
        """Browser flow: GET /dashboard/ sets cookie, then /api/* works."""

        from claudedev.github.webhook_server import create_webhook_app
        from claudedev.ui.dashboard import router as dashboard_router

        app = create_webhook_app(default_secret="test")
        app.include_router(dashboard_router)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Visit dashboard — gets cookie
            dash_resp = await ac.get("/dashboard/")
            assert dash_resp.status_code == 200
            # httpx persists cookies across requests in the same client
            api_resp = await ac.get("/api/projects")
        assert api_resp.status_code == 200

    async def test_webhook_endpoint_no_token_required(self, seeded_db: AsyncSession) -> None:
        """POST /webhook does not require dashboard token (uses HMAC instead)."""

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

    async def test_options_requires_auth(self, seeded_db: AsyncSession) -> None:
        """OPTIONS /api/projects requires auth like any other /api/ request."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.options("/api/projects")
        assert response.status_code == 401

    async def test_non_api_paths_no_auth_required(self, seeded_db: AsyncSession) -> None:
        """Non-/api/ paths should not require dashboard auth."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # /health is a non-/api/ path
            response = await ac.get("/health")
        assert response.status_code == 200

    async def test_rotated_token_is_rejected(self, seeded_db: AsyncSession) -> None:
        """After token rotation (app restart), old tokens are rejected."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="test")
        old_token = app.state.dashboard_token

        # Simulate token rotation by overwriting with a new value
        import secrets

        app.state.dashboard_token = secrets.token_urlsafe(32)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/projects",
                headers={"X-Dashboard-Token": old_token},
            )
        assert response.status_code == 401


def _make_pr_close_payload(pr_number: int, *, merged: bool = False) -> dict[str, Any]:
    """Build a complete pull_request.closed webhook payload for testing."""
    return {
        "action": "closed",
        "number": pr_number,
        "pull_request": {
            "number": pr_number,
            "title": f"PR #{pr_number}",
            "body": "Test PR",
            "state": "closed",
            "merged": merged,
            "html_url": f"https://github.com/test/repo/pull/{pr_number}",
            "user": {"login": "claudedev-bot", "id": 99999},
            "head": {"ref": f"claudedev/issue-{pr_number}", "sha": "abc123", "label": "test:fix"},
            "base": {"ref": "main", "sha": "def456", "label": "test:main"},
            "draft": False,
            "labels": [],
        },
        "repository": {
            "id": 99999,
            "name": "repo",
            "full_name": "test/repo",
            "private": False,
            "default_branch": "main",
            "owner": {"login": "test", "id": 11111},
        },
        "sender": {"login": "claudedev-bot", "id": 99999},
    }


class TestPRCloseHandling:
    """Tests for _handle_pr_close webhook event handling."""

    async def test_pr_merge_updates_issue_status_to_done(self, seeded_db: AsyncSession) -> None:
        """When a PR is merged, the linked TrackedIssue status becomes DONE."""
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            PRStatus,
            Repo,
            TrackedIssue,
            TrackedPR,
        )
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=100, status=IssueStatus.IN_REVIEW)
        seeded_db.add(issue)
        await seeded_db.flush()

        pr = TrackedPR(repo_id=repo.id, issue_id=issue.id, pr_number=50, status=PRStatus.OPEN)
        seeded_db.add(pr)
        await seeded_db.flush()
        await seeded_db.commit()

        payload = _make_pr_close_payload(50, merged=True)
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        async with make_api_client(app) as ac:
            response = await ac.post(
                "/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": "test-pr-merge-1",
                },
            )
        assert response.status_code == 200

        # Verify issue status updated to DONE
        # Refresh from DB to see changes committed by _handle_pr_close
        await seeded_db.refresh(issue)
        assert issue.status == IssueStatus.DONE

        # Verify PR status updated to MERGED
        await seeded_db.refresh(pr)
        assert pr.status == PRStatus.MERGED

    async def test_pr_close_with_worktree_calls_cleanup(self, seeded_db: AsyncSession) -> None:
        """PR close with worktree_path set calls WorktreeManager.cleanup_worktree."""
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            PRStatus,
            Repo,
            TrackedIssue,
            TrackedPR,
        )
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=101,
            status=IssueStatus.IN_REVIEW,
            worktree_path="/tmp/projects/repo/.worktrees/claudedev/issue-101",
        )
        seeded_db.add(issue)
        await seeded_db.flush()

        pr = TrackedPR(repo_id=repo.id, issue_id=issue.id, pr_number=51, status=PRStatus.OPEN)
        seeded_db.add(pr)
        await seeded_db.flush()
        await seeded_db.commit()

        payload = _make_pr_close_payload(51, merged=True)
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        mock_cleanup = AsyncMock(return_value=True)
        with patch(
            "claudedev.engines.worktree_manager.WorktreeManager.cleanup_worktree", mock_cleanup
        ):
            async with make_api_client(app) as ac:
                await ac.post(
                    "/webhook",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "pull_request",
                        "X-GitHub-Delivery": "test-pr-wt-1",
                    },
                )
        mock_cleanup.assert_awaited_once()

    async def test_pr_close_without_worktree_no_cleanup(self, seeded_db: AsyncSession) -> None:
        """PR close without worktree_path does not call WorktreeManager."""
        from sqlalchemy import select

        from claudedev.core.state import (
            IssueStatus,
            PRStatus,
            Repo,
            TrackedIssue,
            TrackedPR,
        )
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=102,
            status=IssueStatus.IN_REVIEW,
            worktree_path=None,
        )
        seeded_db.add(issue)
        await seeded_db.flush()

        pr = TrackedPR(repo_id=repo.id, issue_id=issue.id, pr_number=52, status=PRStatus.OPEN)
        seeded_db.add(pr)
        await seeded_db.flush()
        await seeded_db.commit()

        payload = _make_pr_close_payload(52, merged=False)
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        mock_cleanup = AsyncMock(return_value=True)
        with patch(
            "claudedev.engines.worktree_manager.WorktreeManager.cleanup_worktree", mock_cleanup
        ):
            async with make_api_client(app) as ac:
                await ac.post(
                    "/webhook",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "pull_request",
                        "X-GitHub-Delivery": "test-pr-nowt-1",
                    },
                )
        mock_cleanup.assert_not_awaited()

    async def test_pr_close_unknown_pr_handled_gracefully(self, seeded_db: AsyncSession) -> None:
        """PR close for unknown PR number does not error."""
        from claudedev.github.webhook_server import create_webhook_app

        payload = _make_pr_close_payload(99999, merged=True)
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        async with make_api_client(app) as ac:
            response = await ac.post(
                "/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "pull_request",
                    "X-GitHub-Delivery": "test-pr-unknown-1",
                },
            )
        assert response.status_code == 200


class TestIssueCloseHandling:
    """Tests for _handle_issue_close webhook event handling."""

    async def test_issue_close_updates_status_to_closed(self, seeded_db: AsyncSession) -> None:
        """When an issue is closed, TrackedIssue status becomes CLOSED."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(repo_id=repo.id, github_issue_number=200, status=IssueStatus.ENHANCED)
        seeded_db.add(issue)
        await seeded_db.flush()
        await seeded_db.commit()

        payload = {
            "action": "closed",
            "issue": {
                "number": 200,
                "title": "Test issue",
                "body": "Test body",
                "state": "closed",
                "html_url": "https://github.com/test/repo/issues/200",
                "user": {"login": "testuser", "id": 12345},
                "labels": [],
                "assignees": [],
            },
            "repository": {
                "id": 99999,
                "name": "repo",
                "full_name": "test/repo",
                "private": False,
                "default_branch": "main",
                "owner": {"login": "test", "id": 11111},
            },
            "sender": {"login": "testuser", "id": 12345},
        }
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        async with make_api_client(app) as ac:
            response = await ac.post(
                "/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "issues",
                    "X-GitHub-Delivery": "test-issue-close-1",
                },
            )
        assert response.status_code == 200

        await seeded_db.refresh(issue)
        assert issue.status == IssueStatus.CLOSED

    async def test_issue_close_with_open_pr_skips_worktree_cleanup(
        self, seeded_db: AsyncSession
    ) -> None:
        """Issue close with an open PR does not clean up the worktree."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, PRStatus, Repo, TrackedIssue, TrackedPR
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=201,
            status=IssueStatus.IN_REVIEW,
            worktree_path="/tmp/projects/repo/.worktrees/claudedev/issue-201",
        )
        seeded_db.add(issue)
        await seeded_db.flush()

        pr = TrackedPR(repo_id=repo.id, issue_id=issue.id, pr_number=60, status=PRStatus.OPEN)
        seeded_db.add(pr)
        await seeded_db.flush()
        await seeded_db.commit()

        payload = {
            "action": "closed",
            "issue": {
                "number": 201,
                "title": "Test",
                "body": "",
                "state": "closed",
                "html_url": "https://github.com/test/repo/issues/201",
                "user": {"login": "testuser", "id": 12345},
                "labels": [],
                "assignees": [],
            },
            "repository": {
                "id": 99999,
                "name": "repo",
                "full_name": "test/repo",
                "private": False,
                "default_branch": "main",
                "owner": {"login": "test", "id": 11111},
            },
            "sender": {"login": "testuser", "id": 12345},
        }
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        mock_cleanup = AsyncMock(return_value=True)
        with patch(
            "claudedev.engines.worktree_manager.WorktreeManager.cleanup_worktree", mock_cleanup
        ):
            async with make_api_client(app) as ac:
                await ac.post(
                    "/webhook",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "test-issue-openpr-1",
                    },
                )
        mock_cleanup.assert_not_awaited()

        # But issue status should still be CLOSED
        await seeded_db.refresh(issue)
        assert issue.status == IssueStatus.CLOSED
        # Worktree path should still be set (not cleaned)
        assert issue.worktree_path is not None

    async def test_issue_close_without_pr_cleans_worktree(self, seeded_db: AsyncSession) -> None:
        """Issue close without a PR cleans up the worktree."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        issue = TrackedIssue(
            repo_id=repo.id,
            github_issue_number=202,
            status=IssueStatus.IMPLEMENTING,
            worktree_path="/tmp/projects/repo/.worktrees/claudedev/issue-202",
        )
        seeded_db.add(issue)
        await seeded_db.flush()
        await seeded_db.commit()

        payload = {
            "action": "closed",
            "issue": {
                "number": 202,
                "title": "Test",
                "body": "",
                "state": "closed",
                "html_url": "https://github.com/test/repo/issues/202",
                "user": {"login": "testuser", "id": 12345},
                "labels": [],
                "assignees": [],
            },
            "repository": {
                "id": 99999,
                "name": "repo",
                "full_name": "test/repo",
                "private": False,
                "default_branch": "main",
                "owner": {"login": "test", "id": 11111},
            },
            "sender": {"login": "testuser", "id": 12345},
        }
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        mock_cleanup = AsyncMock(return_value=True)
        with patch(
            "claudedev.engines.worktree_manager.WorktreeManager.cleanup_worktree", mock_cleanup
        ):
            async with make_api_client(app) as ac:
                await ac.post(
                    "/webhook",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": sig,
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "test-issue-nowt-1",
                    },
                )
        mock_cleanup.assert_awaited_once()

    async def test_issue_close_unknown_issue_handled_gracefully(
        self, seeded_db: AsyncSession
    ) -> None:
        """Issue close for unknown issue number does not error."""
        from claudedev.github.webhook_server import create_webhook_app

        payload = {
            "action": "closed",
            "issue": {
                "number": 99999,
                "title": "Unknown",
                "body": "",
                "state": "closed",
                "html_url": "https://github.com/test/repo/issues/99999",
                "user": {"login": "testuser", "id": 12345},
                "labels": [],
                "assignees": [],
            },
            "repository": {
                "id": 99999,
                "name": "repo",
                "full_name": "test/repo",
                "private": False,
                "default_branch": "main",
                "owner": {"login": "test", "id": 11111},
            },
            "sender": {"login": "testuser", "id": 12345},
        }
        body = json.dumps(payload).encode()
        sig = make_signature(body)

        app = create_webhook_app(default_secret=TEST_WEBHOOK_SECRET)
        async with make_api_client(app) as ac:
            response = await ac.post(
                "/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                    "X-GitHub-Event": "issues",
                    "X-GitHub-Delivery": "test-issue-unknown-1",
                },
            )
        assert response.status_code == 200


class TestApiSyncEndpoint:
    """Tests for POST /api/sync — full GitHub issue sync."""

    def _make_gh_issue(self, number: int, state: str = "open") -> dict[str, Any]:
        return {
            "number": number,
            "title": f"Issue {number}",
            "state": state,
            "user": {"login": "u", "id": 1},
            "labels": [],
            "assignees": [],
        }

    async def test_sync_no_gh_client_returns_503(self) -> None:
        """Without gh_client on app.state the endpoint returns 503."""
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app()
        # gh_client is NOT set on app.state
        async with make_api_client(app) as ac:
            response = await ac.post("/api/sync")
        assert response.status_code == 503
        assert "error" in response.json()

    async def test_sync_no_repos_returns_zero_counts(self) -> None:
        """When no repos are tracked, returns new_issues=0 and closed_issues=0."""
        from claudedev.core.state import close_db, init_db
        from claudedev.github.gh_client import GHClient
        from claudedev.github.webhook_server import create_webhook_app

        await init_db("sqlite+aiosqlite:///:memory:")
        try:
            app = create_webhook_app()
            gh = GHClient()
            gh.list_issues = AsyncMock(return_value=[])
            app.state.gh_client = gh

            async with make_api_client(app) as ac:
                response = await ac.post("/api/sync")

            assert response.status_code == 200
            data = response.json()
            assert data["new_issues"] == 0
            assert data["closed_issues"] == 0
        finally:
            await close_db()

    async def test_sync_discovers_new_issues(self, seeded_db: Any) -> None:
        """New issues on GitHub are inserted as TrackedIssue records."""
        from sqlalchemy import select

        from claudedev.core.state import TrackedIssue, get_session
        from claudedev.github.gh_client import GHClient
        from claudedev.github.models import GitHubIssue
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app()
        gh = GHClient()
        gh_issues = [GitHubIssue.model_validate(self._make_gh_issue(n)) for n in (10, 20, 30)]
        gh.list_issues = AsyncMock(return_value=gh_issues)
        app.state.gh_client = gh

        async with make_api_client(app) as ac:
            response = await ac.post("/api/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["new_issues"] == 3
        assert data["closed_issues"] == 0

        # Verify they were actually persisted
        async with get_session() as session:
            result = await session.execute(select(TrackedIssue))
            tracked = result.scalars().all()
        assert len(tracked) == 3
        assert {t.github_issue_number for t in tracked} == {10, 20, 30}

    async def test_sync_idempotent_no_duplicates(self, seeded_db: Any) -> None:
        """Running sync twice does not create duplicate TrackedIssue records."""
        from sqlalchemy import select

        from claudedev.core.state import TrackedIssue, get_session
        from claudedev.github.gh_client import GHClient
        from claudedev.github.models import GitHubIssue
        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app()
        gh = GHClient()
        gh_issues = [GitHubIssue.model_validate(self._make_gh_issue(5))]
        gh.list_issues = AsyncMock(return_value=gh_issues)
        app.state.gh_client = gh

        async with make_api_client(app) as ac:
            await ac.post("/api/sync")
            response = await ac.post("/api/sync")

        data = response.json()
        assert data["new_issues"] == 0  # second run finds nothing new

        async with get_session() as session:
            result = await session.execute(select(TrackedIssue))
            tracked = result.scalars().all()
        assert len(tracked) == 1

    async def test_sync_marks_closed_issues(self, seeded_db: Any) -> None:
        """Issues no longer open on GitHub are marked CLOSED in the DB."""
        from sqlalchemy import select

        from claudedev.core.state import IssueStatus, Repo, TrackedIssue, get_session
        from claudedev.github.gh_client import GHClient
        from claudedev.github.models import GitHubIssue
        from claudedev.github.webhook_server import create_webhook_app

        # Pre-seed a tracked issue as NEW
        async with get_session() as session:
            result = await session.execute(select(Repo))
            repo = result.scalars().first()
            assert repo is not None
            tracked = TrackedIssue(
                repo_id=repo.id,
                github_issue_number=99,
            )
            session.add(tracked)
            await session.commit()
            tracked_id = tracked.id

        app = create_webhook_app()
        gh = GHClient()
        # GitHub says no open issues (99 was closed)
        gh.list_issues = AsyncMock(return_value=[])
        # get_issue returns a closed issue
        closed_gh_issue = GitHubIssue.model_validate(self._make_gh_issue(99, state="closed"))
        gh.get_issue = AsyncMock(return_value=closed_gh_issue)
        app.state.gh_client = gh

        async with make_api_client(app) as ac:
            response = await ac.post("/api/sync")

        assert response.status_code == 200
        data = response.json()
        assert data["closed_issues"] == 1

        async with get_session() as session:
            result = await session.execute(
                select(TrackedIssue).where(TrackedIssue.id == tracked_id)
            )
            updated = result.scalar_one()
        assert updated.status == IssueStatus.CLOSED

    async def test_sync_requires_auth(self) -> None:
        """POST /api/sync is protected by dashboard auth middleware."""
        from httpx import ASGITransport, AsyncClient

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/sync")
        assert response.status_code == 401
        assert response.json()["error"] == "Unauthorized"
