from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.models.execution import ExecutionStatus
from app.models.trigger import Trigger, TriggerType
from app.services import execution_service


def _register_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _webhook_graph() -> dict:
    return {
        "nodes": [
            {"id": "webhook", "type": "webhook_trigger", "config": {}},
            {
                "id": "set",
                "type": "set_data",
                "config": {"fields": [{"key": "received", "value": True}]},
            },
        ],
        "edges": [{"id": "edge", "source": "webhook", "target": "set"}],
    }


def _create_webhook_workflow(client: TestClient, email: str) -> tuple[str, dict]:
    token = _register_and_login(client, email)
    response = client.post(
        "/api/v1/workflows",
        json={"name": "Webhook lifecycle", "graph": _webhook_graph()},
        headers=_auth(token),
    )
    assert response.status_code == 201
    return token, response.json()


def test_webhook_provisions_private_stable_token_and_owner_url(client, db):
    owner_token, workflow = _create_webhook_workflow(client, "webhook-owner@example.com")
    trigger = db.query(Trigger).filter_by(workflow_id=uuid.UUID(workflow['id'])).one()

    assert trigger.type == TriggerType.WEBHOOK
    assert uuid.UUID(trigger.webhook_token).version == 4
    assert workflow["graph"]["nodes"][0]["config"] == {}
    assert trigger.webhook_token not in str(workflow["graph"])

    url_response = client.get(
        f"/api/v1/workflows/{workflow['id']}/webhook-url",
        headers=_auth(owner_token),
    )
    assert url_response.status_code == 200
    assert url_response.json()["webhook_path"] == f"webhooks/{trigger.webhook_token}"

    other_token = _register_and_login(client, "webhook-other@example.com")
    other_response = client.get(
        f"/api/v1/workflows/{workflow['id']}/webhook-url",
        headers=_auth(other_token),
    )
    assert other_response.status_code == 404

    client.put(
        f"/api/v1/workflows/{workflow['id']}",
        json={"name": "Renamed webhook"},
        headers=_auth(owner_token),
    )
    db.refresh(trigger)
    assert trigger.webhook_token == url_response.json()["webhook_path"].removeprefix("webhooks/")


def test_webhook_enqueues_payload_only_while_workflow_is_active(client, db, monkeypatch):
    owner_token, workflow = _create_webhook_workflow(client, "webhook-active@example.com")
    trigger = db.query(Trigger).filter_by(workflow_id=uuid.UUID(workflow['id'])).one()
    received = {}

    async def fake_enqueue(_db, **kwargs):
        received.update(kwargs)
        return SimpleNamespace(
            id=uuid.uuid4(),
            status=ExecutionStatus.QUEUED,
            workflow_id=uuid.UUID(workflow["id"]),
            created_at=datetime.now(UTC),
        )

    monkeypatch.setattr(execution_service, "enqueue_execution", fake_enqueue)
    payload = {"event": "new_order", "order_id": 42}

    inactive_response = client.post(
        f"/api/v1/webhooks/{trigger.webhook_token}",
        json=payload,
    )
    assert inactive_response.status_code == 409

    activate_response = client.post(
        f"/api/v1/workflows/{workflow['id']}/activate",
        headers=_auth(owner_token),
    )
    assert activate_response.status_code == 200
    db.refresh(trigger)
    assert trigger.is_active is True

    webhook_response = client.post(
        f"/api/v1/webhooks/{trigger.webhook_token}",
        json=payload,
    )
    assert webhook_response.status_code == 202
    assert webhook_response.json()["workflow_id"] == workflow["id"]
    assert webhook_response.json()["status"] == "queued"
    assert received["trigger_type"] == "webhook_trigger"
    assert received["input_data"] == payload

    deactivate_response = client.post(
        f"/api/v1/workflows/{workflow['id']}/deactivate",
        headers=_auth(owner_token),
    )
    assert deactivate_response.status_code == 200
    db.refresh(trigger)
    assert trigger.is_active is False

    disabled_response = client.post(
        f"/api/v1/webhooks/{trigger.webhook_token}",
        json=payload,
    )
    assert disabled_response.status_code == 409


def test_removing_webhook_trigger_removes_provisioned_token(client, db):
    owner_token, workflow = _create_webhook_workflow(client, "webhook-remove@example.com")
    trigger = db.query(Trigger).filter_by(workflow_id=uuid.UUID(workflow['id'])).one()
    assert trigger.type == TriggerType.WEBHOOK

    manual_graph = {
        "nodes": [{"id": "manual", "type": "manual_trigger", "config": {}}],
        "edges": [],
    }
    response = client.put(
        f"/api/v1/workflows/{workflow['id']}",
        json={"graph": manual_graph},
        headers=_auth(owner_token),
    )

    assert response.status_code == 200
    assert db.query(Trigger).filter_by(workflow_id=uuid.UUID(workflow['id'])).count() == 0
