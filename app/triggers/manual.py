"""
Manual trigger: user-initiated workflow execution via the API.

Validates the workflow is active, then delegates to execution_service
to create the execution record and enqueue it.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.execution import WorkflowExecution
from app.repositories import workflow_repo
from app.services import execution_service


async def fire_manual_trigger(
    db: Session,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    input_data: dict[str, Any] | None = None,
) -> WorkflowExecution:
    """
    Enqueues a manual execution for *workflow_id*.
    Raises 404 if the workflow doesn't exist, 409 if it's inactive.
    """
    workflow = workflow_repo.get_by_id(db, workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    if not workflow.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow is not active. Activate it before triggering.",
        )

    return await execution_service.enqueue_execution(
        db,
        workflow_id=workflow_id,
        user_id=user_id,
        trigger_type="manual_trigger",
        input_data=input_data or {},
    )
