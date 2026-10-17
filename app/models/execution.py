import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKey


class ExecutionStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowExecution(UUIDPrimaryKey, Base):
    __tablename__ = "workflow_executions"
    __table_args__ = (Index(
        "uq_workflow_executions_trigger_event_key", "trigger_event_key", unique=True
    ),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus),
        nullable=False,
        default=ExecutionStatus.QUEUED,
        server_default=ExecutionStatus.QUEUED.name,
    )
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_event_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Input data passed at trigger time (e.g. webhook payload, manual input_data)
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="executions")  # noqa: F821
    node_executions: Mapped[list["NodeExecution"]] = relationship(
        "NodeExecution", back_populates="execution", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WorkflowExecution id={self.id} status={self.status}>"


class NodeExecution(UUIDPrimaryKey, Base):
    __tablename__ = "node_executions"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # node_id is the string ID within the workflow graph JSON (not a DB foreign key)
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[NodeExecutionStatus] = mapped_column(
        Enum(NodeExecutionStatus), nullable=False
    )
    # Output stored as JSONB — never store raw secrets here
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    execution: Mapped["WorkflowExecution"] = relationship(
        "WorkflowExecution", back_populates="node_executions"
    )

    def __repr__(self) -> str:
        return f"<NodeExecution node_id={self.node_id!r} status={self.status}>"
