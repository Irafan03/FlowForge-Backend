"""Mocked tests for Gmail and Telegram integrations and secret access controls."""

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.engine.context import ExecutionContext
from app.engine.node_executor import NodeExecutionError, _handle_telegram_send
from app.integrations import gmail, telegram


def test_gmail_send_uses_encoded_raw_message():
    with patch("app.integrations.gmail._request", return_value={"id": "sent-1"}) as request:
        result = gmail.send_message("access-token", {
            "to": "user@example.com", "subject": "Hello", "body_html": "<p>Hi</p>"
        })
    assert result == {"message_id": "sent-1"}
    args, kwargs = request.call_args
    assert args[:3] == ("POST", "/users/me/messages/send", "access-token")
    assert kwargs["json"]["raw"]


def test_telegram_send_calls_bot_api():
    response = MagicMock()
    response.is_error = False
    response.json.return_value = {"ok": True, "result": {"message_id": 7, "chat": {"id": 12}}}
    with patch("app.integrations.telegram.httpx.post", return_value=response) as post:
        result = telegram.send_message("bot-secret", {
            "chat_id": "12", "text": "hello", "parse_mode": "Markdown"
        })
    assert result == {"message_id": 7, "chat_id": "12"}
    assert post.call_args.args[0].endswith("/sendMessage")
    assert post.call_args.kwargs["json"]["parse_mode"] == "Markdown"


def test_telegram_api_error_does_not_leak_token():
    response = MagicMock()
    response.is_error = False
    response.json.return_value = {"ok": False, "description": "bad token"}
    with patch("app.integrations.telegram.httpx.post", return_value=response):
        with pytest.raises(NodeExecutionError, match="rejected") as error:
            telegram.send_message("sensitive-token", {"chat_id": "1", "text": "hi"})
    assert "sensitive-token" not in str(error.value)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"credential_id": "credential"}, "allowed_chat_ids"),
        ({"credential_id": "credential", "allowed_chat_ids": ["abc"]}, "allowed_chat_ids"),
        ({"credential_id": "credential", "allowed_chat_ids": ["12"], "polling_interval_seconds": 10}, "polling_interval_seconds"),
    ],
)
def test_telegram_trigger_config_validation(config, message):
    from fastapi import HTTPException

    from app.engine.validators import validate_graph

    graph = {"nodes": [{"id": "telegram", "type": "telegram_trigger", "config": config}], "edges": []}
    with pytest.raises(HTTPException, match=message):
        validate_graph(graph)


class _Query:
    def __init__(self, credential):
        self.credential = credential
        self.criteria = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def first(self):
        return self.credential


class _FakeDb:
    def __init__(self, credential):
        self.credential = credential
        self.query_obj = None

    def query(self, _model):
        self.query_obj = _Query(self.credential)
        return self.query_obj


def test_credential_lookup_is_scoped_to_execution_user(monkeypatch):
    import uuid
    from types import SimpleNamespace

    owner_id, other_id, credential_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cred = SimpleNamespace(id=credential_id, user_id=owner_id, type="telegram_bot", encrypted_data=b"encrypted")
    monkeypatch.setattr("app.repositories.credential_repo.get_by_id", lambda db, cid, uid: cred if cid == credential_id and uid == owner_id else None)
    monkeypatch.setattr("app.services.credential_service.decrypt_data", lambda _: {"bot_token": "secret"})

    ctx = ExecutionContext("execution", {}, db=object(), user_id=owner_id)
    assert ctx.get_credential(str(credential_id), "telegram_bot") == {"bot_token": "secret"}
    foreign_ctx = ExecutionContext("execution", {}, db=object(), user_id=other_id)
    with pytest.raises(ValueError, match="not found"):
        foreign_ctx.get_credential(str(credential_id), "telegram_bot")


