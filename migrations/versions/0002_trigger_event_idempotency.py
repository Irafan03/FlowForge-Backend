"""Add an idempotency key for Gmail and Telegram poll events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_trigger_event_idempotency"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflow_executions", sa.Column("trigger_event_key", sa.String(512), nullable=True))
    op.create_index(
        "uq_workflow_executions_trigger_event_key", "workflow_executions",
        ["trigger_event_key"], unique=True,
    )
    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nonce", sa.String(36), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_states_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("uq_workflow_executions_trigger_event_key", table_name="workflow_executions")
    op.drop_column("workflow_executions", "trigger_event_key")
