"""Configuration management for ClaudeDev.

Loads settings from ~/.claudedev/config.toml and environment variables.
Supports CLAUDEDEV_ prefix env vars via pydantic-settings.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from claudedev.auth import AuthMode

CONFIG_DIR = Path.home() / ".claudedev"
CONFIG_FILE = CONFIG_DIR / "config.toml"
PROJECTS_DIR = CONFIG_DIR / "projects"
DB_PATH = CONFIG_DIR / "claudedev.db"
LOG_DIR = CONFIG_DIR / "logs"


def _load_toml_config() -> dict[str, object]:
    """Load configuration from the TOML config file.

    Reads ~/.claudedev/config.toml and flattens nested sections
    into the top-level dict for pydantic-settings consumption.
    """
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}

    flat: dict[str, object] = {}

    # Flatten [auth] section
    auth = data.get("auth", {})
    if isinstance(auth, dict):
        if "mode" in auth:
            flat["auth_mode"] = auth["mode"]
        if "anthropic_api_key" in auth:
            flat["anthropic_api_key"] = auth["anthropic_api_key"]
        if "claude_code_path" in auth:
            flat["claude_code_path"] = auth["claude_code_path"]

    # Flatten [server] section
    server = data.get("server", {})
    if isinstance(server, dict):
        if "port" in server:
            flat["webhook_port"] = server["port"]
        if "host" in server:
            flat["webhook_host"] = server["host"]

    # Flatten [tunnel] section
    tunnel = data.get("tunnel", {})
    if isinstance(tunnel, dict):
        if "enabled" in tunnel:
            flat["tunnel_enabled"] = tunnel["enabled"]
        if "hostname" in tunnel:
            flat["tunnel_hostname"] = tunnel["hostname"]

    # Flatten [claude] section
    claude = data.get("claude", {})
    if isinstance(claude, dict) and "enhancement_max_turns" in claude:
        flat["enhancement_max_turns"] = claude["enhancement_max_turns"]

    # Flatten [budget] section
    budget = data.get("budget", {})
    if isinstance(budget, dict):
        if "max_per_issue" in budget:
            flat["max_budget_per_issue"] = budget["max_per_issue"]
        if "max_per_project_daily" in budget:
            flat["max_budget_per_project_daily"] = budget["max_per_project_daily"]
        if "max_total_daily" in budget:
            flat["max_budget_total_daily"] = budget["max_total_daily"]

    # Flatten [logging] section
    logging_section = data.get("logging", {})
    if isinstance(logging_section, dict):
        if "level" in logging_section:
            flat["log_level"] = logging_section["level"]
        if "dir" in logging_section:
            flat["log_dir"] = logging_section["dir"]

    # Flatten [notifications] section
    notifications = data.get("notifications", {})
    if isinstance(notifications, dict):
        if "enabled" in notifications:
            flat["notifications_enabled"] = notifications["enabled"]
        if "on_enhancement" in notifications:
            flat["notify_on_enhancement"] = notifications["on_enhancement"]
        if "on_implementation" in notifications:
            flat["notify_on_implementation"] = notifications["on_implementation"]
        if "on_pr_ready" in notifications:
            flat["notify_on_pr_ready"] = notifications["on_pr_ready"]
        if "on_error" in notifications:
            flat["notify_on_error"] = notifications["on_error"]

    # Flatten [iterm2] section
    iterm2 = data.get("iterm2", {})
    if isinstance(iterm2, dict):
        if "enabled" in iterm2:
            flat["iterm2_enabled"] = iterm2["enabled"]
        if "color_coding" in iterm2:
            flat["iterm2_color_coding"] = iterm2["color_coding"]

    # Copy any top-level keys that weren't in sections
    for key in data:
        if key not in (
            "auth",
            "server",
            "tunnel",
            "budget",
            "logging",
            "notifications",
            "iterm2",
        ) and isinstance(data[key], str | int | float | bool):
            flat[key] = data[key]

    return flat


class Settings(BaseSettings):
    """Application settings loaded from config.toml and environment variables.

    Environment variables use the CLAUDEDEV_ prefix. For example:
    - CLAUDEDEV_AUTH_MODE=cli
    - CLAUDEDEV_ANTHROPIC_API_KEY=sk-ant-...
    - CLAUDEDEV_WEBHOOK_PORT=8787
    """

    model_config = SettingsConfigDict(
        env_prefix="CLAUDEDEV_",
        env_file=".env",
        extra="ignore",
    )

    # Auth settings
    auth_mode: AuthMode = Field(default=AuthMode.AUTO, description="Authentication mode")
    anthropic_api_key: str = Field(default="", description="Anthropic API key (optional)")
    claude_code_path: str = Field(
        default="claude",
        description="Path to the Claude Code CLI binary",
    )
    keychain_service: str = Field(
        default="com.claudedev",
        description="macOS Keychain service name for API key storage",
    )

    # Server settings
    webhook_port: int = Field(default=8787, ge=1024, le=65535)
    webhook_host: str = "127.0.0.1"
    webhook_secret_default: str = ""

    # Tunnel settings
    tunnel_enabled: bool = True
    tunnel_hostname: str = ""

    # Budget settings
    max_budget_per_issue: float = Field(default=2.0, ge=0.0)
    max_budget_per_project_daily: float = Field(default=20.0, ge=0.0)
    max_budget_total_daily: float = Field(default=50.0, ge=0.0)

    # Logging settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_dir: Path = LOG_DIR

    # Directory settings
    projects_dir: Path = PROJECTS_DIR
    db_url: str = "postgresql+asyncpg://iworldafric@localhost/claudedev"
    daemon_pid_file: Path = CONFIG_DIR / "daemon.pid"

    # Polling and concurrency
    poll_interval_seconds: int = Field(default=300, ge=30)
    max_concurrent_sessions: int = Field(default=3, ge=1, le=10)

    # Claude query settings
    enhancement_max_turns: int = Field(default=50, ge=5, le=200)

    # Feature flags
    auto_enhance_issues: bool = True
    auto_implement: bool = False
    review_on_pr: bool = True

    # Display settings
    issues_display_filter: Literal["open", "all"] = Field(
        default="open",
        description="Issues list filter: 'open' shows only active issues, 'all' shows all including closed",
    )

    # iTerm2 settings
    iterm2_enabled: bool = True
    iterm2_color_coding: bool = True

    # Notification settings
    notifications_enabled: bool = True
    notify_on_enhancement: bool = True
    notify_on_implementation: bool = True
    notify_on_pr_ready: bool = True
    notify_on_error: bool = True

    @field_validator("projects_dir", "log_dir", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()


def load_settings() -> Settings:
    """Load settings from TOML config file and environment variables.

    TOML values are passed as keyword arguments to Settings, which then
    overlays environment variables on top. Environment variables take
    precedence over config file values.
    """
    toml_data = _load_toml_config()
    return Settings(**toml_data)  # type: ignore[arg-type]


def ensure_dirs() -> None:
    """Create required directories if they do not exist."""
    for d in (CONFIG_DIR, PROJECTS_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
