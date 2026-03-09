"""Test credential discovery from repository .env files."""

from __future__ import annotations

import re
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Role prefixes that indicate test/dev credentials
_ROLE_PREFIXES = {"TEST", "ADMIN", "E2E", "STAGING", "DEV", "DEMO", "QA"}

# Credential suffixes
_CRED_SUFFIXES = {"USER", "EMAIL", "PASS", "PASSWORD", "TOKEN", "SECRET", "LOGIN", "USERNAME"}

# Exact known patterns (always match)
_EXACT_PATTERNS = {
    "TEST_USER", "TEST_PASS", "TEST_EMAIL", "TEST_PASSWORD",
    "ADMIN_USER", "ADMIN_PASS", "ADMIN_EMAIL", "ADMIN_PASSWORD",
    "E2E_USER", "E2E_PASS", "E2E_EMAIL", "E2E_PASSWORD",
    "LOGIN_EMAIL", "LOGIN_PASSWORD", "LOGIN_USER",
}

# Keys that look like credentials but should be excluded (infrastructure, not test creds)
_EXCLUDE_PATTERNS = {"DATABASE", "DB_", "REDIS", "MONGO", "POSTGRES", "MYSQL", "AWS_SECRET", "GITHUB_TOKEN", "SECRET_KEY"}


def discover_test_credentials(repo_local_path: str) -> dict[str, str]:
    """Scan .env and .env.local in a repo directory for test credential variables.

    .env.local values override .env values (more specific takes precedence).

    Returns:
        Dictionary mapping variable names to their values.
    """
    repo_path = Path(repo_local_path).resolve()
    # Security: validate path is a real directory, not a symlink traversal
    if not repo_path.is_dir():
        logger.warning("credential_discovery_path_not_dir", path=repo_local_path)
        return {}
    # Security: block access to sensitive system directories
    sensitive_roots = {"/etc", "/root", "/sys", "/proc", "/boot", "/dev"}
    path_str = str(repo_path)
    for sensitive in sensitive_roots:
        if path_str == sensitive or path_str.startswith(sensitive + "/"):
            logger.warning("credential_discovery_path_sensitive", path=path_str)
            return {}

    credentials: dict[str, str] = {}

    # .env first, then .env.local overrides
    for env_file in [".env", ".env.local"]:
        env_path = repo_path / env_file
        if env_path.is_file():
            found = _parse_env_file(env_path)
            credentials.update(found)
            if found:
                logger.info(
                    "credentials_discovered",
                    file=env_file,
                    count=len(found),
                    keys=list(found.keys()),
                )

    return credentials


def _is_credential_key(key: str) -> bool:
    """Check if an env var key matches credential patterns."""
    upper = key.upper()

    # Exclude infrastructure credentials
    for excl in _EXCLUDE_PATTERNS:
        if excl in upper:
            return False

    # Exact match
    if upper in _EXACT_PATTERNS:
        return True

    # Pattern match: role prefix + credential suffix
    parts = upper.split("_")
    has_role = any(p in _ROLE_PREFIXES for p in parts)
    has_cred = any(p in _CRED_SUFFIXES for p in parts)
    return has_role and has_cred


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file and return matching credential key-value pairs."""
    credentials: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("env_file_read_error", path=str(path))
        return credentials

    for line in text.splitlines():
        line = line.strip()
        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        # Match KEY=VALUE or KEY="VALUE" or KEY='VALUE'
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if not match:
            continue

        key = match.group(1)
        value = match.group(2).strip()

        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        if _is_credential_key(key) and value:
            credentials[key] = value

    return credentials


def mask_credential_value(key: str, value: str) -> str:
    """Mask credential values for display. Shows emails/usernames, hides passwords/secrets."""
    upper = key.upper()
    # Show user/email fields in full
    if any(s in upper for s in ("USER", "EMAIL", "LOGIN", "USERNAME")):
        return value
    # Mask password/secret/token fields
    if len(value) <= 4:
        return "***"
    return value[:2] + "***" + value[-1]
