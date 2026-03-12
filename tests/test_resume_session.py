"""Tests for ClaudeSDKClient.resume_session -- session resume via CLI."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudedev.auth import AuthManager, AuthMode
from claudedev.integrations.claude_sdk import ClaudeSDKClient


@pytest.fixture
def cli_client() -> ClaudeSDKClient:
    auth = MagicMock(spec=AuthManager)
    auth.get_auth_mode.return_value = AuthMode.CLI
    auth.claude_code_path = "/usr/bin/claude"
    return ClaudeSDKClient(auth)


class TestResumeSession:
    async def test_builds_correct_command(self, cli_client: ClaudeSDKClient) -> None:
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[
                b'{"type":"result","stop_reason":"end_turn","result":"Done"}\n',
                b"",
            ]
        )
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            chunks = []
            async for chunk in cli_client.resume_session(
                session_id="sess-abc-123",
                prompt="Use approach A",
                cwd="/tmp/worktree",
            ):
                chunks.append(chunk)

            call_args = mock_exec.call_args[0]
            assert "--resume" in call_args
            assert "sess-abc-123" in call_args
            assert "-p" in call_args
            assert "Use approach A" in call_args

    async def test_streams_output(self, cli_client: ClaudeSDKClient) -> None:
        lines = [
            b'{"type":"assistant","message":{"content":[{"type":"text","text":"OK"}]}}\n',
            b'{"type":"result","stop_reason":"end_turn","result":"Done"}\n',
            b"",
        ]
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=lines)
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            chunks = []
            async for chunk in cli_client.resume_session(
                session_id="sess-123",
                prompt="Continue",
                cwd="/tmp",
            ):
                chunks.append(chunk)

        assert len(chunks) == 2

    async def test_uses_stream_json_format(self, cli_client: ClaudeSDKClient) -> None:
        mock_proc = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(side_effect=[b"", b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            async for _ in cli_client.resume_session("s", "p", "/tmp"):
                pass

            call_args = mock_exec.call_args[0]
            assert "--output-format" in call_args
            assert "stream-json" in call_args
            assert "--verbose" in call_args
