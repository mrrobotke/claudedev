"""Tests for ClaudeBridge — Anthropic API integration layer."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from claudedev.brain.config import BrainConfig
from claudedev.brain.integration.claude_bridge import ClaudeBridge, ClaudeResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config(**overrides: Any) -> BrainConfig:
    """Return a minimal BrainConfig with sensible test defaults."""
    kwargs: dict[str, Any] = {
        "project_path": "/tmp/test_project",
        "claude_model": "claude-test-model",
        "max_retries": 3,
    }
    kwargs.update(overrides)
    return BrainConfig(**kwargs)


def make_text_block(text: str) -> MagicMock:
    """Build a mock text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_tool_block(name: str) -> MagicMock:
    """Build a mock tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    return block


def make_usage(input_tokens: int = 10, output_tokens: int = 20) -> MagicMock:
    """Build a mock Usage object."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def make_response(
    content_blocks: list[MagicMock] | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> MagicMock:
    """Build a mock anthropic Message response."""
    response = MagicMock()
    response.content = content_blocks if content_blocks is not None else [make_text_block("hello")]
    response.stop_reason = stop_reason
    response.usage = make_usage(input_tokens=input_tokens, output_tokens=output_tokens)
    return response


def make_dummy_request() -> httpx.Request:
    return httpx.Request("GET", "http://test")


def make_dummy_response(status: int = 429) -> httpx.Response:
    return httpx.Response(status, request=make_dummy_request())


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestClaudeBridgeConstruction:
    def test_creates_with_config(self) -> None:
        """Bridge should instantiate without error given a valid config."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_anthropic.AsyncAnthropic.return_value = MagicMock()
            config = make_config()
            bridge = ClaudeBridge(config)
            assert bridge is not None

    def test_uses_model_from_config(self) -> None:
        """Bridge should store the model name from BrainConfig."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_anthropic.AsyncAnthropic.return_value = MagicMock()
            config = make_config(claude_model="claude-opus-4")
            bridge = ClaudeBridge(config)
            assert bridge._model == "claude-opus-4"

    def test_uses_max_retries_from_config(self) -> None:
        """Bridge should store max_retries from BrainConfig."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_anthropic.AsyncAnthropic.return_value = MagicMock()
            config = make_config(max_retries=5)
            bridge = ClaudeBridge(config)
            assert bridge._max_retries == 5

    def test_instantiates_anthropic_client(self) -> None:
        """Bridge should call anthropic.AsyncAnthropic() during construction."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            ClaudeBridge(make_config())
            mock_anthropic.AsyncAnthropic.assert_called_once()


# ---------------------------------------------------------------------------
# execute_task — happy path
# ---------------------------------------------------------------------------


