"""Decrypt dashboard-issued OAuth tokens with AES-256-GCM."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENV = "TOKEN_ENCRYPTION_KEY"
IV_LENGTH = 12
TAG_LENGTH = 16


class CryptoError(RuntimeError):
    """Raised when the encryption key or token payload is invalid."""


def _decode_key(key: bytes | None = None) -> bytes:
    """Return the 32-byte AES key from an argument or the environment."""
    if key is not None:
        decoded = key
    else:
        raw = os.environ.get(KEY_ENV)
        if not raw:
            raise CryptoError(f"{KEY_ENV} is not set")
        try:
            decoded = base64.b64decode(raw)
        except ValueError as exc:
            raise CryptoError(f"{KEY_ENV} is not valid base64") from exc
    if len(decoded) != 32:
        raise CryptoError(f"{KEY_ENV} must decode to exactly 32 bytes")
    return decoded


def decrypt(value: str, key: bytes | None = None) -> str:
    """Decrypt a base64(iv).base64(tag).base64(ciphertext) token."""
    parts = value.split(".")
    if len(parts) != 3:
        raise CryptoError("invalid encrypted token format")
    try:
        iv, tag, ciphertext = (base64.b64decode(part) for part in parts)
    except ValueError as exc:
        raise CryptoError("invalid encrypted token format") from exc
    if len(iv) != IV_LENGTH or len(tag) != TAG_LENGTH:
        raise CryptoError("invalid encrypted token format")
    key_bytes = _decode_key(key)
    try:
        plaintext = AESGCM(key_bytes).decrypt(iv, ciphertext + tag, None)
    except Exception as exc:
        raise CryptoError("could not decrypt token") from exc
    return plaintext.decode("utf-8")
