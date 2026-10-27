from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Supported node types in Phase 1
NODE_TYPES = Literal[
    "manual_trigger",
    "webhook_trigger",
    "schedule_trigger",
    "gmail_trigger",
    "telegram_trigger",
    "set_data",
    "if_condition",
    "http_request",
    "gmail_send",
    "telegram_send",
    "ml_prediction",
    "ai_agent",
    "google_sheets_append",
]


class NodePosition(BaseModel):
    x: float = 0.0
    y: float = 0.0


class NodeDefinition(BaseModel):
    """A single node in the workflow graph."""

    id: str = Field(..., min_length=1, max_length=255)
    type: NODE_TYPES
    name: str | None = Field(None, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    position: NodePosition = Field(default_factory=NodePosition)


class EdgeDefinition(BaseModel):
    """A directed edge between two nodes."""

    id: str | None = None
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    # For IF nodes the source_handle is "true" or "false"
    source_handle: str | None = None
    target_handle: str | None = None


class WorkflowGraph(BaseModel):
    """The complete DAG stored in workflow.graph."""

    nodes: list[NodeDefinition] = Field(..., min_length=1)
    edges: list[EdgeDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_no_duplicate_node_ids(self) -> "WorkflowGraph":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate node IDs found in graph")
        return self
