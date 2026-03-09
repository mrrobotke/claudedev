"""Cloudflare Tunnel management for webhook ingress.

Manages the cloudflared tunnel process lifecycle and provides
the public URL for GitHub webhooks. Uses asyncio.create_subprocess_exec
for safe (non-shell) process spawning.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class TunnelStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class TunnelInfo:
    """Information about the running tunnel."""

    status: TunnelStatus
    public_url: str = ""
    hostname: str = ""
    pid: int | None = None
    error: str = ""


class TunnelManager:
    """Manages the Cloudflare tunnel (cloudflared) process.

    Starts a tunnel that exposes the local webhook server to the internet,
    providing a public HTTPS URL for GitHub webhooks.
    """

    def __init__(self, local_port: int = 8787, hostname: str = "") -> None:
        self.local_port = local_port
        self.hostname = hostname
        self._process: asyncio.subprocess.Process | None = None
        self._public_url: str = ""
        self._status: TunnelStatus = TunnelStatus.STOPPED

    @staticmethod
    def _find_cloudflared() -> str:
        """Find the cloudflared binary, checking common locations."""
        import shutil

        path = shutil.which("cloudflared")
        if path:
            return path
        common_paths: list[Path] = [
            Path("/opt/homebrew/bin/cloudflared"),
            Path("/usr/local/bin/cloudflared"),
            Path("/usr/bin/cloudflared"),
            Path.home() / ".cloudflared" / "cloudflared",
        ]
        for candidate in common_paths:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        raise FileNotFoundError("cloudflared not found")

    async def start(self) -> TunnelInfo:
        """Start the cloudflared tunnel and extract the public URL."""
        if self._status == TunnelStatus.RUNNING:
            return self.info

        self._status = TunnelStatus.STARTING
        logger.info("tunnel_starting", port=self.local_port, hostname=self.hostname)

        try:
            cloudflared_bin = self._find_cloudflared()
            if self.hostname:
                cmd_args = [
                    cloudflared_bin,
                    "tunnel",
                    "run",
                    "--url",
                    f"http://localhost:{self.local_port}",
                ]
            else:
                cmd_args = [
                    cloudflared_bin,
                    "tunnel",
                    "--url",
                    f"http://localhost:{self.local_port}",
                    "--no-autoupdate",
                ]

            self._process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            url = await self._wait_for_url(timeout=30)
            if url:
                self._public_url = url
                self._status = TunnelStatus.RUNNING
                logger.info("tunnel_started", url=url, pid=self._process.pid)
            else:
                self._status = TunnelStatus.ERROR
                logger.error("tunnel_no_url")

            return self.info

        except FileNotFoundError:
            self._status = TunnelStatus.ERROR
            logger.error("cloudflared_not_found")
            return TunnelInfo(
                status=TunnelStatus.ERROR,
                error="cloudflared not found. Install with: brew install cloudflared",
            )
        except Exception as exc:
            self._status = TunnelStatus.ERROR
            logger.exception("tunnel_start_failed")
            return TunnelInfo(status=TunnelStatus.ERROR, error=str(exc))

    async def _wait_for_url(self, timeout: int = 30) -> str:
        """Wait for cloudflared to output its public URL."""
        if self.hostname:
            return f"https://{self.hostname}"

        if self._process is None or self._process.stderr is None:
            return ""

        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

        try:
            async with asyncio.timeout(timeout):
                while True:
                    line_bytes = await self._process.stderr.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace")
                    match = url_pattern.search(line)
                    if match:
                        return match.group(0)
        except TimeoutError:
            logger.warning("tunnel_url_timeout")

        return ""

    async def stop(self) -> None:
        """Stop the cloudflared tunnel process."""
        if self._process is not None:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=10)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass

            logger.info("tunnel_stopped", pid=self._process.pid)
            self._process = None

        self._status = TunnelStatus.STOPPED
        self._public_url = ""

    @property
    def info(self) -> TunnelInfo:
        """Get current tunnel information."""
        return TunnelInfo(
            status=self._status,
            public_url=self._public_url,
            hostname=self.hostname,
            pid=self._process.pid if self._process else None,
        )

    @property
    def is_running(self) -> bool:
        return self._status == TunnelStatus.RUNNING

    @property
    def public_url(self) -> str:
        return self._public_url
