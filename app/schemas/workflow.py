import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.node import WorkflowGraph


# ── Request schemas ────────────────────────────────────────────────────────────

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    graph: WorkflowGraph


class WorkflowUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    graph: WorkflowGraph | None = None


# ── Response schemas ───────────────────────────────────────────────────────────

class WorkflowRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    graph: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowList(BaseModel):
    items: list[WorkflowRead]
    total: int
    skip: int
    limit: int


class WorkflowActivationRead(BaseModel):
    id: uuid.UUID
    is_active: bool

    model_config = {"from_attributes": True}


class WorkflowWebhookURLRead(BaseModel):
    """Webhook path relative to the configured API base URL."""

    webhook_path: str
