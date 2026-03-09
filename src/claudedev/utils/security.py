"""Security utilities: HMAC verification, secret generation, keychain integration.

NOTE: All subprocess calls use asyncio.create_subprocess_exec (argument list, no shell)
for safe process execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets


def generate_webhook_secret(length: int = 32) -> str:
    """Generate a cryptographically secure webhook secret.

    Args:
        length: Number of random bytes (hex-encoded output is 2x this).

    Returns:
        A hex-encoded random string.
    """
    return secrets.token_hex(length)


def verify_hmac_sha256(payload: bytes, secret: str, signature: str) -> bool:
    """Verify a GitHub-style HMAC-SHA256 signature.

    Args:
        payload: The raw request body bytes.
        secret: The webhook secret string.
        signature: The signature header value (with 'sha256=' prefix).

    Returns:
        True if the signature is valid.
    """
    if not signature.startswith("sha256="):
        return False

    expected = signature[7:]
    computed = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected)


def generate_api_token(prefix: str = "cdev") -> str:
    """Generate a prefixed API token for internal use.

    Args:
        prefix: Token prefix for identification.

    Returns:
        A prefixed token string like 'cdev_abc123...'.
    """
    return f"{prefix}_{secrets.token_urlsafe(32)}"


async def store_secret_keychain(service: str, account: str, password: str) -> bool:
    """Store a secret in the macOS Keychain via the security CLI.

    Uses create_subprocess_exec with argument list (no shell) for safety.

    Args:
        service: Keychain service name.
        account: Account name (key).
        password: The secret value.

    Returns:
        True if stored successfully.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            password,
            "-U",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def get_secret_keychain(service: str, account: str) -> str | None:
    """Retrieve a secret from the macOS Keychain via the security CLI.

    Uses create_subprocess_exec with argument list (no shell) for safety.

    Args:
        service: Keychain service name.
        account: Account name (key).

    Returns:
        The secret value, or None if not found.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "security",
            "find-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip()
        return None
    except Exception:
        return None
