"""Authentication management for ClaudeDev.

Supports two authentication paths:
1. Claude Code CLI (`claude -p`): Uses existing Claude Code subscription from ~/.claude/
   - No API key needed
   - Checks if `claude` is installed and authenticated
2. Anthropic API Key: For Claude Agent SDK usage
   - Reads from ANTHROPIC_API_KEY env var
   - Or from ~/.claudedev/config.toml
   - Or from macOS Keychain
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

CONFIG_DIR = Path.home() / ".claudedev"
CONFIG_FILE = CONFIG_DIR / "config.toml"

KEYCHAIN_SERVICE = "com.claudedev"
KEYCHAIN_ACCOUNT = "anthropic-api-key"


class AuthMode(StrEnum):
    """Authentication mode for ClaudeDev."""

    CLI = "cli"
    API_KEY = "api_key"
    AUTO = "auto"


@dataclass
class AuthStatus:
    """Result of authentication validation."""

    mode: AuthMode
    is_valid: bool
    claude_code_version: str = ""
    api_key_source: str = ""
    error_message: str = ""
    details: dict[str, str] = field(default_factory=dict)


class AuthManager:
    """Manages authentication for ClaudeDev.

    Supports CLI-based auth (claude -p) and API key auth (Claude Agent SDK).
    Auto mode detects the best available authentication method.
    """

    def __init__(
        self,
        preferred_mode: AuthMode = AuthMode.AUTO,
        claude_code_path: str = "claude",
        keychain_service: str = KEYCHAIN_SERVICE,
        api_key: str = "",
    ) -> None:
        self._preferred_mode = preferred_mode
        self._claude_code_path = claude_code_path
        self._keychain_service = keychain_service
        self._explicit_api_key = api_key

    @property
    def claude_code_path(self) -> str:
        """The path to the Claude Code CLI executable."""
        return self._claude_code_path

    def detect_claude_code(self) -> bool:
        """Check if the Claude Code CLI is installed and accessible.

        Runs `claude --version` to verify the CLI is available.
        Returns True if the CLI is found and responds.
        """
        claude_path = shutil.which(self._claude_code_path)
        if claude_path is None:
            logger.debug("claude_code_not_found", path=self._claude_code_path)
            return False

        try:
            result = subprocess.run(
                [self._claude_code_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                logger.debug("claude_code_detected", version=result.stdout.strip())
                return True
            logger.debug(
                "claude_code_version_failed",
                returncode=result.returncode,
                stderr=result.stderr.strip(),
            )
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("claude_code_detection_error", error=str(exc))
            return False

    def _get_claude_code_version(self) -> str:
        """Get the version string of the Claude Code CLI."""
        try:
            result = subprocess.run(
                [self._claude_code_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return ""

    def detect_api_key(self) -> str | None:
        """Detect an Anthropic API key from available sources.

        Checks in order:
        1. Explicitly provided key (constructor argument)
        2. ANTHROPIC_API_KEY environment variable
        3. Config file (~/.claudedev/config.toml)
        4. macOS Keychain

        Returns the API key if found, None otherwise.
        """
        if self._explicit_api_key:
            logger.debug("api_key_source", source="explicit")
            return self._explicit_api_key

        env_key = os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            logger.debug("api_key_source", source="environment")
            return env_key

        config_key = self._get_api_key_from_config()
        if config_key:
            logger.debug("api_key_source", source="config_file")
            return config_key

        keychain_key = self.get_api_key_from_keychain()
        if keychain_key:
            logger.debug("api_key_source", source="keychain")
            return keychain_key

        return None

    def _get_api_key_source(self) -> str:
        """Identify the source of the API key for status reporting."""
        if self._explicit_api_key:
            return "explicit"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "environment"
        if self._get_api_key_from_config():
            return "config_file"
        if self.get_api_key_from_keychain():
            return "keychain"
        return ""

    def _get_api_key_from_config(self) -> str | None:
        """Read the API key from the TOML config file."""
        if not CONFIG_FILE.exists():
            return None
        try:
            with open(CONFIG_FILE, "rb") as f:
                data = tomllib.load(f)
            auth_section = data.get("auth", {})
            if isinstance(auth_section, dict):
                key = auth_section.get("anthropic_api_key")
                if isinstance(key, str) and key.startswith("sk-ant-"):
                    return key
        except (OSError, tomllib.TOMLDecodeError) as exc:
            logger.warning("config_read_error", error=str(exc))
        return None

    def get_api_key_from_keychain(self) -> str | None:
        """Retrieve the Anthropic API key from macOS Keychain.

        Uses the `security find-generic-password` command to access
        the keychain item stored under the configured service name.
        """
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    self._keychain_service,
                    "-a",
                    KEYCHAIN_ACCOUNT,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                key = result.stdout.strip()
                if key.startswith("sk-ant-"):
                    return key
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("keychain_read_error", error=str(exc))
        return None

    def store_api_key(self, key: str) -> None:
        """Store an Anthropic API key in the macOS Keychain.

        Uses the `security add-generic-password` command. If an entry
        already exists, it is updated.

        Args:
            key: The Anthropic API key to store. Must start with 'sk-ant-'.

        Raises:
            ValueError: If the key format is invalid.
            RuntimeError: If the keychain operation fails.
        """
        if not key.startswith("sk-ant-"):
            raise ValueError("Invalid API key format. Key must start with 'sk-ant-'.")

        # Try to delete existing entry first (ignore errors if not found)
        subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-s",
                self._keychain_service,
                "-a",
                KEYCHAIN_ACCOUNT,
            ],
            capture_output=True,
            timeout=10,
        )

        result = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-s",
                self._keychain_service,
                "-a",
                KEYCHAIN_ACCOUNT,
                "-w",
                key,
                "-U",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to store API key in keychain: {result.stderr.strip()}")
        logger.info("api_key_stored_in_keychain", service=self._keychain_service)

    def get_auth_mode(self) -> AuthMode:
        """Determine the best available authentication mode.

        If preferred mode is AUTO, checks for CLI first, then API key.
        If a specific mode is preferred, validates that it's available.

        Returns:
            The detected AuthMode (CLI or API_KEY).
        """
        if self._preferred_mode == AuthMode.CLI:
            return AuthMode.CLI
        if self._preferred_mode == AuthMode.API_KEY:
            return AuthMode.API_KEY

        # AUTO mode: prefer CLI if available, fall back to API key
        if self.detect_claude_code():
            return AuthMode.CLI
        if self.detect_api_key() is not None:
            return AuthMode.API_KEY

        # Default to CLI even if not detected (will fail at validation)
        return AuthMode.CLI

    def validate_auth(self) -> AuthStatus:
        """Validate the current authentication configuration.

        Checks the preferred or auto-detected auth mode and returns
        a detailed status including validity, version info, and any errors.

        Returns:
            AuthStatus with validation results.
        """
        mode = self.get_auth_mode()

        if mode == AuthMode.CLI:
            return self._validate_cli_auth()
        return self._validate_api_key_auth()

    def _validate_cli_auth(self) -> AuthStatus:
        """Validate CLI-based authentication."""
        if not self.detect_claude_code():
            return AuthStatus(
                mode=AuthMode.CLI,
                is_valid=False,
                error_message=(
                    f"Claude Code CLI not found at '{self._claude_code_path}'. "
                    "Install it or provide an API key instead."
                ),
            )

        version = self._get_claude_code_version()
        return AuthStatus(
            mode=AuthMode.CLI,
            is_valid=True,
            claude_code_version=version,
            details={"path": shutil.which(self._claude_code_path) or self._claude_code_path},
        )

    def _validate_api_key_auth(self) -> AuthStatus:
        """Validate API key-based authentication."""
        key = self.detect_api_key()
        if key is None:
            return AuthStatus(
                mode=AuthMode.API_KEY,
                is_valid=False,
                error_message=(
                    "No Anthropic API key found. Set ANTHROPIC_API_KEY env var, "
                    "add it to ~/.claudedev/config.toml, or store it in the macOS Keychain."
                ),
            )

        source = self._get_api_key_source()
        # Mask the key for logging: show first 10 chars + last 4
        masked = key[:10] + "..." + key[-4:] if len(key) > 14 else key[:4] + "..."
        return AuthStatus(
            mode=AuthMode.API_KEY,
            is_valid=True,
            api_key_source=source,
            details={"masked_key": masked},
        )

    def ensure_authenticated(self) -> None:
        """Ensure valid authentication is available.

        Raises:
            RuntimeError: If no valid authentication method is available.
        """
        status = self.validate_auth()
        if not status.is_valid:
            raise RuntimeError(
                f"Authentication failed ({status.mode.value}): {status.error_message}"
            )
        logger.info(
            "authentication_valid",
            mode=status.mode.value,
            version=status.claude_code_version or None,
            key_source=status.api_key_source or None,
        )

    async def ensure_authenticated_async(self) -> None:
        """Async wrapper for ensure_authenticated.

        Runs the synchronous auth checks in a thread pool to avoid
        blocking the event loop on subprocess calls.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.ensure_authenticated)

    def get_api_key_or_none(self) -> str | None:
        """Return the API key if auth mode is API_KEY, else None.

        Convenience method for components that need the raw key.
        """
        mode = self.get_auth_mode()
        if mode == AuthMode.API_KEY:
            return self.detect_api_key()
        return None
