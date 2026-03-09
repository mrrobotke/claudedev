"""Tests for security utilities."""

from __future__ import annotations

import hashlib
import hmac

from claudedev.utils.security import (
    generate_api_token,
    generate_webhook_secret,
    verify_hmac_sha256,
)


class TestVerifyHmacSha256:
    def test_valid_signature(self) -> None:
        secret = "my-secret"
        payload = b'{"action":"opened"}'
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"

        assert verify_hmac_sha256(payload, secret, signature) is True

    def test_invalid_signature(self) -> None:
        secret = "my-secret"
        payload = b'{"action":"opened"}'
        assert verify_hmac_sha256(payload, secret, "sha256=bogus") is False

    def test_wrong_secret(self) -> None:
        payload = b'{"data":"test"}'
        digest = hmac.new(b"correct-secret", payload, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"

        assert verify_hmac_sha256(payload, "wrong-secret", signature) is False

    def test_missing_prefix(self) -> None:
        secret = "my-secret"
        payload = b'{"action":"opened"}'
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        # Without sha256= prefix
        assert verify_hmac_sha256(payload, secret, digest) is False

    def test_empty_payload(self) -> None:
        secret = "my-secret"
        payload = b""
        digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"

        assert verify_hmac_sha256(payload, secret, signature) is True

    def test_empty_signature(self) -> None:
        assert verify_hmac_sha256(b"data", "secret", "") is False

    def test_tampered_payload(self) -> None:
        secret = "my-secret"
        original = b'{"amount":100}'
        digest = hmac.new(secret.encode(), original, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"

        tampered = b'{"amount":9999}'
        assert verify_hmac_sha256(tampered, secret, signature) is False

    def test_timing_safe_comparison_used(self) -> None:
        """Verify the implementation uses hmac.compare_digest (timing-safe)."""
        import inspect

        source = inspect.getsource(verify_hmac_sha256)
        assert "compare_digest" in source


class TestGenerateWebhookSecret:
    def test_default_length(self) -> None:
        secret = generate_webhook_secret()
        # 32 bytes = 64 hex chars
        assert len(secret) == 64

    def test_custom_length(self) -> None:
        secret = generate_webhook_secret(length=16)
        assert len(secret) == 32  # 16 bytes = 32 hex chars

    def test_uniqueness(self) -> None:
        secrets = {generate_webhook_secret() for _ in range(100)}
        assert len(secrets) == 100

    def test_hex_chars_only(self) -> None:
        secret = generate_webhook_secret()
        assert all(c in "0123456789abcdef" for c in secret)

    def test_sufficient_entropy(self) -> None:
        """Default 32 bytes gives 256 bits of entropy."""
        secret = generate_webhook_secret()
        assert len(secret) >= 64  # At least 256 bits


class TestGenerateApiToken:
    def test_default_prefix(self) -> None:
        token = generate_api_token()
        assert token.startswith("cdev_")

    def test_custom_prefix(self) -> None:
        token = generate_api_token(prefix="test")
        assert token.startswith("test_")

    def test_token_length(self) -> None:
        token = generate_api_token()
        # prefix "cdev_" + 32 bytes url-safe base64 (43 chars)
        assert len(token) > 40

    def test_uniqueness(self) -> None:
        tokens = {generate_api_token() for _ in range(100)}
        assert len(tokens) == 100
