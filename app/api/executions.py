"""
Execution endpoints:

  POST   /workflows/{id}/executions         → manual trigger (202 Accepted)
  GET    /executions                         → list all executions (paginated)
  GET    /executions/{execution_id}          → get one execution with node logs
  POST   /executions/{execution_id}/cancel   → cancel a queued/running execution
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.execution import ExecutionStatus
from app.models.user import User
from app.repositories import execution_repo
from app.schemas.execution import (
    ExecutionEnqueuedRead,
    ExecutionList,
    ExecutionRead,
    ManualTriggerRequest,
)
from app.services import execution_service
from app.triggers.manual import fire_manual_trigger

router = APIRouter(tags=["executions"])


@router.post(
    "/workflows/{workflow_id}/executions",
    response_model=ExecutionEnqueuedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger a workflow execution",
)
async def trigger_execution(
    workflow_id: uuid.UUID,
    body: ManualTriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionEnqueuedRead:
    execution = await fire_manual_trigger(
        db,
        workflow_id=workflow_id,
        user_id=current_user.id,
        input_data=body.input_data,
    )
    return ExecutionEnqueuedRead(
        execution_id=execution.id,
        status=execution.status,
        workflow_id=execution.workflow_id,
        created_at=execution.created_at,
    )


@router.get(
    "/executions",
    response_model=ExecutionList,
    summary="List executions for the current user",
)
def list_executions(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    workflow_id: uuid.UUID | None = None,
    execution_status: ExecutionStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionList:
    items, total = execution_repo.list_by_user(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        workflow_id=workflow_id,
        status=execution_status,
    )
    return ExecutionList(items=items, total=total, skip=skip, limit=limit)  # type: ignore[arg-type]


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionRead,
    summary="Get a single execution with its node logs",
)
def get_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionRead:
    execution = execution_repo.get_by_id(db, execution_id, current_user.id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution  # type: ignore[return-value]


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionRead,
    summary="Cancel a queued or running execution",
)
def cancel_execution(
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExecutionRead:
    execution = execution_service.cancel_execution(db, execution_id, current_user.id)
    return execution  # type: ignore[return-value]
