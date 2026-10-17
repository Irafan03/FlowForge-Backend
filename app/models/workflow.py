import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Workflow(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "workflows"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # graph is the full JSON DAG: {"nodes": [...], "edges": [...]}
    graph: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="workflows")  # noqa: F821
    executions: Mapped[list["WorkflowExecution"]] = relationship(  # noqa: F821
        "WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan"
    )
    trigger: Mapped["Trigger | None"] = relationship(  # noqa: F821
        "Trigger", back_populates="workflow", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Workflow id={self.id} name={self.name!r}>"
