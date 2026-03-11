"""Tests for test credential discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from claudedev.core.credentials import (
    _is_credential_key,
    _parse_env_file,
    discover_test_credentials,
    mask_credential_value,
)


class TestIsCredentialKey:
    def test_exact_patterns(self) -> None:
        assert _is_credential_key("TEST_USER") is True
        assert _is_credential_key("TEST_PASS") is True
        assert _is_credential_key("ADMIN_EMAIL") is True
        assert _is_credential_key("E2E_PASSWORD") is True
        assert _is_credential_key("LOGIN_EMAIL") is True

    def test_role_plus_suffix(self) -> None:
        assert _is_credential_key("STAGING_PASSWORD") is True
        assert _is_credential_key("DEV_TOKEN") is True
        assert _is_credential_key("QA_USERNAME") is True
        assert _is_credential_key("DEMO_SECRET") is True

    def test_rejects_non_credential_keys(self) -> None:
        assert _is_credential_key("DATABASE_URL") is False
        assert _is_credential_key("REDIS_HOST") is False
        assert _is_credential_key("PORT") is False
        assert _is_credential_key("NODE_ENV") is False
        assert _is_credential_key("API_URL") is False

    def test_excludes_infrastructure_secrets(self) -> None:
        assert _is_credential_key("DB_PASSWORD") is False
        assert _is_credential_key("POSTGRES_PASSWORD") is False
        assert _is_credential_key("AWS_SECRET_ACCESS_KEY") is False
        assert _is_credential_key("GITHUB_TOKEN") is False

    def test_case_insensitive(self) -> None:
        assert _is_credential_key("test_user") is True
        assert _is_credential_key("Test_Pass") is True


class TestParseEnvFile:
    def test_parses_simple_env(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_USER=admin@test.com\nTEST_PASS=secret123\n")
        result = _parse_env_file(env_file)
        assert result == {"TEST_USER": "admin@test.com", "TEST_PASS": "secret123"}

    def test_strips_quotes(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_USER=\"quoted@test.com\"\nTEST_PASS='single'\n")
        result = _parse_env_file(env_file)
        assert result == {"TEST_USER": "quoted@test.com", "TEST_PASS": "single"}

    def test_skips_comments_and_empty(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# Comment\n\nTEST_USER=user\n  # Another comment\n")
        result = _parse_env_file(env_file)
        assert result == {"TEST_USER": "user"}

    def test_ignores_non_credential_vars(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_URL=postgres://...\nPORT=3000\nTEST_USER=user\n")
        result = _parse_env_file(env_file)
        assert result == {"TEST_USER": "user"}

    def test_empty_values_skipped(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_USER=\nTEST_PASS=secret\n")
        result = _parse_env_file(env_file)
        assert result == {"TEST_PASS": "secret"}

    def test_missing_file(self, tmp_path: Path) -> None:
        result = _parse_env_file(tmp_path / "nonexistent")
        assert result == {}


class TestDiscoverTestCredentials:
    def test_discovers_from_env(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("TEST_USER=user@test.com\nTEST_PASS=pass123\n")
        result = discover_test_credentials(str(tmp_path))
        assert result == {"TEST_USER": "user@test.com", "TEST_PASS": "pass123"}

    def test_env_local_overrides_env(self, tmp_path: Path) -> None:
        (tmp_path / ".env").write_text("TEST_USER=env_user\nTEST_PASS=env_pass\n")
        (tmp_path / ".env.local").write_text("TEST_USER=local_user\n")
        result = discover_test_credentials(str(tmp_path))
        assert result["TEST_USER"] == "local_user"
        assert result["TEST_PASS"] == "env_pass"

    def test_no_env_files(self, tmp_path: Path) -> None:
        result = discover_test_credentials(str(tmp_path))
        assert result == {}

    def test_invalid_path(self) -> None:
        result = discover_test_credentials("/nonexistent/path/12345")
        assert result == {}


class TestMaskCredentialValue:
    def test_shows_user_email(self) -> None:
        assert mask_credential_value("TEST_USER", "admin@test.com") == "admin@test.com"
        assert mask_credential_value("LOGIN_EMAIL", "user@example.com") == "user@example.com"

    def test_masks_password(self) -> None:
        masked = mask_credential_value("TEST_PASS", "secret123")
        assert masked != "secret123"
        assert "***" in masked

    def test_masks_short_value(self) -> None:
        assert mask_credential_value("TEST_PASS", "ab") == "***"

    def test_masks_token(self) -> None:
        masked = mask_credential_value("DEV_TOKEN", "tok_1234567890")
        assert "***" in masked


class TestCredentialEndpoints:
    async def test_get_credentials_empty(self, seeded_db: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import select

        from claudedev.core.state import Repo
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        hdrs = {"X-Dashboard-Token": app.state.dashboard_token}
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            response = await ac.get(f"/api/repos/{repo.id}/credentials")
        assert response.status_code == 200
        assert response.json()["credentials"] == {}

    async def test_set_credentials(self, seeded_db: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import select

        from claudedev.core.state import Repo
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        hdrs = {"X-Dashboard-Token": app.state.dashboard_token}
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            response = await ac.post(
                f"/api/repos/{repo.id}/credentials",
                json={"credentials": {"TEST_USER": "admin@test.com", "TEST_PASS": "secret123"}},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "TEST_USER" in data["credentials"]

    async def test_clear_credentials(self, seeded_db: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import select

        from claudedev.core.state import Repo
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        hdrs = {"X-Dashboard-Token": app.state.dashboard_token}
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            # Set first
            await ac.post(
                f"/api/repos/{repo.id}/credentials",
                json={"credentials": {"TEST_USER": "user"}},
            )
            # Then clear
            response = await ac.delete(f"/api/repos/{repo.id}/credentials")
        assert response.status_code == 200
        assert response.json()["status"] == "cleared"

        # Verify cleared
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            response = await ac.get(f"/api/repos/{repo.id}/credentials")
        assert response.json()["credentials"] == {}

    async def test_get_credentials_not_found(self, seeded_db: Any) -> None:
        from httpx import ASGITransport, AsyncClient

        from claudedev.github.webhook_server import create_webhook_app

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        hdrs = {"X-Dashboard-Token": app.state.dashboard_token}
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            response = await ac.get("/api/repos/99999/credentials")
        assert response.status_code == 404

    async def test_discover_credentials(self, seeded_db: Any, tmp_path: Path) -> None:
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import select

        from claudedev.core.state import Repo
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()
        # Set local_path to tmp_path with an .env file
        repo.local_path = str(tmp_path)
        (tmp_path / ".env").write_text("TEST_USER=admin@test.com\nTEST_PASS=secret123\n")
        await seeded_db.commit()

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        hdrs = {"X-Dashboard-Token": app.state.dashboard_token}
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            response = await ac.post(f"/api/repos/{repo.id}/credentials/discover")
        assert response.status_code == 200
        data = response.json()
        assert data["discovered_count"] >= 1
        assert "TEST_USER" in data.get("credentials", {})

    async def test_set_credentials_validation(self, seeded_db: Any) -> None:
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy import select

        from claudedev.core.state import Repo
        from claudedev.github.webhook_server import create_webhook_app

        result = await seeded_db.execute(select(Repo))
        repo = result.scalar_one()

        app = create_webhook_app(default_secret="")
        transport = ASGITransport(app=app)
        hdrs = {"X-Dashboard-Token": app.state.dashboard_token}
        async with AsyncClient(transport=transport, base_url="http://test", headers=hdrs) as ac:
            # Invalid key format
            response = await ac.post(
                f"/api/repos/{repo.id}/credentials",
                json={"credentials": {"bad key": "value"}},
            )
        assert response.status_code == 422
