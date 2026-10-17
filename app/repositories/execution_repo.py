import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.execution import (
    ExecutionStatus,
    NodeExecution,
    NodeExecutionStatus,
    WorkflowExecution,
)


def create_execution(
    db: Session,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    trigger_type: str,
    input_data: dict[str, Any] | None = None,
    trigger_event_key: str | None = None,
) -> WorkflowExecution:
    execution = WorkflowExecution(
        workflow_id=workflow_id,
        user_id=user_id,
        status=ExecutionStatus.QUEUED,
        trigger_type=trigger_type,
        input_data=input_data or {},
        trigger_event_key=trigger_event_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def get_by_id(
    db: Session, execution_id: uuid.UUID, user_id: uuid.UUID
) -> WorkflowExecution | None:
    """Always filter by user_id."""
    return (
        db.query(WorkflowExecution)
        .options(selectinload(WorkflowExecution.node_executions))
        .filter(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.user_id == user_id,
        )
        .first()
    )


def get_by_id_internal(db: Session, execution_id: uuid.UUID) -> WorkflowExecution | None:
    """No user filter — used by the worker after the execution is already owned."""
    return (
        db.query(WorkflowExecution)
        .options(selectinload(WorkflowExecution.node_executions))
        .filter(WorkflowExecution.id == execution_id)
        .first()
    )


def list_by_user(
    db: Session,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    workflow_id: uuid.UUID | None = None,
    status: ExecutionStatus | None = None,
) -> tuple[list[WorkflowExecution], int]:
    q = (
        db.query(WorkflowExecution)
        .options(selectinload(WorkflowExecution.node_executions))
        .filter(WorkflowExecution.user_id == user_id)
    )
    if workflow_id:
        q = q.filter(WorkflowExecution.workflow_id == workflow_id)
    if status:
        q = q.filter(WorkflowExecution.status == status)
    total = q.with_entities(func.count()).scalar()
    items = q.order_by(WorkflowExecution.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def update_status(
    db: Session,
    execution: WorkflowExecution,
    status: ExecutionStatus,
    error: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    duration_ms: int | None = None,
) -> WorkflowExecution:
    execution.status = status
    if error is not None:
        execution.error = error
    if started_at is not None:
        execution.started_at = started_at
    if finished_at is not None:
        execution.finished_at = finished_at
    if duration_ms is not None:
        execution.duration_ms = duration_ms
    db.commit()
    db.refresh(execution)
    return execution


def create_node_execution(
    db: Session,
    execution_id: uuid.UUID,
    node_id: str,
    node_type: str,
    status: NodeExecutionStatus,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    duration_ms: int | None = None,
) -> NodeExecution:
    ne = NodeExecution(
        execution_id=execution_id,
        node_id=node_id,
        node_type=node_type,
        status=status,
        output=output,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )
    db.add(ne)
    db.commit()
    db.refresh(ne)
    return ne
