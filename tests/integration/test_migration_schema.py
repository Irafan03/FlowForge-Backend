"""Schema contract checks for PostgreSQL databases provisioned by Alembic."""

from __future__ import annotations

from sqlalchemy import Enum, inspect

from app.models.execution import WorkflowExecution
from app.models.trigger import Trigger, TriggerType
from app.models.user import User
from app.models.workflow import Workflow


def test_alembic_schema_matches_orm(postgres_engine):
    inspector = inspect(postgres_engine)

    with postgres_engine.connect() as connection:
        revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
    assert revision == "0004_trigger_type_alignment"

    postgres_enums = {
        item["name"]: item["labels"] for item in inspector.get_enums(schema="public")
    }
    assert postgres_enums["triggertype"] == [item.value for item in TriggerType]
    assert isinstance(Trigger.__table__.c.type.type, Enum)
    assert Trigger.__table__.c.type.type.name == "triggertype"
    assert Trigger.__table__.c.config.server_default is not None
    assert Trigger.__table__.c.is_active.server_default is not None

    trigger_columns = {
        column["name"]: column for column in inspector.get_columns("triggers")
    }
    assert trigger_columns["type"]["type"].name == "triggertype"
    assert trigger_columns["config"]["default"] is not None
    assert trigger_columns["is_active"]["default"] == "true"

    workflow_columns = {
        column["name"]: column for column in inspector.get_columns("workflows")
    }
    assert workflow_columns["graph"]["default"] is not None
    assert workflow_columns["is_active"]["default"] == "false"
    assert Workflow.__table__.c.graph.server_default is not None
    assert Workflow.__table__.c.is_active.server_default is not None

    user_columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert user_columns["is_active"]["default"] == "true"
    assert User.__table__.c.is_active.server_default is not None

    execution_columns = {
        column["name"]: column
        for column in inspector.get_columns("workflow_executions")
    }
    assert "queued" in (execution_columns["status"]["default"] or "").lower()
    assert WorkflowExecution.__table__.c.status.server_default is not None
    assert WorkflowExecution.__table__.c.created_at.server_default is not None

    assert "ix_users_email" not in {
        item["name"] for item in inspector.get_indexes("users")
    }
    assert "ix_triggers_webhook_token" not in {
        item["name"] for item in inspector.get_indexes("triggers")
    }
    assert any(
        item["column_names"] == ["email"]
        for item in inspector.get_unique_constraints("users")
    )
    assert any(
        item["column_names"] == ["webhook_token"]
        for item in inspector.get_unique_constraints("triggers")
    )
