import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from fastapi import HTTPException, status
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
    try:
        _sync_poll_trigger(db, workflow, graph)
    except Exception:
        db.rollback()
        raise
    db.commit()
    db.refresh(workflow)
    return workflow


def update(db: Session, workflow: Workflow, data: dict[str, Any]) -> Workflow:
    for field, value in data.items():
        setattr(workflow, field, value)
    if "graph" in data:
        try:
            _sync_poll_trigger(db, workflow, data["graph"])
        except Exception:
            db.rollback()
            raise
    db.commit()
    db.refresh(workflow)
    return workflow


def delete(db: Session, workflow: Workflow) -> None:
    db.delete(workflow)
    db.commit()


def set_active(db: Session, workflow: Workflow, is_active: bool) -> Workflow:
    workflow.is_active = is_active
    trigger = db.query(Trigger).filter(Trigger.workflow_id == workflow.id).first()
    if trigger:
        trigger.is_active = is_active
        if is_active and trigger.type == TriggerType.SCHEDULE:
            from app.triggers.schedule import compute_next_run

            trigger.next_run_at = compute_next_run(
                trigger.cron_expression or (trigger.config or {}).get("cron", ""),
                datetime.now(UTC),
                trigger.timezone,
            )
    db.commit()
    db.refresh(workflow)
    return workflow


def _sync_poll_trigger(db: Session, workflow: Workflow, graph: dict[str, Any]) -> None:
    """Keep durable trigger rows aligned with their graph nodes."""
    node = next(
        (
            n for n in graph.get("nodes", [])
            if n.get("type") in (
                "schedule_trigger",
                "gmail_trigger",
                "telegram_trigger",
                "webhook_trigger",
            )
        ),
        None,
    )
    existing = db.query(Trigger).filter(Trigger.workflow_id == workflow.id).first()
    if node is None:  # validate_graph normally prevents this
        if existing and existing.type in (
            TriggerType.SCHEDULE,
            TriggerType.GMAIL,
            TriggerType.TELEGRAM,
            TriggerType.WEBHOOK,
        ):
            db.delete(existing)
        return

    trigger_type = TriggerType(node["type"])
    config = dict(node.get("config") or {})
    if trigger_type == TriggerType.TELEGRAM:
        config.setdefault("polling_interval_seconds", 1)
    cron_expression = timezone_name = None
    next_run_at = None
    webhook_token = None
    if trigger_type == TriggerType.SCHEDULE:
        cron_expression, timezone_name = _validate_schedule_config(config)
        from app.triggers.schedule import compute_next_run

        next_run_at = compute_next_run(
            cron_expression, datetime.now(UTC), timezone_name
        )
    elif trigger_type == TriggerType.WEBHOOK:
        webhook_token = (
            existing.webhook_token
            if existing and existing.type == TriggerType.WEBHOOK
            else None
        ) or str(uuid.uuid4())
    previous_webhook_secret = (
        existing.webhook_secret
        if existing and existing.type == TriggerType.WEBHOOK
        else None
    )
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
    existing.webhook_token = webhook_token
    existing.webhook_secret = (
        previous_webhook_secret if trigger_type == TriggerType.WEBHOOK else None
    )
    existing.cron_expression = cron_expression
    existing.timezone = timezone_name
    existing.next_run_at = next_run_at


def _validate_schedule_config(config: dict[str, Any]) -> tuple[str, str]:
    cron_expression = config.get("cron")
    timezone_name = config.get("timezone", "UTC")
    if timezone_name is None:
        timezone_name = "UTC"
    if (
        not isinstance(cron_expression, str)
        or len(cron_expression.split()) != 5
        or not croniter.is_valid(cron_expression)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Schedule Trigger requires a valid five-field 'cron' expression",
        )
    if not isinstance(timezone_name, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Schedule Trigger 'timezone' must be a valid IANA timezone",
        )
    try:
        if timezone_name != "UTC":
            ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid Schedule Trigger timezone: {timezone_name}",
        ) from None
    return cron_expression, timezone_name
