"""Align execution status columns with the SQLAlchemy PostgreSQL enums.

This migration is intentionally forward-only. It refuses unknown schema shapes or
status values before changing anything, and PostgreSQL transactional DDL keeps a
failed conversion from leaving a partial schema behind.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_execution_status_enums"
down_revision = "0002_trigger_event_idempotency"
branch_labels = None
depends_on = None

WORKFLOW_STATUS_LABELS = ("QUEUED", "RUNNING", "SUCCESS", "FAILED", "CANCELLED")
NODE_STATUS_LABELS = ("PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED")


def _validate_legacy_schema(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    expected = {
        "workflow_executions": ("'queued'::character varying",),
        "node_executions": (None,),
    }

    for table_name, (expected_default,) in expected.items():
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        status = columns.get("status")
        if status is None:
            raise RuntimeError(f"Cannot migrate: {table_name}.status is missing")
        if not isinstance(status["type"], sa.String) or isinstance(status["type"], sa.Enum):
            raise RuntimeError(
                f"Cannot migrate: expected {table_name}.status to be VARCHAR, "
                f"found {status['type']}"
            )
        if status["type"].length != 20 or status["nullable"]:
            raise RuntimeError(
                f"Cannot migrate: {table_name}.status does not match the 0001 schema"
            )
        if status.get("default") != expected_default:
            raise RuntimeError(
                f"Cannot migrate: unexpected default on {table_name}.status: "
                f"{status.get('default')!r}"
            )

    existing_enums = {
        enum["name"] for enum in inspector.get_enums(schema="public")
    }
    conflicting = existing_enums.intersection({"executionstatus", "nodeexecutionstatus"})
    if conflicting:
        raise RuntimeError(
            "Cannot migrate: enum type name already exists: "
            + ", ".join(sorted(conflicting))
        )


def _validate_status_values(bind: sa.Connection) -> None:
    allowed_workflow = tuple(label.lower() for label in WORKFLOW_STATUS_LABELS)
    allowed_nodes = tuple(label.lower() for label in NODE_STATUS_LABELS)

    checks = (
        ("workflow_executions", allowed_workflow),
        ("node_executions", allowed_nodes),
    )
    for table_name, allowed in checks:
        allowed_sql = ", ".join("'" + label + "'" for label in allowed)
        unknown = bind.execute(
            sa.text(
                f"SELECT DISTINCT status FROM {table_name} "
                f"WHERE status IS NULL OR lower(status) NOT IN ({allowed_sql}) "
                "ORDER BY status"
            )
        ).scalars().all()
        if unknown:
            raise RuntimeError(
                f"Cannot migrate: unknown {table_name}.status value(s): {unknown!r}"
            )


def _case_mapping(labels: tuple[str, ...]) -> str:
    clauses = " ".join(
        f"WHEN '{label.lower()}' THEN '{label}'" for label in labels
    )
    return f"CASE lower(status) {clauses} END"


def upgrade() -> None:
    bind = op.get_bind()
    _validate_legacy_schema(bind)
    _validate_status_values(bind)

    workflow_enum = postgresql.ENUM(
        *WORKFLOW_STATUS_LABELS,
        name="executionstatus",
        create_type=False,
    )
    node_enum = postgresql.ENUM(
        *NODE_STATUS_LABELS,
        name="nodeexecutionstatus",
        create_type=False,
    )
    postgresql.ENUM(*WORKFLOW_STATUS_LABELS, name="executionstatus").create(bind)
    postgresql.ENUM(*NODE_STATUS_LABELS, name="nodeexecutionstatus").create(bind)

    # Drop the lowercase legacy default before the column type conversion.
    op.execute(
        "ALTER TABLE workflow_executions "
        "ALTER COLUMN status DROP DEFAULT"
    )
    op.alter_column(
        "workflow_executions",
        "status",
        existing_type=sa.String(length=20),
        type_=workflow_enum,
        existing_nullable=False,
        postgresql_using=f"{_case_mapping(WORKFLOW_STATUS_LABELS)}::executionstatus",
    )
    op.alter_column(
        "node_executions",
        "status",
        existing_type=sa.String(length=20),
        type_=node_enum,
        existing_nullable=False,
        postgresql_using=f"{_case_mapping(NODE_STATUS_LABELS)}::nodeexecutionstatus",
    )
    op.execute(
        "ALTER TABLE workflow_executions "
        "ALTER COLUMN status SET DEFAULT 'QUEUED'::executionstatus"
    )


def downgrade() -> None:
    raise NotImplementedError("Revision 0003 is forward-only; downgrade is not supported")
