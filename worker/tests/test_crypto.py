"""Tests for the shared token encryption format."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from clipmachine.crypto import CryptoError, decrypt

KEY = base64.b64decode(
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
)
FIXTURE = Path(__file__).parent / "fixtures" / "ts_encrypted_token.txt"


def test_typescript_fixture_decrypts() -> None:
    """A token encrypted by the dashboard decrypts in Python."""
    assert decrypt(FIXTURE.read_text(encoding="utf-8"), key=KEY) == (
        "1//0gFixtureRefreshTokenForCrossLanguageTest"
    )


def test_invalid_payload_raises() -> None:
    """Malformed ciphertext is rejected."""
    with pytest.raises(CryptoError, match="invalid encrypted token format"):
        decrypt("not-a-token", key=KEY)


def test_short_key_raises() -> None:
    """The AES key must be 32 bytes."""
    with pytest.raises(CryptoError, match="exactly 32 bytes"):
        decrypt(FIXTURE.read_text(encoding="utf-8"), key=b"short")