def test_telegram_node_uses_owned_credential(monkeypatch):
    owner_id, credential_id = uuid.uuid4(), uuid.uuid4()
    cred = SimpleNamespace(id=credential_id, user_id=owner_id, type="telegram_bot", encrypted_data=b"encrypted")
    monkeypatch.setattr("app.repositories.credential_repo.get_by_id", lambda db, cid, uid: cred if uid == owner_id else None)
    monkeypatch.setattr("app.services.credential_service.decrypt_data", lambda _: {"bot_token": "secret"})
    with patch("app.integrations.telegram.send_message", return_value={"message_id": 1}) as send:
        out = _handle_telegram_send({}, {"credential_id": str(credential_id), "chat_id": "1", "text": "hi"},
                                    ExecutionContext("execution", {}, db=object(), user_id=owner_id))
    assert out["message_id"] == 1
    assert send.call_args.args[0] == "secret"


@pytest.mark.asyncio
async def test_telegram_poll_uses_stable_idempotency_key(monkeypatch):
    from app.triggers import integrations as poller

    trigger_id, workflow_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    trigger = SimpleNamespace(id=trigger_id, config={}, type="telegram_trigger")
    workflow = SimpleNamespace(id=workflow_id, user_id=user_id)
    db = MagicMock()
    monkeypatch.setattr(poller, "_credential_data", lambda *args: (None, {"bot_token": "secret"}))
    monkeypatch.setattr(poller.telegram, "get_updates", lambda *args: [{
        "update_id": 41,
        "message": {
            "message_id": 9,
            "chat": {"id": 12},
            "from": {"id": 5, "username": "alice"},
            "text": "hello",
            "date": 100,
        },
    }])
    enqueue = MagicMock()
    async def _enqueue(*args):
        enqueue(*args)
    monkeypatch.setattr(poller.execution_service, "enqueue_external_execution", _enqueue)

    count = await poller._poll_telegram(db, trigger, workflow, {
        "credential_id": str(uuid.uuid4()), "allowed_chat_ids": ["12"]
    })

    assert count == 1
    assert enqueue.call_args.args[-1] == f"telegram:{trigger_id}:41"
    assert trigger.config["offset"] == 42
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_activation_processes_pending_updates(monkeypatch):
    """The first poll after activation processes queued updates and saves the offset."""
    from app.triggers import integrations as poller

    trigger_id, workflow_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    trigger = SimpleNamespace(id=trigger_id, config={}, type="telegram_trigger")
    workflow = SimpleNamespace(id=workflow_id, user_id=user_id)
    db = MagicMock()
    monkeypatch.setattr(poller, "_credential_data", lambda *args: (None, {"bot_token": "secret"}))
    update = {
        "update_id": 41,
        "message": {"message_id": 9, "chat": {"id": 12}, "text": "queued", "date": 100},
    }
    get_updates = MagicMock(return_value=[update])
    monkeypatch.setattr(poller.telegram, "get_updates", get_updates)
    enqueue = AsyncMock()
    monkeypatch.setattr(poller.execution_service, "enqueue_external_execution", enqueue)

    count = await poller._poll_telegram(db, trigger, workflow, {
        "credential_id": str(uuid.uuid4()), "allowed_chat_ids": [12]
    })

    assert count == 1
    assert enqueue.await_args.args[-1] == f"telegram:{trigger_id}:41"
    assert get_updates.call_args.args[1] is None
    assert trigger.config["offset"] == 42


