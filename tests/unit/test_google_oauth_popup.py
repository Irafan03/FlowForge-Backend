from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer

from app.api import integrations
from app.engine.context import ExecutionContext
from app.engine.node_executor import execute_node
from app.integrations import gmail
from app.models.credential import Credential
from app.models.oauth_state import OAuthState
from app.models.user import User
from app.services.credential_service import encrypt_data


def test_google_auth_url_persists_nonce_and_returns_signed_state(monkeypatch):
    settings = SimpleNamespace(
        GOOGLE_CLIENT_ID="test-client-id",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        GOOGLE_REDIRECT_URI="https://api.example.test/api/v1/integrations/google/callback",
        SECRET_KEY="test-oauth-state-key",
    )
    monkeypatch.setattr(integrations, "get_settings", lambda: settings)
    user = SimpleNamespace(id="514d3cef-846d-4e91-95b6-c55a979138b5")

    class Query:
        def filter(self, *_conditions):
            return self

        def delete(self, **_kwargs):
            return 0

    class Database:
        def __init__(self):
            self.added = None
            self.committed = False

        def query(self, _model):
            return Query()

        def add(self, row):
            self.added = row

        def commit(self):
            self.committed = True

    db = Database()
    authorization_url = integrations._create_authorization_url(user, db)
    query = parse_qs(urlparse(authorization_url).query)

    assert urlparse(authorization_url).hostname == "accounts.google.com"
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == [settings.GOOGLE_REDIRECT_URI]
    assert "gmail.readonly" in query["scope"][0]
    assert "gmail.send" in query["scope"][0]
    assert query["access_type"] == ["offline"]
    payload = URLSafeTimedSerializer(settings.SECRET_KEY, salt="gmail-oauth-state").loads(query["state"][0])
    assert payload["user_id"] == user.id
    assert db.added.user_id == user.id
    assert db.added.nonce == payload["nonce"]
    assert db.committed is True
    assert isinstance(db.added, OAuthState)


def test_google_auth_url_requires_oauth_configuration(monkeypatch):
    monkeypatch.setattr(
        integrations,
        "get_settings",
        lambda: SimpleNamespace(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET=""),
    )
    with pytest.raises(HTTPException) as error:
        integrations._create_authorization_url(SimpleNamespace(id="user"), object())
    assert error.value.status_code == 503


def test_google_popup_result_contains_status_only(monkeypatch):
    monkeypatch.setattr(
        integrations,
        "get_settings",
        lambda: SimpleNamespace(FRONTEND_URL="https://app.example.test/path"),
    )
    response = integrations._popup_result("connected")
    html = response.body.decode()
    assert response.status_code == 200
    assert '"status": "connected"' in html
    assert "https://app.example.test" in html
    assert "access_token" not in html
    assert "refresh_token" not in html


def test_google_token_exchange_logs_only_safe_provider_error_code(monkeypatch, caplog):
    response = Mock(is_error=True, status_code=401)
    response.json.return_value = {"error": "invalid_client", "access_token": "never-log-this"}
    monkeypatch.setattr(gmail.httpx, "post", Mock(return_value=response))
    settings = SimpleNamespace(
        GOOGLE_CLIENT_ID="test-client-id",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        GOOGLE_REDIRECT_URI="https://api.example.test/callback",
    )

    with caplog.at_level("WARNING", logger=gmail.__name__), pytest.raises(Exception):
        gmail.exchange_code("authorization-code-secret", settings)

    assert "invalid_client" in caplog.text
    assert "never-log-this" not in caplog.text
    assert "authorization-code-secret" not in caplog.text
    assert "test-client-secret" not in caplog.text


def test_gmail_send_resolves_encrypted_oauth_credential(db, monkeypatch):
    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr("app.services.credential_service._get_fernet", lambda: fernet)
    user = User(email=f"gmail-{uuid.uuid4()}@example.com", hashed_password="x")
    db.add(user)
    db.flush()
    credential = Credential(
        user_id=user.id,
        name="Google Gmail",
        type="oauth2_google",
        encrypted_data=encrypt_data({
            "access_token": "access-token-test",
            "refresh_token": "refresh-token-test",
            "expiry": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        }),
    )
    db.add(credential)
    db.flush()
    context = ExecutionContext(
        execution_id=str(uuid.uuid4()),
        workflow_graph={"nodes": [], "edges": []},
        db=db,
        user_id=user.id,
    )
    send = Mock(return_value={"message_id": "sent-1"})
    monkeypatch.setattr("app.integrations.gmail.send_message", send)

    result = execute_node({
        "id": "send",
        "type": "gmail_send",
        "config": {
            "credential_id": str(credential.id),
            "to": "recipient@example.test",
            "subject": "Test",
            "body": "Hello",
        },
    }, context)

    assert result["message_id"] == "sent-1"
    send.assert_called_once()
    assert send.call_args.args[0] == "access-token-test"
