"""
Workflow CRUD endpoints:

  POST   /workflows                    → create
  GET    /workflows                    → list (paginated)
  GET    /workflows/{id}               → get one
  PUT    /workflows/{id}               → update
  DELETE /workflows/{id}               → delete
  POST   /workflows/{id}/activate      → set is_active=True
  POST   /workflows/{id}/deactivate    → set is_active=False
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.engine.validators import validate_graph
from app.models.trigger import Trigger, TriggerType
from app.models.user import User
from app.repositories import workflow_repo
from app.schemas.workflow import (
    WorkflowActivationRead,
    WorkflowCreate,
    WorkflowList,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowWebhookURLRead,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post(
    "",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workflow",
)
def create_workflow(
    body: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowRead:
    graph_dict = body.graph.model_dump(mode="python")
    validate_graph(graph_dict)
    workflow = workflow_repo.create(
        db,
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        graph=graph_dict,
    )
    return workflow  # type: ignore[return-value]


@router.get(
    "",
    response_model=WorkflowList,
    summary="List all workflows for the current user",
)
def list_workflows(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowList:
    items, total = workflow_repo.list_by_user(
        db, current_user.id, skip=skip, limit=limit, is_active=is_active
    )
    return WorkflowList(items=items, total=total, skip=skip, limit=limit)  # type: ignore[arg-type]


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRead,
    summary="Get a single workflow",
)
def get_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowRead:
    workflow = workflow_repo.get_by_id(db, workflow_id, current_user.id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow  # type: ignore[return-value]


@router.get(
    "/{workflow_id}/webhook-url",
    response_model=WorkflowWebhookURLRead,
    summary="Get the webhook path for a workflow",
)
def get_workflow_webhook_url(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowWebhookURLRead:
    workflow = workflow_repo.get_by_id(db, workflow_id, current_user.id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    trigger = (
        db.query(Trigger)
        .filter(
            Trigger.workflow_id == workflow.id,
            Trigger.type == TriggerType.WEBHOOK,
        )
        .first()
    )
    if not trigger or not trigger.webhook_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook trigger not found")

    return WorkflowWebhookURLRead(webhook_path=f"webhooks/{trigger.webhook_token}")


@router.put(
    "/{workflow_id}",
    response_model=WorkflowRead,
    summary="Update a workflow",
)
def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowRead:
    workflow = workflow_repo.get_by_id(db, workflow_id, current_user.id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    update_data = body.model_dump(exclude_unset=True)
    if "graph" in update_data:
        if body.graph is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Workflow graph cannot be null",
            )
        # model_dump returns nested dicts already when mode='python'
        graph_dict = body.graph.model_dump(mode="python")  # type: ignore[union-attr]
        validate_graph(graph_dict)
        update_data["graph"] = graph_dict

    workflow = workflow_repo.update(db, workflow, update_data)
    return workflow  # type: ignore[return-value]


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workflow",
)
def delete_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    workflow = workflow_repo.get_by_id(db, workflow_id, current_user.id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    workflow_repo.delete(db, workflow)


@router.post(
    "/{workflow_id}/activate",
    response_model=WorkflowActivationRead,
    summary="Activate a workflow",
)
def activate_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowActivationRead:
    workflow = workflow_repo.get_by_id(db, workflow_id, current_user.id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    # Validate graph is still valid before activating
    validate_graph(workflow.graph)
    workflow = workflow_repo.set_active(db, workflow, True)
    return workflow  # type: ignore[return-value]


@router.post(
    "/{workflow_id}/deactivate",
    response_model=WorkflowActivationRead,
    summary="Deactivate a workflow",
)
def deactivate_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkflowActivationRead:
    workflow = workflow_repo.get_by_id(db, workflow_id, current_user.id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    workflow = workflow_repo.set_active(db, workflow, False)
    return workflow  # type: ignore[return-value]
