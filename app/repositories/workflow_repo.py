import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.trigger import Trigger, TriggerType
from app.models.workflow import Workflow


def get_by_id(db: Session, workflow_id: uuid.UUID, user_id: uuid.UUID) -> Workflow | None:
    """Always filter by user_id to enforce isolation."""
    return (
        db.query(Workflow)
        .filter(Workflow.id == workflow_id, Workflow.user_id == user_id)
        .first()
    )


def get_by_id_any_user(db: Session, workflow_id: uuid.UUID) -> Workflow | None:
    """Used internally (e.g. worker) where user context is already validated."""
    return db.get(Workflow, workflow_id)


def list_by_user(
    db: Session,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    is_active: bool | None = None,
) -> tuple[list[Workflow], int]:
    q = db.query(Workflow).filter(Workflow.user_id == user_id)
    if is_active is not None:
        q = q.filter(Workflow.is_active == is_active)
    total = q.with_entities(func.count()).scalar()
    items = q.offset(skip).limit(limit).all()
    return items, total


def create(
    db: Session,
    user_id: uuid.UUID,
    name: str,
    description: str | None,
    graph: dict[str, Any],
) -> Workflow:
    workflow = Workflow(user_id=user_id, name=name, description=description, graph=graph)
    db.add(workflow)
    # Assign the generated UUID and persist the parent row before creating its trigger.
    db.flush()
    _sync_poll_trigger(db, workflow, graph)
    db.commit()
    db.refresh(workflow)
    return workflow


def update(db: Session, workflow: Workflow, data: dict[str, Any]) -> Workflow:
    for field, value in data.items():
        setattr(workflow, field, value)
    if "graph" in data:
        _sync_poll_trigger(db, workflow, data["graph"])
    db.commit()
    db.refresh(workflow)
    return workflow


def delete(db: Session, workflow: Workflow) -> None:
    db.delete(workflow)
    db.commit()


def set_active(db: Session, workflow: Workflow, is_active: bool) -> Workflow:
    workflow.is_active = is_active
    trigger = db.query(Trigger).filter(Trigger.workflow_id == workflow.id).first()
    if trigger and trigger.type in (TriggerType.GMAIL, TriggerType.TELEGRAM):
        trigger.is_active = is_active
    db.commit()
    db.refresh(workflow)
    return workflow


def _sync_poll_trigger(db: Session, workflow: Workflow, graph: dict[str, Any]) -> None:
    """Keep the durable poll-trigger row aligned with Gmail/Telegram graph nodes."""
    node = next(
        (n for n in graph.get("nodes", []) if n.get("type") in ("gmail_trigger", "telegram_trigger")),
        None,
    )
    existing = db.query(Trigger).filter(Trigger.workflow_id == workflow.id).first()
    if node is None:
        if existing and existing.type in (TriggerType.GMAIL, TriggerType.TELEGRAM):
            db.delete(existing)
        return

    trigger_type = TriggerType.GMAIL if node["type"] == "gmail_trigger" else TriggerType.TELEGRAM
    config = dict(node.get("config") or {})
    if trigger_type == TriggerType.TELEGRAM:
        config.setdefault("polling_interval_seconds", 60)
    if existing and existing.type == trigger_type:
        old_config = dict(existing.config or {})
        if old_config.get("credential_id") == config.get("credential_id"):
            for key in (
                "cursor_internal_ms",
                "last_polled_at",
                "offset",
            ):
                if key in old_config:
                    config[key] = old_config[key]
    if existing is None:
        existing = Trigger(workflow_id=workflow.id, type=trigger_type, config=config)
        db.add(existing)
    else:
        existing.type = trigger_type
        existing.config = config
        existing.is_active = workflow.is_active
