"""Claude API bridge — executes tasks via the Anthropic messages API.

Provides a thin async wrapper around the synchronous anthropic client,
with retry logic for rate limits and structured result parsing.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING

import anthropic
import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from anthropic.types import Message as AnthropicMessage

    from claudedev.brain.config import BrainConfig

logger = structlog.get_logger(__name__)


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


class ClaudeBridge:
    """Async bridge to the Anthropic messages API.

    Handles rate-limit retries with exponential backoff and maps API errors
    to structured ClaudeResult failures — never raises to the caller.
    """

    _RETRY_BASE_SECONDS: float = 1.0
    _RETRY_MAX_SECONDS: float = 30.0

    def __init__(self, config: BrainConfig) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            msg = "ANTHROPIC_API_KEY environment variable is not set"
            raise OSError(msg)
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic(api_key=api_key)
        self._model: str = config.claude_model
        self._max_retries: int = config.max_retries

    async def execute_task(
        self,
        task: str,
        system_prompt: str,
    ) -> ClaudeResult:
        """Execute a task by sending it to the Claude messages API.

        Retries on RateLimitError with exponential backoff.
        Returns a failed ClaudeResult (never raises) on timeout or API errors.

        Args:
            task: The user-facing task description / prompt.
            system_prompt: The system instructions for Claude.

        Returns:
            ClaudeResult with success=True on a good response, success=False otherwise.
        """
        log = logger.bind(model=self._model)
        start = time.perf_counter()

        for attempt in range(self._max_retries + 1):
            try:
                log.debug("claude_bridge_attempt", attempt=attempt)
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=16384,
                    system=system_prompt,
                    messages=[{"role": "user", "content": task}],
                )
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
                        error=f"Rate limit exceeded after {attempt + 1} attempts: {exc}",
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
                    error=f"timeout: {exc}",
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
                    error=str(exc),
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
                    error=f"Unexpected error: {type(exc).__name__}: {exc}",
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
