import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.execution import ExecutionStatus, NodeExecutionStatus


# ── Request schemas ────────────────────────────────────────────────────────────

class ManualTriggerRequest(BaseModel):
    """Optional input data passed when manually triggering a workflow."""
    input_data: dict[str, Any] = Field(default_factory=dict)


# ── Response schemas ───────────────────────────────────────────────────────────

class NodeExecutionRead(BaseModel):
    id: uuid.UUID
    node_id: str
    node_type: str
    status: NodeExecutionStatus
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None

    model_config = {"from_attributes": True}


class ExecutionRead(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    user_id: uuid.UUID
    status: ExecutionStatus
    trigger_type: str
    input_data: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    node_executions: list[NodeExecutionRead] = []

    model_config = {"from_attributes": True}


class ExecutionEnqueuedRead(BaseModel):
    """Minimal response immediately after enqueueing (202)."""
    execution_id: uuid.UUID
    status: ExecutionStatus
    workflow_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionList(BaseModel):
    items: list[ExecutionRead]
    total: int
    skip: int
    limit: int