@pytest.mark.asyncio
async def test_external_execution_recovers_concurrent_unique_key_conflict(monkeypatch):
    from app.models.execution import ExecutionStatus
    from app.services import execution_service

    workflow_id, user_id, execution_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    existing = SimpleNamespace(
        id=execution_id,
        workflow_id=workflow_id,
        user_id=user_id,
        status=ExecutionStatus.QUEUED,
    )
    query = MagicMock()
    query.filter.return_value = query
    query.first.side_effect = [None, existing]
    db = MagicMock()
    db.query.return_value = query
    monkeypatch.setattr(execution_service.workflow_repo, "get_by_id", lambda *_: object())
    monkeypatch.setattr(
        execution_service.execution_repo,
        "create_execution",
        MagicMock(side_effect=IntegrityError("insert", {}, Exception("duplicate key"))),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(execution_service, "_enqueue_arq", enqueue)

    result = await execution_service.enqueue_external_execution(
        db, workflow_id, user_id, "telegram_trigger", {"text": "hello"}, "telegram:event-1"
    )

    assert result is existing
    db.rollback.assert_called_once()
    assert query.first.call_count == 2
    enqueue.assert_awaited_once_with(str(execution_id))


@pytest.mark.asyncio
async def test_telegram_poll_rejects_missing_chat_allowlist(monkeypatch):
    from app.triggers import integrations as poller

    with pytest.raises(ValueError, match="allowed_chat_id"):
        await poller._poll_telegram(MagicMock(), SimpleNamespace(config={}), SimpleNamespace(), {})


def test_google_callback_consumes_oauth_state_once(monkeypatch):
    import sys
    from types import ModuleType

    from fastapi import HTTPException

    from app import api as api_package

    # Load this router under a test-only name; neither the application router nor
    # the temporary dependency stub is left cached after this test.
    module_path = Path(__file__).resolve().parents[2] / "app" / "api" / "integrations.py"
    previous_deps_module = sys.modules.get("app.api.deps")
    had_package_deps = hasattr(api_package, "deps")
    package_deps_before = getattr(api_package, "deps", None)
    # The real dependency module creates a PostgreSQL engine at import time. Give
    # this isolated module stub dependencies only for this import, then restore
    # the previous sys.modules entry before any other test can observe the stub.
    isolated_deps = ModuleType("app.api.deps")
    isolated_deps.get_db = lambda: None
    isolated_deps.get_current_user = lambda: None
    with monkeypatch.context() as isolated:
        isolated.setitem(sys.modules, "app.api.deps", isolated_deps)
        isolated.setattr(api_package, "deps", isolated_deps, raising=False)
        spec = importlib.util.spec_from_file_location(
            f"test_google_integrations_router_{uuid.uuid4().hex}", module_path
        )
        assert spec is not None and spec.loader is not None
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
    assert sys.modules.get("app.api.deps") is previous_deps_module
    assert hasattr(api_package, "deps") is had_package_deps
    if had_package_deps:
        assert api_package.deps is package_deps_before

    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, is_active=True)
    state_row = SimpleNamespace(nonce="nonce", user_id=user_id)

    class _StateQuery:
        def __init__(self, db):
            self.db = db
        def filter(self, *_criteria):
            return self
        def with_for_update(self):
            return self
        def first(self):
            return self.db.state

    class _Db:
        def __init__(self):
            self.state = state_row
        def query(self, _model):
            return _StateQuery(self)
        def delete(self, row):
            assert row is state_row
            self.state = None
        def commit(self):
            pass

    db = _Db()
    settings = SimpleNamespace(GOOGLE_CLIENT_ID="client", GOOGLE_CLIENT_SECRET="secret", FRONTEND_URL="http://localhost:5173")
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(api, "_serializer", lambda: SimpleNamespace(loads=lambda *_a, **_k: {"user_id": str(user_id), "nonce": "nonce"}))
    monkeypatch.setattr("app.repositories.user_repo.get_by_id", lambda *_args: user)
    monkeypatch.setattr("app.integrations.gmail.exchange_code", lambda *_args: {"access_token": "access", "refresh_token": "refresh"})
    monkeypatch.setattr(api, "encrypt_data", lambda data: b"encrypted")
    saved = {}
    monkeypatch.setattr("app.repositories.credential_repo.create", lambda _db, **kwargs: saved.update(kwargs))

    result = api.google_callback("auth-code", "signed-state", error=None, db=db)
    assert result.status_code == 200
    assert "flowforge:google-oauth" in result.body.decode()
    assert '"status": "connected"' in result.body.decode()
    assert "refresh" not in result.body.decode()
    assert saved["type"] == "oauth2_google"
    assert saved["encrypted_data"] == b"encrypted"
    assert "refresh_token" not in result.body.decode()
    with pytest.raises(HTTPException) as error:
        api.google_callback("auth-code", "signed-state", error=None, db=db)
    assert error.value.status_code == 400
