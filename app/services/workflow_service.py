"""
Workflow service: business logic for creating, updating, and validating workflows.
Graph structural validation lives in app/engine/validators.py;
this service wires it with the repository layer and enforces business rules.
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.workflow import Workflow
from app.repositories import workflow_repo
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


def create_workflow(db: Session, user_id: uuid.UUID, data: WorkflowCreate) -> Workflow:
    """Validate the graph and persist the workflow."""
    from app.engine.validators import validate_graph  # avoid circular import

    graph_dict = data.graph.model_dump()
    validate_graph(graph_dict)  # raises HTTPException on invalid graph

    return workflow_repo.create(
        db,
        user_id=user_id,
        name=data.name,
        description=data.description,
        graph=graph_dict,
    )


def update_workflow(
    db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID, data: WorkflowUpdate
) -> Workflow:
    from app.engine.validators import validate_graph

    workflow = workflow_repo.get_by_id(db, workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    update_data: dict[str, Any] = {}
    if data.name is not None:
        update_data["name"] = data.name
    if data.description is not None:
        update_data["description"] = data.description
    if data.graph is not None:
        graph_dict = data.graph.model_dump()
        validate_graph(graph_dict)
        update_data["graph"] = graph_dict

    return workflow_repo.update(db, workflow, update_data)


def get_workflow(db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID) -> Workflow:
    workflow = workflow_repo.get_by_id(db, workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


def delete_workflow(db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID) -> None:
    workflow = get_workflow(db, workflow_id, user_id)
    workflow_repo.delete(db, workflow)


def activate_workflow(db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID) -> Workflow:
    workflow = get_workflow(db, workflow_id, user_id)
    return workflow_repo.set_active(db, workflow, True)


def deactivate_workflow(db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID) -> Workflow:
    workflow = get_workflow(db, workflow_id, user_id)
    return workflow_repo.set_active(db, workflow, False)
