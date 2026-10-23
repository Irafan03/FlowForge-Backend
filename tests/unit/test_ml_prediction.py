from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.engine.context import ExecutionContext
from app.engine.node_executor import NodeExecutionError, execute_node
from app.integrations.ml_prediction import execute_ml_prediction

MODEL = "breast_cancer_logistic_regression"
INPUT = {"mean radius": 17.99, "mean texture": 10.38}
OUTPUT = {
    "model_id": MODEL,
    "prediction": "malignant",
    "confidence": 0.98,
    "raw_output": {"malignant": 0.98, "benign": 0.02},
    "duration_ms": 1.2,
}


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.ml_prediction.get_settings",
        lambda: SimpleNamespace(FLOWFORGE_ML_URL="http://localhost:8001/"),
    )


def reply(data=OUTPUT, status=200, bad_json=False):
    return httpx.Response(
        status,
        json=data if not bad_json else None,
        content=b"bad" if bad_json else None,
        request=httpx.Request("POST", "http://localhost:8001/predict"),
    )


def client(response=None, error=None):
    mock = MagicMock()
    mock.__enter__.return_value = mock
    if error:
        mock.post.side_effect = error
    else:
        mock.post.return_value = response
    return patch("app.integrations.ml_prediction.httpx.Client", return_value=mock), mock


def config():
    return {"model_id": MODEL, "input": INPUT}


def test_success_sends_exact_request_and_returns_fields(settings):
    patcher, mock = client(reply())
    with patcher:
        result = execute_node(
            {"id": "ml", "type": "ml_prediction", "config": config()},
            ExecutionContext("e", {"nodes": [], "edges": []}),
        )
    mock.post.assert_called_once_with(
        "http://localhost:8001/predict", json={"model_id": MODEL, "input": INPUT}
    )
    assert result == OUTPUT


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"model_id": "", "input": INPUT}, "model_id"),
        ({"model_id": MODEL, "input": []}, "input"),
        ({**config(), "timeout_seconds": 0}, "timeout_seconds"),
    ],
)
def test_bad_config(body, error, settings):
    with pytest.raises(NodeExecutionError, match=error):
        execute_ml_prediction(body)


def test_http_timeout_connection_and_json_failures(settings):
    patcher, _ = client(reply({"detail": "unavailable"}, 503))
    with patcher, pytest.raises(NodeExecutionError, match="HTTP 503"):
        execute_ml_prediction(config())
    patcher, _ = client(error=httpx.ReadTimeout("late"))
    with patcher, pytest.raises(NodeExecutionError, match="timed out"):
        execute_ml_prediction(config())
    patcher, _ = client(
        error=httpx.ConnectError(
            "refused", request=httpx.Request("POST", "http://localhost:8001/predict")
        )
    )
    with patcher, pytest.raises(NodeExecutionError, match="connection error"):
        execute_ml_prediction(config())
    patcher, _ = client(reply(bad_json=True))
    with patcher, pytest.raises(NodeExecutionError, match="invalid JSON"):
        execute_ml_prediction(config())


def persist(db, graph):
    import uuid

    from app.models.execution import ExecutionStatus, WorkflowExecution
    from app.models.user import User
    from app.models.workflow import Workflow

    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db.add(user)
    db.flush()
    wf = Workflow(user_id=user.id, name="ML test", graph=graph, is_active=True)
    db.add(wf)
    db.flush()
    ex = WorkflowExecution(
        workflow_id=wf.id,
        user_id=user.id,
        status=ExecutionStatus.QUEUED,
        trigger_type="manual_trigger",
        input_data={},
        created_at=datetime.now(UTC),
    )
    db.add(ex)
    db.commit()
    return ex


def graph():
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "config": {}},
            {"id": "ml", "type": "ml_prediction", "config": config()},
            {
                "id": "after",
                "type": "set_data",
                "config": {"fields": [{"key": "label", "value": "{{ml.prediction}}"}]},
            },
        ],
        "edges": [{"source": "trigger", "target": "ml"}, {"source": "ml", "target": "after"}],
    }


def test_runner_persists_ml_output_and_context_for_next_node(db, settings):
    from app.engine.runner import run_workflow
    from app.models.execution import ExecutionStatus, NodeExecutionStatus

    patcher, _ = client(reply())
    with patcher:
        ex = persist(db, graph())
        run_workflow(db, ex.id)
    db.refresh(ex)
    nodes = {n.node_id: n for n in ex.node_executions}
    assert ex.status == ExecutionStatus.SUCCESS
    assert nodes["ml"].status == NodeExecutionStatus.SUCCESS and nodes["ml"].output == OUTPUT
    assert nodes["after"].output == {"label": "malignant"}


def test_runner_marks_failure_and_skips_dependent(db, settings):
    from app.engine.runner import run_workflow
    from app.models.execution import ExecutionStatus, NodeExecutionStatus

    patcher, _ = client(reply({"detail": "offline"}, 503))
    with patcher:
        ex = persist(db, graph())
        run_workflow(db, ex.id)
    db.refresh(ex)
    nodes = {n.node_id: n for n in ex.node_executions}
    assert ex.status == ExecutionStatus.FAILED
    assert nodes["ml"].status == NodeExecutionStatus.FAILED
    assert nodes["after"].status == NodeExecutionStatus.SKIPPED
