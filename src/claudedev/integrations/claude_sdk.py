"""Claude Agent SDK wrapper for managing agent sessions.

Provides async interface supporting two authentication paths:
1. CLI mode: Uses `claude -p` subprocess for queries
2. API Key mode: Uses the Claude Agent SDK Python package directly

Both modes expose the same interface for callers.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from claudedev.auth import AuthManager, AuthMode

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from claudedev.engines.websocket_manager import WebSocketManager

logger = structlog.get_logger(__name__)


@dataclass
class SessionInfo:
    """Metadata for a Claude Agent SDK session."""

    session_id: str
    prompt: str
    working_dir: str
    subagents: list[str] = field(default_factory=list)
    status: str = "running"
    cost_usd: float = 0.0
    output: str = ""


class ClaudeSDKClient:
    """Async wrapper around Claude, supporting both CLI and SDK modes.

    In CLI mode, invokes `claude -p` as a subprocess.
    In API_KEY mode, uses the Claude Agent SDK Python package.
    Both modes expose the same async interface.
    """

    def __init__(
        self,
        auth_manager: AuthManager,
        max_concurrent: int = 3,
    ) -> None:
        self._auth = auth_manager
        self._sessions: dict[str, SessionInfo] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._mode = auth_manager.get_auth_mode()

    @property
    def auth_mode(self) -> AuthMode:
        """The active authentication mode."""
        return self._mode

    async def create_session(
        self,
        prompt: str,
        working_dir: str,
        subagents: list[str] | None = None,
        max_cost_usd: float = 5.0,
        hooks: dict[str, object] | None = None,
    ) -> str:
        """Create a new session record for tracking purposes only.

        NOTE: This method does NOT invoke Claude. It only stores metadata
        in memory for session tracking. To actually execute a prompt, use
        ``run_query()`` or ``run_headless()``.

        Returns the session ID for subsequent tracking operations.
        """
        session_id = f"claude-{uuid.uuid4().hex[:12]}"
        log = logger.bind(session_id=session_id)

        session_info = SessionInfo(
            session_id=session_id,
            prompt=prompt,
            working_dir=working_dir,
            subagents=subagents or [],
        )
        self._sessions[session_id] = session_info

        log.info(
            "session_created",
            mode=self._mode.value,
            working_dir=working_dir,
            subagents=subagents or [],
            max_cost=max_cost_usd,
        )

        return session_id

    async def run_query(
        self,
        prompt: str,
        cwd: str = ".",
        allowed_tools: list[str] | None = None,
        max_turns: int = 10,
        max_budget_usd: float = 2.0,
        output_format: str = "text",
        system_prompt: str = "",
        *,
        session_id: str | None = None,
        ws_manager: WebSocketManager | None = None,
    ) -> AsyncIterator[str]:
        """Run a query through Claude, streaming results.

        Uses CLI mode or SDK mode depending on the configured auth.

        Args:
            prompt: The prompt to send to Claude.
            cwd: Working directory for the query.
            allowed_tools: List of allowed tool names (CLI mode: --allowedTools).
            max_turns: Maximum conversation turns (CLI mode: --max-turns).
            max_budget_usd: Cost limit for API key mode.
            output_format: Output format - 'text', 'json', or 'stream-json'.
            session_id: Optional session ID for WebSocket broadcast.
            ws_manager: Optional WebSocketManager for live output streaming.

        Yields:
            Response text chunks.
        """
        async with self._semaphore:
            if self._mode == AuthMode.CLI:
                async for chunk in self._run_query_cli(
                    prompt, cwd, allowed_tools, max_turns, output_format, system_prompt,
                    session_id=session_id, ws_manager=ws_manager,
                ):
                    yield chunk
            else:
                async for chunk in self._run_query_sdk(
                    prompt, cwd, allowed_tools, max_turns, max_budget_usd, output_format,
                    system_prompt
                ):
                    yield chunk

    async def _run_query_cli(
        self,
        prompt: str,
        cwd: str,
        allowed_tools: list[str] | None,
        max_turns: int,
        output_format: str,
        system_prompt: str = "",
        *,
        session_id: str | None = None,
        ws_manager: WebSocketManager | None = None,
    ) -> AsyncIterator[str]:
        """Execute a query via the Claude Code CLI (`claude -p`)."""
        log = logger.bind(mode="cli")
        claude_path = self._auth.claude_code_path

        if system_prompt:
            full_prompt = (
                f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n[END SYSTEM INSTRUCTIONS]\n\n{prompt}"
            )
        else:
            full_prompt = prompt

        cmd = [claude_path, "-p", full_prompt, "--output-format", output_format]

        if allowed_tools:
            for tool in allowed_tools:
                cmd.extend(["--allowedTools", tool])

        cmd.extend(["--max-turns", str(max_turns)])

        log.debug("cli_query_start", cmd_length=len(cmd), cwd=cwd)

        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            if process.stdout is None:
                return

            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                yield decoded
                if session_id and ws_manager:
                    await ws_manager.broadcast_output(session_id, decoded.rstrip())

            await process.wait()

            if process.returncode != 0 and process.stderr:
                stderr_output = await process.stderr.read()
                error_text = stderr_output.decode("utf-8", errors="replace").strip()
                if error_text:
                    log.warning("cli_query_stderr", stderr=error_text)

        except (OSError, asyncio.CancelledError) as exc:
            log.error("cli_query_error", error=str(exc))
            raise

    async def _run_query_sdk(
        self,
        prompt: str,
        cwd: str,
        allowed_tools: list[str] | None,
        max_turns: int,
        max_budget_usd: float,
        output_format: str,
        system_prompt: str = "",
    ) -> AsyncIterator[str]:
        """Execute a query via the Claude Agent SDK Python package."""
        log = logger.bind(mode="sdk")
        api_key = self._auth.detect_api_key()

        if not api_key:
            raise RuntimeError("No API key available for SDK mode.")

        log.debug("sdk_query_start", cwd=cwd, max_budget=max_budget_usd)

        if system_prompt:
            full_prompt = (
                f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n[END SYSTEM INSTRUCTIONS]\n\n{prompt}"
            )
        else:
            full_prompt = prompt

        try:
            from claude_agent_sdk import Claude  # type: ignore[attr-defined]

            client = Claude(api_key=api_key)
            response = await client.query(
                prompt=full_prompt,
                cwd=cwd,
                allowed_tools=allowed_tools or [],
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
            )

            if hasattr(response, "__aiter__"):
                async for chunk in response:
                    if hasattr(chunk, "content"):
                        yield str(chunk.content)
                    else:
                        yield str(chunk)
            else:
                yield str(response)

        except ImportError:
            log.error("claude_agent_sdk_not_installed")
            raise RuntimeError(
                "claude-agent-sdk package not installed. "
                "Install it with: poetry add claude-agent-sdk"
            ) from None

    async def run_headless(
        self,
        prompt: str,
        cwd: str = ".",
        allowed_tools: list[str] | None = None,
    ) -> str:
        """Run a simple one-shot query via CLI and return the full result.

        This is a convenience method that collects all output into a single string.
        Always uses CLI mode for simplicity.

        Args:
            prompt: The prompt to send.
            cwd: Working directory.
            allowed_tools: List of allowed tool names.

        Returns:
            The complete response text.
        """
        claude_path = self._auth.claude_code_path
        cmd = [claude_path, "-p", prompt, "--output-format", "text"]

        if allowed_tools:
            for tool in allowed_tools:
                cmd.extend(["--allowedTools", tool])

        log = logger.bind(mode="headless")
        log.debug("headless_query_start", cwd=cwd)

        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=300,
                env=env,
            )

            if result.returncode != 0:
                log.warning(
                    "headless_query_nonzero_exit",
                    returncode=result.returncode,
                    stderr=result.stderr.strip()[:200],
                )

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            log.error("headless_query_timeout")
            raise RuntimeError("Claude CLI query timed out after 300 seconds.") from None

    async def resume_session(
        self,
        session_id: str,
        prompt: str,
    ) -> AsyncIterator[str]:
        """Resume an existing session with a follow-up prompt.

        In CLI mode, uses --resume flag.
        In SDK mode, continues the existing session context.

        Args:
            session_id: The session ID to resume.
            prompt: The follow-up prompt.

        Yields:
            Response text chunks.
        """
        session = self._sessions.get(session_id)
        cwd = session.working_dir if session else "."

        async with self._semaphore:
            if self._mode == AuthMode.CLI:
                claude_path = self._auth.claude_code_path
                cmd = [
                    claude_path,
                    "-p",
                    prompt,
                    "--resume",
                    session_id,
                    "--output-format",
                    "text",
                ]

                env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

                try:
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        cwd=cwd,
                        env=env,
                    )

                    if process.stdout is None:
                        return

                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        yield line.decode("utf-8", errors="replace")

                    await process.wait()
                except (OSError, asyncio.CancelledError) as exc:
                    logger.bind(mode="cli").error("resume_session_error", error=str(exc))
                    raise
            else:
                api_key = self._auth.detect_api_key()
                if not api_key:
                    raise RuntimeError("No API key available for SDK mode.")

                try:
                    from claude_agent_sdk import Claude  # type: ignore[attr-defined]

                    client = Claude(api_key=api_key)
                    response = await client.resume(
                        session_id=session_id,
                        prompt=prompt,
                    )

                    if hasattr(response, "__aiter__"):
                        async for chunk in response:
                            if hasattr(chunk, "content"):
                                yield str(chunk.content)
                            else:
                                yield str(chunk)
                    else:
                        yield str(response)

                except ImportError:
                    raise RuntimeError(
                        "claude-agent-sdk package not installed. "
                        "Install it with: poetry add claude-agent-sdk"
                    ) from None

    async def get_session_cost(self, session_id: str) -> float:
        """Get the accumulated cost for a session.

        In CLI mode, attempts to parse cost from session metadata.
        In SDK mode, queries the SDK for cost tracking.

        Returns:
            Cost in USD, or 0.0 if unknown.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return 0.0

        if self._mode == AuthMode.CLI:
            try:
                claude_path = self._auth.claude_code_path
                result = await asyncio.to_thread(
                    subprocess.run,
                    [claude_path, "session", "cost", session_id],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    try:
                        cost_data = json.loads(result.stdout.strip())
                        if isinstance(cost_data, dict) and "cost_usd" in cost_data:
                            session.cost_usd = float(cost_data["cost_usd"])
                    except (json.JSONDecodeError, ValueError, KeyError):
                        with contextlib.suppress(ValueError):
                            session.cost_usd = float(result.stdout.strip())
            except (subprocess.TimeoutExpired, OSError):
                pass

        return session.cost_usd

    async def get_session_status(self, session_id: str) -> str:
        """Get the current status of a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return "unknown"
        return session.status

    async def get_session_output(self, session_id: str) -> str:
        """Get the output/summary of a completed session."""
        session = self._sessions.get(session_id)
        if session is None:
            return ""
        return session.output

    async def cancel_session(self, session_id: str) -> bool:
        """Cancel a running session."""
        session = self._sessions.get(session_id)
        if session is None:
            return False

        if session.status == "running":
            session.status = "cancelled"
            logger.info("session_cancelled", session_id=session_id)
            return True
        return False

    async def list_sessions(self) -> list[SessionInfo]:
        """List all tracked sessions."""
        return list(self._sessions.values())

    async def cleanup_completed(self) -> int:
        """Remove completed/cancelled/failed sessions from tracking."""
        to_remove = [
            sid
            for sid, info in self._sessions.items()
            if info.status in ("completed", "cancelled", "failed")
        ]
        for sid in to_remove:
            del self._sessions[sid]
        return len(to_remove)
