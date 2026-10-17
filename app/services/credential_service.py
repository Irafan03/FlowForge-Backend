"""
Credential service: Fernet-based encryption/decryption for external secrets.

The ENCRYPTION_KEY is never logged or returned. Only the encrypted bytes
are stored in the database. The decrypted dict is only materialized in
memory during node execution and discarded afterward.
"""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.ENCRYPTION_KEY
    # Fernet requires a URL-safe base64-encoded 32-byte key.
    # The key in settings must already be in this format.
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_data(data: dict[str, Any]) -> bytes:
    """Serialize data to JSON and encrypt with Fernet."""
    f = _get_fernet()
    plaintext = json.dumps(data).encode("utf-8")
    return f.encrypt(plaintext)


def decrypt_data(encrypted: bytes) -> dict[str, Any]:
    """
    Decrypt Fernet ciphertext and deserialize JSON.
    Raises ValueError on invalid token (wrong key, tampered data, expired ttl).
    Never logs the decrypted content.
    """
    f = _get_fernet()
    try:
        plaintext = f.decrypt(encrypted)
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt credential: invalid token") from exc
    return json.loads(plaintext.decode("utf-8"))
