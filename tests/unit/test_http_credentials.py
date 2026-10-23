from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from app.engine.runner import run_workflow
from app.models.credential import Credential
from app.models.execution import ExecutionStatus, NodeExecution
from app.models.user import User
from app.models.workflow import Workflow
from app.repositories.execution_repo import create_execution
from app.services.credential_service import encrypt_data


@pytest.mark.parametrize(
    ("credential_type", "credential_data", "node_auth", "expected_header"),
    [
        (
            "api_key",
            {"api_key": "e2e-test-secret"},
            {"api_key_header": "Authorization", "api_key_prefix": "Bearer "},
            "Bearer e2e-test-secret",
        ),
        (
            "http_header",
            {"X-API-Key": "e2e-test-secret"},
            {},
            "e2e-test-secret",
        ),
    ],
)
def test_http_node_uses_owned_encrypted_credential_and_redacts_persisted_output(
    db, monkeypatch, credential_type, credential_data, node_auth, expected_header
):
    secret = "e2e-test-secret"
    user = User(email=f"http-credential-{uuid.uuid4()}@example.com", hashed_password="x")
    db.add(user)
    db.flush()

    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr("app.services.credential_service._get_fernet", lambda: fernet)
    credential = Credential(
        user_id=user.id,
        name="HTTP test credential",
        type=credential_type,
        encrypted_data=encrypt_data(credential_data),
    )
    db.add(credential)
    db.flush()
    assert secret.encode() not in credential.encrypted_data

    graph = {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "config": {}},
            {
                "id": "request",
                "type": "http_request",
                "config": {
                    "url": "https://example.com/private",
                    "method": "GET",
                    "credential_id": str(credential.id),
                    "credential_type": credential_type,
                    **node_auth,
                },
            },
        ],
        "edges": [{"id": "edge", "source": "trigger", "target": "request"}],
    }
    workflow = Workflow(user_id=user.id, name="HTTP credential test", graph=graph)
    db.add(workflow)
    db.flush()
    execution = create_execution(db, workflow.id, user.id, "manual_trigger")

    response = MagicMock()
    response.status_code = 200
    response.is_success = True
    response.headers = {
        "content-type": "application/json",
        "set-cookie": f"session={secret}",
    }
    response.content = json.dumps({"echo": expected_header, "api_key": secret}).encode()
    response.json.return_value = {"echo": expected_header, "api_key": secret}
    request_mock = MagicMock(return_value=response)
    client_context = MagicMock()
    client_context.__enter__.return_value.request = request_mock
    client_options = {}

    def fake_client(**kwargs):
        client_options.update(kwargs)
        return client_context

    monkeypatch.setattr("app.integrations.http_request._check_ssrf", lambda _url: None)
    monkeypatch.setattr("app.integrations.http_request.httpx.Client", fake_client)

    run_workflow(db, execution.id)

    db.refresh(execution)
    http_node_execution = (
        db.query(NodeExecution)
        .filter_by(execution_id=execution.id, node_id="request")
        .one()
    )
    assert execution.status == ExecutionStatus.SUCCESS
    assert client_options["follow_redirects"] is False
    assert request_mock.call_args.kwargs["headers"][
        "Authorization" if credential_type == "api_key" else "X-API-Key"
    ] == expected_header
    assert "set-cookie" not in {key.lower() for key in http_node_execution.output["headers"]}
    persisted_output = json.dumps(http_node_execution.output)
    assert secret not in persisted_output
    assert "[REDACTED]" in persisted_output


def test_http_node_rejects_credentials_owned_by_another_user(db, monkeypatch):
    from app.engine.context import ExecutionContext
    from app.engine.node_executor import execute_node

    credential_owner = User(email="http-owner@example.com", hashed_password="x")
    workflow_owner = User(email="http-other@example.com", hashed_password="x")
    db.add_all([credential_owner, workflow_owner])
    db.flush()
    fernet = Fernet(Fernet.generate_key())
    monkeypatch.setattr("app.services.credential_service._get_fernet", lambda: fernet)
    credential = Credential(
        user_id=credential_owner.id,
        name="Private key",
        type="api_key",
        encrypted_data=encrypt_data({"api_key": "hidden"}),
    )
    db.add(credential)
    db.flush()
    context = ExecutionContext(
        execution_id=str(uuid.uuid4()),
        workflow_graph={"nodes": [], "edges": []},
        db=db,
        user_id=workflow_owner.id,
    )
    with pytest.raises(ValueError, match="Credential not found"):
        execute_node(
            {
                "id": "request",
                "type": "http_request",
                "config": {
                    "url": "https://example.com",
                    "method": "GET",
                    "credential_id": str(credential.id),
                    "credential_type": "api_key",
                },
            },
            context,
        )