class TestExecuteTaskSuccess:
    async def test_basic_execution_returns_claude_result(self) -> None:
        """A successful API call returns a ClaudeResult with success=True."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response())

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(
                task="do something",
                system_prompt="you are helpful",
            )

            assert isinstance(result, ClaudeResult)
            assert result.success is True

    async def test_system_prompt_passed_to_api(self) -> None:
        """The system_prompt argument must be forwarded to messages.create."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response())

            bridge = ClaudeBridge(make_config())
            await bridge.execute_task(task="task", system_prompt="my system prompt")

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["system"] == "my system prompt"

    async def test_model_passed_to_api(self) -> None:
        """The model ID from config must be forwarded to messages.create."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response())

            bridge = ClaudeBridge(make_config(claude_model="claude-specific-model"))
            await bridge.execute_task(task="task", system_prompt="sys")

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] == "claude-specific-model"

    async def test_result_includes_duration(self) -> None:
        """The returned ClaudeResult must have a positive duration_ms."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response())

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.duration_ms >= 0.0

    async def test_text_content_extracted(self) -> None:
        """Text blocks in the response should be joined into result.content."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(
                content_blocks=[make_text_block("Hello"), make_text_block(" World")],
            ))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.content == "Hello World"

    async def test_tool_use_extracted(self) -> None:
        """Tool-use blocks should be captured in result.tool_use_history."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(
                content_blocks=[
                    make_tool_block("read_file"),
                    make_tool_block("write_file"),
                    make_text_block("done"),
                ],
            ))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.tool_use_history == ["read_file", "write_file"]

    async def test_stop_reason_captured(self) -> None:
        """The stop_reason from the response should appear in ClaudeResult."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(stop_reason="max_tokens"))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.stop_reason == "max_tokens"

    async def test_token_counts_captured(self) -> None:
        """Input and output token counts must be stored in ClaudeResult."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(
                input_tokens=100, output_tokens=200
            ))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.input_tokens == 100
            assert result.output_tokens == 200

    async def test_execute_task_only_requires_task_and_system_prompt(self) -> None:
        """execute_task works with only task and system_prompt arguments."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response())

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="t", system_prompt="s")

            assert result.success is True


# ---------------------------------------------------------------------------
# execute_task — error handling
# ---------------------------------------------------------------------------


class TestExecuteTaskErrors:
    async def test_api_error_returns_failed_result(self) -> None:
        """anthropic.APIError must produce success=False, never raise."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            api_error = real_anthropic.APIError(
                message="internal server error",
                request=make_dummy_request(),
                body=None,
            )
            mock_client.messages.create = AsyncMock(side_effect=api_error)

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is False
            assert result.error is not None
            assert "internal server error" in result.error

    async def test_api_error_result_has_empty_content(self) -> None:
        """A failed ClaudeResult due to APIError should have empty content."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            mock_client.messages.create = AsyncMock(side_effect=real_anthropic.APIError(
                message="boom", request=make_dummy_request(), body=None
            ))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.content == ""
            assert result.input_tokens == 0
            assert result.output_tokens == 0

    async def test_api_timeout_error_returns_failed_result(self) -> None:
        """anthropic.APITimeoutError must produce success=False with 'timeout' in error."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            timeout_error = real_anthropic.APITimeoutError(request=make_dummy_request())
            mock_client.messages.create = AsyncMock(side_effect=timeout_error)

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is False
            assert result.error is not None
            assert "timeout" in result.error.lower()

    async def test_api_timeout_never_raises(self) -> None:
        """execute_task must not raise even on APITimeoutError."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            mock_client.messages.create = AsyncMock(side_effect=real_anthropic.APITimeoutError(
                request=make_dummy_request()
            ))

            bridge = ClaudeBridge(make_config())
            # Should not raise
            result = await bridge.execute_task(task="task", system_prompt="sys")
            assert isinstance(result, ClaudeResult)

    async def test_rate_limit_retries_then_succeeds(self) -> None:
        """RateLimitError on first attempt should retry and return success."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            rate_error = real_anthropic.RateLimitError(
                message="rate limited",
                response=make_dummy_response(429),
                body=None,
            )
            good_response = make_response()
            mock_client.messages.create = AsyncMock(side_effect=[rate_error, good_response])

            bridge = ClaudeBridge(make_config(max_retries=3))

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is True
            assert mock_sleep.called

    async def test_rate_limit_retries_uses_exponential_backoff(self) -> None:
        """Retry wait time should increase with each attempt."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            rate_error = real_anthropic.RateLimitError(
                message="rate limited",
                response=make_dummy_response(429),
                body=None,
            )
            # Fail twice, then succeed
            good_response = make_response()
            mock_client.messages.create = AsyncMock(side_effect=[rate_error, rate_error, good_response])

            bridge = ClaudeBridge(make_config(max_retries=3))
            sleep_calls: list[float] = []

            async def capture_sleep(secs: float) -> None:
                sleep_calls.append(secs)

            with patch("asyncio.sleep", side_effect=capture_sleep):
                result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is True
            assert len(sleep_calls) == 2
            # Second wait should be >= first wait (exponential backoff)
            assert sleep_calls[1] >= sleep_calls[0]

    async def test_rate_limit_exhausted_returns_failed_result(self) -> None:
        """When all retry attempts are exhausted, return success=False."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            rate_error = real_anthropic.RateLimitError(
                message="rate limited",
                response=make_dummy_response(429),
                body=None,
            )
            # Always fail with rate limit
            mock_client.messages.create = AsyncMock(side_effect=rate_error)

            bridge = ClaudeBridge(make_config(max_retries=2))

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is False
            assert result.error is not None

    async def test_rate_limit_one_retry_sleeps_once_then_fails(self) -> None:
        """With max_retries=1, one sleep occurs then failure is returned."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            rate_error = real_anthropic.RateLimitError(
                message="rate limited",
                response=make_dummy_response(429),
                body=None,
            )
            mock_client.messages.create = AsyncMock(side_effect=rate_error)

            bridge = ClaudeBridge(make_config(max_retries=1))

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is False
            assert result.error is not None
            mock_sleep.assert_called_once()

    async def test_rate_limit_zero_retries_fails_immediately_no_sleep(self) -> None:
        """With max_retries=0, a RateLimitError returns failure without calling sleep."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError

            rate_error = real_anthropic.RateLimitError(
                message="rate limited",
                response=make_dummy_response(429),
                body=None,
            )
            mock_client.messages.create = AsyncMock(side_effect=rate_error)

            bridge = ClaudeBridge(make_config(max_retries=0))

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is False
            assert result.error is not None
            mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestClaudeBridgeEdgeCases:
    async def test_empty_response_content_returns_empty_string(self) -> None:
        """An API response with no content blocks yields content=''."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(content_blocks=[]))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is True
            assert result.content == ""
            assert result.tool_use_history == []

    async def test_very_long_task_does_not_crash(self) -> None:
        """A very long task string should not cause an exception."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response())

            bridge = ClaudeBridge(make_config())
            long_task = "x" * 100_000
            result = await bridge.execute_task(task=long_task, system_prompt="sys")

            assert result.success is True

    async def test_none_stop_reason_normalised_to_empty_string(self) -> None:
        """If stop_reason is None in the API response, result should have ''."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(stop_reason=None))  # type: ignore[arg-type]

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.stop_reason == ""

    async def test_mixed_content_blocks(self) -> None:
        """Mixed text and tool blocks: text joined, tools listed separately."""
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=make_response(
                content_blocks=[
                    make_text_block("Starting task. "),
                    make_tool_block("bash"),
                    make_text_block("Done."),
                    make_tool_block("read_file"),
                ],
            ))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.content == "Starting task. Done."
            assert result.tool_use_history == ["bash", "read_file"]


class TestClaudeBridgeUnexpectedErrors:
    async def test_unexpected_exception_returns_failed_result(self) -> None:
        with patch("claudedev.brain.integration.claude_bridge.anthropic") as mock_anthropic:
            import anthropic as real_anthropic

            mock_client = MagicMock()
            mock_anthropic.AsyncAnthropic.return_value = mock_client
            mock_anthropic.APIError = real_anthropic.APIError
            mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
            mock_anthropic.RateLimitError = real_anthropic.RateLimitError
            mock_client.messages.create = AsyncMock(side_effect=AttributeError("unexpected"))

            bridge = ClaudeBridge(make_config())
            result = await bridge.execute_task(task="task", system_prompt="sys")

            assert result.success is False
            assert "AttributeError" in (result.error or "")


class TestClaudeBridgeAPIKeyValidation:
    """API key must be validated at construction time."""

    async def test_missing_api_key_raises_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(OSError, match="ANTHROPIC_API_KEY"):
            ClaudeBridge(make_config())

    async def test_empty_api_key_raises_os_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        with pytest.raises(OSError, match="ANTHROPIC_API_KEY"):
            ClaudeBridge(make_config())
