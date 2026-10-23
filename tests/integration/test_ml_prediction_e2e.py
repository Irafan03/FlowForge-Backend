"""Opt-in real FlowForge ML + PostgreSQL runner test.

Run with RUN_ML_E2E=1, TEST_DATABASE_URL pointing only at the dedicated
flowforge_test database, and FLOWFORGE_ML_URL pointing at the live ML API.
This deliberately uses no HTTP mocks and deletes only rows created here.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import delete, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, selectinload

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ML_E2E") != "1",
    reason="set RUN_ML_E2E=1 to run against the live ML API and test PostgreSQL",
)

MODEL_ID = "breast_cancer_logistic_regression"
# First row of sklearn.datasets.load_breast_cancer(as_frame=True).data, the
# dataset used by FlowForge-ML training. Keep this fixture independent of the
# backend's optional sklearn installation.
BREAST_CANCER_SAMPLE = {
    "mean radius": 17.99,
    "mean texture": 10.38,
    "mean perimeter": 122.8,
    "mean area": 1001.0,
    "mean smoothness": 0.1184,
    "mean compactness": 0.2776,
    "mean concavity": 0.3001,
    "mean concave points": 0.1471,
    "mean symmetry": 0.2419,
    "mean fractal dimension": 0.07871,
    "radius error": 1.095,
    "texture error": 0.9053,
    "perimeter error": 8.589,
    "area error": 153.4,
    "smoothness error": 0.006399,
    "compactness error": 0.04904,
    "concavity error": 0.05373,
    "concave points error": 0.01587,
    "symmetry error": 0.03003,
    "fractal dimension error": 0.006193,
    "worst radius": 25.38,
    "worst texture": 17.33,
    "worst perimeter": 184.6,
    "worst area": 2019.0,
    "worst smoothness": 0.1622,
    "worst compactness": 0.6656,
    "worst concavity": 0.7119,
    "worst concave points": 0.2654,
    "worst symmetry": 0.4601,
    "worst fractal dimension": 0.1189,
}


def _verified_database_url():
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("RUN_ML_E2E=1 requires TEST_DATABASE_URL; no DB was opened")

    url = make_url(raw_url)
    allowed_host_port = (
        (url.host in {"localhost", "127.0.0.1", "::1"} and url.port in {5433, 55432})
        or (url.host == "db_test" and url.port == 5432)
    )
    if not (
        url.drivername.startswith("postgresql")
        and url.username == "flowforge_test"
        and url.database == "flowforge_test"
        and allowed_host_port
    ):
        pytest.fail(
            "TEST_DATABASE_URL must target the dedicated flowforge_test database "
            "at an allowed test host and port; refusing to write"
        )
    return raw_url, url


def test_real_ml_runner_persists_prediction_in_postgres(request):
    """Run the true runner and HTTP client, then verify independent DB readback."""
    from sqlalchemy import create_engine

    raw_database_url, parsed_url = _verified_database_url()
    ml_url = os.environ.get("FLOWFORGE_ML_URL", "").rstrip("/")
    if ml_url != "http://127.0.0.1:8004":
        pytest.fail(
            "Set FLOWFORGE_ML_URL=http://127.0.0.1:8004 explicitly; refusing fallback"
        )

    # Verify the target database identity read-only before the PostgreSQL fixture
    # can initialize a fresh disposable instance or the test creates any rows.
    probe_engine = create_engine(raw_database_url, connect_args={"connect_timeout": 5})
    try:
        with probe_engine.connect() as connection:
            database_name, database_user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            assert database_name == "flowforge_test", "connected database is not flowforge_test"
            assert database_user == "flowforge_test", "connected user is not flowforge_test"
            if parsed_url.port == 5433:
                tables = set(inspect(connection).get_table_names(schema="public"))
                assert "alembic_version" in tables, (
                    "port 5433 must already have the test schema; refusing migration"
                )
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                assert revision == "0004_trigger_type_alignment", (
                    "test database must already be at Alembic head; refusing migration"
                )
    finally:
        probe_engine.dispose()

    # The shared fixture independently enforces the same test-only URL rules.
    postgres_engine = request.getfixturevalue("postgres_engine")

    health_response = httpx.get(f"{ml_url}/health", timeout=5)
    health_response.raise_for_status()
    health = health_response.json()
    assert health.get("ready") is True and health.get("model_loaded") is True, health

    models_response = httpx.get(f"{ml_url}/models", timeout=5)
    models_response.raise_for_status()
    available_models = models_response.json().get("models", [])
    model = next((item for item in available_models if item.get("model_id") == MODEL_ID), None)
    assert model is not None, f"model {MODEL_ID!r} is unavailable: {available_models!r}"
    assert model.get("feature_count") == 30
    assert set(model.get("features", [])) == set(BREAST_CANCER_SAMPLE)

    from app.config.settings import get_settings
    from app.engine.runner import run_workflow
    from app.models.execution import (
        ExecutionStatus,
        NodeExecution,
        NodeExecutionStatus,
        WorkflowExecution,
    )
    from app.models.user import User
    from app.models.workflow import Workflow

    get_settings.cache_clear()
    assert get_settings().FLOWFORGE_ML_URL.rstrip("/") == ml_url

    scenario_id = uuid.uuid4()
    user_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    execution_id = uuid.uuid4()
    email = f"ml-e2e-{scenario_id}@test.invalid"
    graph = {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "config": {}},
            {
                "id": "ml",
                "type": "ml_prediction",
                "config": {"model_id": MODEL_ID, "input": BREAST_CANCER_SAMPLE},
            },
            {
                "id": "after",
                "type": "set_data",
                "config": {"fields": [{"key": "label", "value": "{{ml.prediction}}"}]},
            },
        ],
        "edges": [
            {"id": "edge-trigger-ml", "source": "trigger", "target": "ml"},
            {"id": "edge-ml-after", "source": "ml", "target": "after"},
        ],
    }

    with Session(postgres_engine, expire_on_commit=False) as db:
        user = User(
            id=user_id,
            email=email,
            hashed_password="e2e-only-not-a-login-password",
        )
        workflow = Workflow(
            id=workflow_id,
            user_id=user_id,
            name=f"Real ML E2E {scenario_id}",
            graph=graph,
            is_active=True,
        )
        execution = WorkflowExecution(
            id=execution_id,
            workflow_id=workflow_id,
            user_id=user_id,
            status=ExecutionStatus.QUEUED,
            trigger_type="manual_trigger",
            input_data={},
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([user, workflow, execution])
        db.commit()

    runner_error = None
    try:
        with Session(postgres_engine, expire_on_commit=False) as db:
            run_workflow(db, execution_id)
    except Exception as exc:  # retain readback and scoped cleanup on runner failures
        runner_error = repr(exc)

    # Read through a fresh SQLAlchemy session to prove committed persistence.
    try:
        with Session(postgres_engine) as verify_db:
            persisted = (
                verify_db.query(WorkflowExecution)
                .options(selectinload(WorkflowExecution.node_executions))
                .filter(WorkflowExecution.id == execution_id)
                .one_or_none()
            )
            assert persisted is not None, "workflow execution was not persisted"
            final_status = persisted.status
            nodes = {node.node_id: node for node in persisted.node_executions}
            ml_node = nodes.get("ml")
            dependent_node = nodes.get("after")
            ml_output = ml_node.output if ml_node else None
            dependent_output = dependent_node.output if dependent_node else None

        assert runner_error is None, f"runner raised: {runner_error}"
        assert final_status == ExecutionStatus.SUCCESS
        assert ml_node is not None and ml_node.status == NodeExecutionStatus.SUCCESS
        assert ml_output is not None
        assert ml_output["model_id"] == MODEL_ID
        assert ml_output["prediction"] in model.get("labels", [])
        assert 0.0 <= ml_output["confidence"] <= 1.0
        assert set(ml_output["raw_output"]) == set(model.get("labels", []))
        assert sum(ml_output["raw_output"].values()) == pytest.approx(1.0, abs=1e-6)
        assert dependent_node is not None
        assert dependent_node.status == NodeExecutionStatus.SUCCESS
        assert dependent_output == {"label": ml_output["prediction"]}
        print(f'Persisted real ML node output: {ml_output}')
    finally:
        # Delete only this scenario's rows, and only after the independent readback.
        with Session(postgres_engine) as cleanup_db:
            cleanup_db.execute(
                delete(NodeExecution).where(NodeExecution.execution_id == execution_id)
            )
            cleanup_db.execute(
                delete(WorkflowExecution).where(WorkflowExecution.id == execution_id)
            )
            cleanup_db.execute(
                delete(Workflow).where(
                    Workflow.id == workflow_id,
                    Workflow.user_id == user_id,
                )
            )
            cleanup_db.execute(
                delete(User).where(User.id == user_id, User.email == email)
            )
            cleanup_db.commit()

        with Session(postgres_engine) as cleanup_check:
            assert cleanup_check.get(WorkflowExecution, execution_id) is None
            assert cleanup_check.get(Workflow, workflow_id) is None
            assert cleanup_check.get(User, user_id) is None

