"""
Schedule trigger: fires a workflow on a cron schedule.

In Phase 1 this module provides the helper that the ARQ cron task calls.
The ARQ worker registers a periodic task that:
  1. Queries all active workflows whose Trigger has type='schedule_trigger'
     and whose next_run_at <= now().
  2. Enqueues an execution for each one.
  3. Updates next_run_at using croniter.

Cron expressions follow standard 5-field syntax (minute hour dom month dow).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from sqlalchemy.orm import Session

from app.models.execution import WorkflowExecution
from app.models.trigger import Trigger, TriggerType
from app.services import execution_service


async def fire_due_schedules(db: Session) -> list[WorkflowExecution]:
    """
    Called by the ARQ periodic task every minute.
    Returns the list of executions that were enqueued.
    """
    now = datetime.now(timezone.utc)

    due_triggers: list[Trigger] = (
        db.query(Trigger)
        .filter(
            Trigger.type == TriggerType.SCHEDULE,
            Trigger.next_run_at <= now,
            Trigger.is_active.is_(True),
        )
        .all()
    )

    executions: list[WorkflowExecution] = []
    for trigger in due_triggers:
        workflow = trigger.workflow
        if not workflow or not workflow.is_active:
            continue

        cron_expr: str = (trigger.config or {}).get("cron", "")
        if not cron_expr or not croniter.is_valid(cron_expr):
            continue

        try:
            execution = await execution_service.enqueue_execution(
                db,
                workflow_id=workflow.id,
                user_id=workflow.user_id,
                trigger_type="schedule_trigger",
                input_data={"cron": cron_expr, "triggered_at": now.isoformat()},
            )
            executions.append(execution)
        except Exception:
            # Log but don't crash the whole cron run
            import logging
            logging.getLogger(__name__).exception(
                "Failed to enqueue schedule for workflow %s", workflow.id
            )

        # Advance next_run_at regardless of enqueue success
        _advance_next_run(db, trigger, cron_expr, now)

    return executions


def compute_next_run(cron_expr: str, from_dt: datetime | None = None) -> datetime:
    """Return the next scheduled run time after *from_dt* (UTC)."""
    base = from_dt or datetime.now(timezone.utc)
    it = croniter(cron_expr, base)
    return it.get_next(datetime)


def _advance_next_run(
    db: Session, trigger: Trigger, cron_expr: str, after: datetime
) -> None:
    """Update trigger.next_run_at to the next cron slot after *after*."""
    try:
        trigger.next_run_at = compute_next_run(cron_expr, after)
        db.commit()
    except Exception:
        db.rollback()
