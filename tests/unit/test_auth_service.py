"""
Unit tests for auth_service: password hashing and JWT round-trip.
No DB required.
"""

from __future__ import annotations

import pytest

from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"
        assert hashed.startswith("$2b$")

    def test_correct_password_verifies(self):
        hashed = hash_password("correct_horse_battery_staple")
        assert verify_password("correct_horse_battery_staple", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_empty_password_hashes(self):
        # Edge case — passlib handles it, bcrypt allows empty strings
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_different_hashes_for_same_password(self):
        # bcrypt uses a random salt each time
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestJWT:
    def test_encode_decode_round_trip(self):
        token, expires_in = create_access_token("user-123")
        assert isinstance(token, str)
        assert expires_in > 0

        user_id = decode_access_token(token)
        assert user_id == "user-123"

    def test_decode_garbage_raises(self):
        with pytest.raises(ValueError):
            decode_access_token("not.a.jwt")

    def test_decode_tampered_token_raises(self):
        token, _ = create_access_token("user-abc")
        # Tamper with the signature
        tampered = token[:-4] + "XXXX"
        with pytest.raises(ValueError):
            decode_access_token(tampered)

    def test_token_contains_user_id(self):
        import base64
        import json

        user_id = "deadbeef-dead-beef-dead-beefdeadbeef"
        token, _ = create_access_token(user_id)

        # Decode payload (no verification, just inspect)
        parts = token.split(".")
        # Add padding
        payload_b64 = parts[1] + "=="
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload["sub"] == user_id
