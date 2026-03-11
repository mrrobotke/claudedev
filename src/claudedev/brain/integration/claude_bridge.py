"""Claude API bridge — executes tasks via the Anthropic messages API.

Provides a thin async wrapper around the synchronous anthropic client,
with retry logic for rate limits and structured result parsing.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Literal

import anthropic
import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anthropic.types import Message as AnthropicMessage

    from claudedev.brain.config import BrainConfig

logger = structlog.get_logger(__name__)

_MAX_ERROR_LENGTH = 500


class ClaudeResult(BaseModel):
    """Structured result from a Claude API call."""

    content: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    stop_reason: str
    tool_use_history: list[str]
    duration_ms: float
    success: bool
    error: str | None = None
    turns_used: int = Field(default=1, ge=1)


class StreamChunk(BaseModel):
    """A single chunk from a streaming Claude response."""

    type: Literal["text", "tool_use_start", "tool_use_end", "done"]
    content: str = ""
    tool_name: str | None = None


class ClaudeBridge:
    """Async bridge to the Anthropic messages API.

    Handles rate-limit retries with exponential backoff and maps API errors
    to structured ClaudeResult failures -- never raises to the caller.
    """

    _RETRY_BASE_SECONDS: float = 1.0
    _RETRY_MAX_SECONDS: float = 30.0

    def __init__(self, config: BrainConfig) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        claude_code_token = os.environ.get("CLAUDE_CODE_TOKEN", "")

        if api_key:
            self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic(api_key=api_key)
            self._auth_mode: str = "api_key"
        elif claude_code_token:
            raw_url = os.environ.get("CLAUDE_CODE_BASE_URL", "https://api.anthropic.com")
            if not raw_url.startswith("https://"):
                msg = f"CLAUDE_CODE_BASE_URL must use HTTPS, got: {raw_url!r}"
                raise ValueError(msg)
            self._client = anthropic.AsyncAnthropic(
                api_key=claude_code_token,
                base_url=raw_url,
            )
            self._auth_mode = "claude_code_subscription"
        else:
            msg = "No authentication configured: set ANTHROPIC_API_KEY or CLAUDE_CODE_TOKEN"
            raise OSError(msg)

        self._model: str = config.claude_model
        self._max_retries: int = config.max_retries
        logger.info("claude_bridge_init", auth_mode=self._auth_mode)

    @property
    def auth_mode(self) -> str:
        """Return the authentication mode used by this bridge."""
        return self._auth_mode

    async def execute_task(
        self,
        task: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
    ) -> ClaudeResult:
        """Execute a task by sending it to the Claude messages API.

        Retries on RateLimitError with exponential backoff.
        Returns a failed ClaudeResult (never raises) on timeout or API errors.

        Args:
            task: The user-facing task description / prompt.
            system_prompt: The system instructions for Claude.
            allowed_tools: Optional list of tool names to make available. When
                provided, minimal tool definitions are constructed and passed
                to the API.
            max_turns: Maximum number of agentic turns (default 30). Accepted
                for forward-compatibility but not yet implemented (Phase 2).

        Returns:
            ClaudeResult with success=True on a good response, success=False otherwise.
        """
        log = logger.bind(
            model=self._model,
            allowed_tools_count=len(allowed_tools) if allowed_tools else 0,
            max_turns=max_turns,
        )
        log.debug("max_turns_not_yet_implemented", max_turns=max_turns)
        start = time.perf_counter()

        for attempt in range(self._max_retries + 1):
            try:
                log.debug("claude_bridge_attempt", attempt=attempt)
                create_kwargs: dict[str, object] = {
                    "model": self._model,
                    "max_tokens": 16384,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": task}],
                }
                if allowed_tools is not None:
                    create_kwargs["tools"] = [
                        {
                            "name": name,
                            "description": f"Tool: {name}",
                            "input_schema": {"type": "object"},
                        }
                        for name in allowed_tools
                    ]
                response = await self._client.messages.create(**create_kwargs)  # type: ignore[call-overload]
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                result = self._parse_response(response, elapsed_ms)
                log.info(
                    "claude_bridge_success",
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    stop_reason=result.stop_reason,
                    duration_ms=round(elapsed_ms, 1),
                )
                return result

            except anthropic.RateLimitError as exc:
                if attempt >= self._max_retries:
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    log.warning("claude_bridge_rate_limit_exhausted", attempts=attempt + 1)
                    return ClaudeResult(
                        content="",
                        input_tokens=0,
                        output_tokens=0,
                        stop_reason="",
                        tool_use_history=[],
                        duration_ms=elapsed_ms,
                        success=False,
                        error=f"Rate limit exceeded after {attempt + 1} attempts: {exc}"[
                            :_MAX_ERROR_LENGTH
                        ],
                    )
                wait = min(self._RETRY_BASE_SECONDS * (2**attempt), self._RETRY_MAX_SECONDS)
                log.warning(
                    "claude_bridge_rate_limit_retry",
                    attempt=attempt,
                    wait_seconds=wait,
                )
                await asyncio.sleep(wait)

            except anthropic.APITimeoutError as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                log.error("claude_bridge_timeout", error=str(exc))
                return ClaudeResult(
                    content="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="",
                    tool_use_history=[],
                    duration_ms=elapsed_ms,
                    success=False,
                    error=f"timeout: {exc}"[:_MAX_ERROR_LENGTH],
                )

            except anthropic.APIError as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                log.error("claude_bridge_api_error", error=str(exc))
                return ClaudeResult(
                    content="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="",
                    tool_use_history=[],
                    duration_ms=elapsed_ms,
                    success=False,
                    error=str(exc)[:_MAX_ERROR_LENGTH],
                )

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                log.error("claude_bridge_unexpected_error", error=str(exc), exc_info=True)
                return ClaudeResult(
                    content="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="",
                    tool_use_history=[],
                    duration_ms=elapsed_ms,
                    success=False,
                    error=f"Unexpected error: {type(exc).__name__}: {exc}"[:_MAX_ERROR_LENGTH],
                )

        # Unreachable, but satisfies the type checker.
        elapsed_ms = (time.perf_counter() - start) * 1000.0  # pragma: no cover
        return ClaudeResult(  # pragma: no cover
            content="",
            input_tokens=0,
            output_tokens=0,
            stop_reason="",
            tool_use_history=[],
            duration_ms=elapsed_ms,
            success=False,
            error="Unexpected loop exit",
        )

    async def execute_task_stream(
        self,
        task: str,
        system_prompt: str,
        allowed_tools: list[str] | None = None,
        max_turns: int = 30,
    ) -> AsyncIterator[StreamChunk]:
        """Execute a task with streaming response.

        Yields StreamChunk objects as the response is generated.
        The final chunk has type="done".

        Never raises -- yields a done chunk with error on failure.

        Args:
            task: The user-facing task description / prompt.
            system_prompt: The system instructions for Claude.
            allowed_tools: Optional list of tool names to make available.
            max_turns: Maximum number of agentic turns (default 30). Accepted
                for forward-compatibility but not yet implemented (Phase 2).
        """
        log = logger.bind(
            model=self._model,
            allowed_tools_count=len(allowed_tools) if allowed_tools else 0,
            max_turns=max_turns,
        )
        log.debug("max_turns_not_yet_implemented", max_turns=max_turns)
        start = time.perf_counter()

        create_kwargs: dict[str, object] = {
            "model": self._model,
            "max_tokens": 16384,
            "system": system_prompt,
            "messages": [{"role": "user", "content": task}],
        }
        if allowed_tools is not None:
            create_kwargs["tools"] = [
                {"name": name, "description": f"Tool: {name}", "input_schema": {"type": "object"}}
                for name in allowed_tools
            ]

        try:
            _in_tool_use = False
            async with self._client.messages.stream(**create_kwargs) as stream:  # type: ignore[arg-type]
                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if hasattr(block, "type") and block.type == "tool_use":
                            _in_tool_use = True
                            yield StreamChunk(type="tool_use_start", tool_name=block.name)
                        else:
                            _in_tool_use = False
                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if hasattr(delta, "text"):
                            yield StreamChunk(type="text", content=delta.text)
                    elif event.type == "content_block_stop":
                        if _in_tool_use:
                            yield StreamChunk(type="tool_use_end")
                            _in_tool_use = False

                # Get the final message for metadata
                final_message = await stream.get_final_message()
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                result = self._parse_response(final_message, elapsed_ms)
                log.info("stream_complete", duration_ms=round(elapsed_ms, 1))
                yield StreamChunk(type="done", content=result.model_dump_json())

        except anthropic.RateLimitError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            log.warning("stream_rate_limited", error=str(exc))
            yield StreamChunk(
                type="done",
                content=ClaudeResult(
                    content="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="",
                    tool_use_history=[],
                    duration_ms=elapsed_ms,
                    success=False,
                    error=f"Rate limit: {exc}"[:_MAX_ERROR_LENGTH],
                ).model_dump_json(),
            )

        except anthropic.APIError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            log.error("stream_api_error", error=str(exc))
            yield StreamChunk(
                type="done",
                content=ClaudeResult(
                    content="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="",
                    tool_use_history=[],
                    duration_ms=elapsed_ms,
                    success=False,
                    error=str(exc)[:_MAX_ERROR_LENGTH],
                ).model_dump_json(),
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            log.error("stream_unexpected_error", error=str(exc), exc_info=True)
            yield StreamChunk(
                type="done",
                content=ClaudeResult(
                    content="",
                    input_tokens=0,
                    output_tokens=0,
                    stop_reason="",
                    tool_use_history=[],
                    duration_ms=elapsed_ms,
                    success=False,
                    error=f"Unexpected error: {type(exc).__name__}: {exc}"[:_MAX_ERROR_LENGTH],
                ).model_dump_json(),
            )

    def _parse_response(self, response: AnthropicMessage, duration_ms: float) -> ClaudeResult:
        """Extract structured fields from an Anthropic Message response.

        Args:
            response: The anthropic.types.Message returned by messages.create.
            duration_ms: Elapsed time to include in the result.

        Returns:
            ClaudeResult populated from the response content blocks and usage.
        """
        text_parts: list[str] = []
        tool_names: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_names.append(block.name)

        content = "".join(text_parts)
        stop_reason: str = response.stop_reason or ""
        input_tokens: int = response.usage.input_tokens
        output_tokens: int = response.usage.output_tokens

        return ClaudeResult(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
            tool_use_history=tool_names,
            duration_ms=duration_ms,
            success=True,
            error=None,
        )
