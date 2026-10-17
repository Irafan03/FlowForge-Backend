"""
Execution service: creates WorkflowExecution records and enqueues them
into the ARQ Redis queue for the worker to pick up.
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.execution import ExecutionStatus, WorkflowExecution
from app.repositories import execution_repo, workflow_repo


async def enqueue_execution(
    db: Session,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    trigger_type: str,
    input_data: dict[str, Any] | None = None,
    trigger_event_key: str | None = None,
) -> WorkflowExecution:
    """
    1. Verify the workflow exists and belongs to this user.
    2. Create a WorkflowExecution record (status=queued).
    3. Push execution_id onto the ARQ queue.
    Returns the execution record immediately (202 Accepted pattern).
    """
    workflow = workflow_repo.get_by_id(db, workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    execution = execution_repo.create_execution(
        db,
        workflow_id=workflow_id,
        user_id=user_id,
        trigger_type=trigger_type,
        input_data=input_data or {},
        trigger_event_key=trigger_event_key,
    )

    await _enqueue_arq(str(execution.id))

    return execution


async def enqueue_external_execution(
    db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID, trigger_type: str,
    input_data: dict[str, Any], event_key: str,
) -> WorkflowExecution:
    """Idempotently create a provider event execution and ensure queued jobs are enqueued."""
    workflow = workflow_repo.get_by_id(db, workflow_id, user_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    execution = _find_event_execution(db, event_key, workflow_id, user_id)
    if execution is None:
        try:
            execution = execution_repo.create_execution(
                db, workflow_id, user_id, trigger_type, input_data, trigger_event_key=event_key
            )
        except IntegrityError:
            # Concurrent pollers can both observe no row. The unique index decides the
            # winner; clear the failed transaction and recover that committed execution.
            db.rollback()
            execution = _find_event_execution(db, event_key, workflow_id, user_id)
            if execution is None:
                # This was a different integrity problem, not an idempotency race.
                raise
    if execution.status == ExecutionStatus.QUEUED:
        await _enqueue_arq(str(execution.id))
    return execution


def _find_event_execution(
    db: Session,
    event_key: str,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
) -> WorkflowExecution | None:
    execution = (
        db.query(WorkflowExecution)
        .filter(WorkflowExecution.trigger_event_key == event_key)
        .first()
    )
    if execution is not None and (
        execution.workflow_id != workflow_id or execution.user_id != user_id
    ):
        raise RuntimeError("Trigger event idempotency key is already used by another workflow")
    return execution


async def _enqueue_arq(execution_id: str) -> None:
    """
    Push the execution_id onto the ARQ queue using a shared pool.

    The pool is obtained from the app-level singleton (set during startup).
    Falls back to creating a one-shot pool if the singleton is not yet
    initialized (e.g. during tests or CLI usage).
    """
    from arq.connections import ArqRedis, RedisSettings

    from app.config.settings import get_settings

    pool: ArqRedis | None = _get_shared_pool()

    if pool is None:
        # Fallback: create a short-lived pool (used in tests / standalone scripts)
        from arq import create_pool

        settings = get_settings()
        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        try:
            await pool.enqueue_job("run_execution", execution_id, _job_id=f"run_execution:{execution_id}")
        finally:
            await pool.aclose()
        return

    await pool.enqueue_job("run_execution", execution_id, _job_id=f"run_execution:{execution_id}")


# ---------------------------------------------------------------------------
# Shared pool management
# The FastAPI lifespan sets this once on startup and clears it on shutdown.
# This avoids opening a new Redis connection on every single trigger.
# ---------------------------------------------------------------------------

_shared_pool: Any = None  # ArqRedis | None


def _get_shared_pool() -> Any:
    return _shared_pool


def set_shared_pool(pool: Any) -> None:
    """Called from app lifespan (startup) to register the shared ARQ pool."""
    global _shared_pool
    _shared_pool = pool


def clear_shared_pool() -> None:
    """Called from app lifespan (shutdown)."""
    global _shared_pool
    _shared_pool = None


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

def cancel_execution(
    db: Session, execution_id: uuid.UUID, user_id: uuid.UUID
) -> WorkflowExecution:
    """
    Mark an execution as CANCELLED in the DB.

    The ARQ job may already be in the queue; the runner checks the DB status
    at the very start of run_workflow() and returns early if CANCELLED,
    so the job will be a no-op when the worker picks it up.
    """
    execution = execution_repo.get_by_id(db, execution_id, user_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    if execution.status in (
        ExecutionStatus.SUCCESS,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel execution with status '{execution.status.value}'",
        )
    return execution_repo.update_status(db, execution, ExecutionStatus.CANCELLED)
