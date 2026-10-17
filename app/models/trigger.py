import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class TriggerType(enum.StrEnum):
    MANUAL = "manual_trigger"
    WEBHOOK = "webhook_trigger"
    SCHEDULE = "schedule_trigger"
    GMAIL = "gmail_trigger"
    TELEGRAM = "telegram_trigger"


class Trigger(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "triggers"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # Type: manual, webhook, schedule, gmail, telegram
    type: Mapped[TriggerType] = mapped_column(
        Enum(
            TriggerType,
            name="triggertype",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # Webhook-specific
    webhook_token: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    # HMAC secret for webhook signature verification (stored encrypted via Fernet)
    webhook_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Schedule-specific
    cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="trigger")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Trigger id={self.id} type={self.type!r} workflow_id={self.workflow_id}>"
