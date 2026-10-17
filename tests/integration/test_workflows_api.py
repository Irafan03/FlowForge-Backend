"""
Integration smoke tests for the workflows API.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str = "user@example.com") -> str:
    """Helper: register + login and return Bearer token."""
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


MINIMAL_GRAPH = {
    "nodes": [
        {"id": "t1", "type": "manual_trigger", "config": {}},
        {"id": "s1", "type": "set_data", "config": {"fields": [{"key": "x", "value": 1}]}},
    ],
    "edges": [{"id": "e1", "source": "t1", "target": "s1"}],
}

def _telegram_graph(config: dict) -> dict:
    return {
        "nodes": [{"id": "tg1", "type": "telegram_trigger", "config": config}],
        "edges": [],
    }


class TestWorkflowCRUD:
    def test_create_workflow(self, client: TestClient):
        token = _register_and_login(client, "wf1@example.com")
        resp = client.post(
            "/api/v1/workflows",
            json={"name": "My Flow", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Flow"
        assert data["is_active"] is False
        assert "id" in data

    def test_list_workflows_empty(self, client: TestClient):
        token = _register_and_login(client, "wf2@example.com")
        resp = client.get("/api/v1/workflows", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_list_workflows_after_create(self, client: TestClient):
        token = _register_and_login(client, "wf3@example.com")
        client.post(
            "/api/v1/workflows",
            json={"name": "Flow A", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        resp = client.get("/api/v1/workflows", headers=_auth(token))
        assert resp.json()["total"] == 1

    def test_get_workflow(self, client: TestClient):
        token = _register_and_login(client, "wf4@example.com")
        create_resp = client.post(
            "/api/v1/workflows",
            json={"name": "Flow B", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        wf_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/workflows/{wf_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == wf_id

    def test_get_workflow_not_found(self, client: TestClient):
        token = _register_and_login(client, "wf5@example.com")
        resp = client.get(
            "/api/v1/workflows/00000000-0000-0000-0000-000000000000",
            headers=_auth(token),
        )
        assert resp.status_code == 404

    def test_update_workflow(self, client: TestClient):
        token = _register_and_login(client, "wf6@example.com")
        create_resp = client.post(
            "/api/v1/workflows",
            json={"name": "Old Name", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        wf_id = create_resp.json()["id"]
        resp = client.put(
            f"/api/v1/workflows/{wf_id}",
            json={"name": "New Name"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_delete_workflow(self, client: TestClient):
        token = _register_and_login(client, "wf7@example.com")
        create_resp = client.post(
            "/api/v1/workflows",
            json={"name": "Disposable", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        wf_id = create_resp.json()["id"]
        del_resp = client.delete(f"/api/v1/workflows/{wf_id}", headers=_auth(token))
        assert del_resp.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/api/v1/workflows/{wf_id}", headers=_auth(token))
        assert get_resp.status_code == 404

    def test_activate_workflow(self, client: TestClient):
        token = _register_and_login(client, "wf8@example.com")
        create_resp = client.post(
            "/api/v1/workflows",
            json={"name": "Inactive", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        wf_id = create_resp.json()["id"]
        resp = client.post(f"/api/v1/workflows/{wf_id}/activate", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_deactivate_workflow(self, client: TestClient):
        token = _register_and_login(client, "wf9@example.com")
        create_resp = client.post(
            "/api/v1/workflows",
            json={"name": "Active", "graph": MINIMAL_GRAPH},
            headers=_auth(token),
        )
        wf_id = create_resp.json()["id"]
        client.post(f"/api/v1/workflows/{wf_id}/activate", headers=_auth(token))
        resp = client.post(f"/api/v1/workflows/{wf_id}/deactivate", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_user_isolation(self, client: TestClient):
        """User A cannot see User B's workflows."""
        token_a = _register_and_login(client, "userA@example.com")
        token_b = _register_and_login(client, "userB@example.com")

        create_resp = client.post(
            "/api/v1/workflows",
            json={"name": "Secret Flow", "graph": MINIMAL_GRAPH},
            headers=_auth(token_a),
        )
        wf_id = create_resp.json()["id"]

        resp_b = client.get(f"/api/v1/workflows/{wf_id}", headers=_auth(token_b))
        assert resp_b.status_code == 404

    def test_create_invalid_graph_rejected(self, client: TestClient):
        """Graph with cycle should be rejected at save time."""
        token = _register_and_login(client, "invalid@example.com")
        bad_graph = {
            "nodes": [
                {"id": "t1", "type": "manual_trigger", "config": {}},
                {"id": "n1", "type": "set_data", "config": {"fields": []}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "n1"},
                {"id": "e2", "source": "n1", "target": "t1"},  # cycle
            ],
        }
        resp = client.post(
            "/api/v1/workflows",
            json={"name": "Cyclic", "graph": bad_graph},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    def test_create_telegram_workflow_requires_allowed_chat_ids(self, client: TestClient):
        token = _register_and_login(client, "telegram-create-validation@example.com")
        resp = client.post(
            "/api/v1/workflows",
            json={
                "name": "Telegram Flow",
                "graph": _telegram_graph({"credential_id": "credential-id"}),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 422
        assert "allowed_chat_ids" in resp.json()["detail"]

    def test_create_telegram_workflow_validates_poll_interval(self, client: TestClient):
        token = _register_and_login(client, "telegram-interval-validation@example.com")
        resp = client.post(
            "/api/v1/workflows",
            json={
                "name": "Telegram Flow",
                "graph": _telegram_graph({
                    "credential_id": "credential-id",
                    "allowed_chat_ids": ["-100123"],
                    "polling_interval_seconds": 10,
                }),
            },
            headers=_auth(token),
        )
        assert resp.status_code == 422
        assert "polling_interval_seconds" in resp.json()["detail"]

    def test_update_telegram_workflow_validates_allowed_chat_ids(self, client: TestClient):
        token = _register_and_login(client, "telegram-update-validation@example.com")
        created = client.post(
            "/api/v1/workflows",
            json={
                "name": "Telegram Flow",
                "graph": _telegram_graph({
                    "credential_id": "credential-id",
                    "allowed_chat_ids": ["123"],
                }),
            },
            headers=_auth(token),
        )
        assert created.status_code == 201
        workflow_id = created.json()["id"]

        resp = client.put(
            f"/api/v1/workflows/{workflow_id}",
            json={"graph": _telegram_graph({
                "credential_id": "credential-id",
                "allowed_chat_ids": [],
            })},
            headers=_auth(token),
        )
        assert resp.status_code == 422
        assert "allowed_chat_ids" in resp.json()["detail"]
