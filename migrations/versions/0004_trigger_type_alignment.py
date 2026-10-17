"""Align trigger type and redundant unique indexes with the ORM.

Revision ID: 0004_trigger_type_alignment
Revises: 0003_execution_status_enums
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_trigger_type_alignment"
down_revision: str | None = "0003_execution_status_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGER_TYPE_LABELS = (
    "manual_trigger",
    "webhook_trigger",
    "schedule_trigger",
    "gmail_trigger",
    "telegram_trigger",
)


def _validate_revision_0003(bind: sa.Connection) -> None:
    """Refuse an unexpected start point rather than guessing at schema shape."""
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names(schema="public"))
    if "alembic_version" not in tables:
        raise RuntimeError("Cannot migrate: alembic_version is missing")

    version = bind.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if version != "0003_execution_status_enums":
        raise RuntimeError(
            "Cannot migrate: expected Alembic revision 0003_execution_status_enums, "
            f"found {version!r}"
        )

    trigger_columns = {
        column["name"]: column for column in inspector.get_columns("triggers")
    }
    trigger_type = trigger_columns.get("type")
    if (
        trigger_type is None
        or not isinstance(trigger_type["type"], sa.String)
        or isinstance(trigger_type["type"], sa.Enum)
        or trigger_type["type"].length != 50
        or trigger_type["nullable"]
        or trigger_type.get("default") is not None
    ):
        raise RuntimeError(
            "Cannot migrate: expected triggers.type to be non-null VARCHAR(50) "
            "without a default, as created by revision 0001"
        )

    enum_names = {item["name"] for item in inspector.get_enums(schema="public")}
    if "triggertype" in enum_names:
        raise RuntimeError("Cannot migrate: public.triggertype already exists")

    expected_unique_keys = (
        ("users", "email", "ix_users_email"),
        ("triggers", "webhook_token", "ix_triggers_webhook_token"),
    )
    for table_name, column_name, index_name in expected_unique_keys:
        constraints = inspector.get_unique_constraints(table_name)
        if not any(item.get("column_names") == [column_name] for item in constraints):
            raise RuntimeError(
                f"Cannot migrate: {table_name}.{column_name} unique constraint is missing"
            )

        indexes = {item["name"]: item for item in inspector.get_indexes(table_name)}
        index = indexes.get(index_name)
        if (
            index is None
            or not index.get("unique")
            or index.get("column_names") != [column_name]
            or index.get("dialect_options", {}).get("postgresql_where") is not None
        ):
            raise RuntimeError(
                f"Cannot migrate: expected duplicate unique index {index_name} "
                f"on {table_name}.{column_name}"
            )


def _validate_trigger_values(bind: sa.Connection) -> None:
    allowed_values = ", ".join(f"'{label}'" for label in TRIGGER_TYPE_LABELS)
    unknown = bind.execute(
        sa.text(
            "SELECT DISTINCT type FROM triggers "
            f"WHERE type IS NULL OR type NOT IN ({allowed_values}) ORDER BY type"
        )
    ).scalars().all()
    if unknown:
        raise RuntimeError(
            f"Cannot migrate: unknown triggers.type value(s): {unknown!r}"
        )


def upgrade() -> None:
    bind = op.get_bind()
    _validate_revision_0003(bind)
    _validate_trigger_values(bind)

    trigger_enum = postgresql.ENUM(
        *TRIGGER_TYPE_LABELS,
        name="triggertype",
        create_type=False,
    )
    postgresql.ENUM(*TRIGGER_TYPE_LABELS, name="triggertype").create(bind)
    op.alter_column(
        "triggers",
        "type",
        existing_type=sa.String(length=50),
        type_=trigger_enum,
        existing_nullable=False,
        postgresql_using="type::text::triggertype",
    )

    # The unique constraints remain the canonical enforcement. These indexes
    # duplicate the constraints and are not declared by the cleaned ORM model.
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_triggers_webhook_token", table_name="triggers")


def downgrade() -> None:
    raise NotImplementedError("Revision 0004 is forward-only; downgrade is not supported")
