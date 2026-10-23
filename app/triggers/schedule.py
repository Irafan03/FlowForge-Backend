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

import logging
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy.orm import Session

from app.models.execution import WorkflowExecution
from app.models.trigger import Trigger, TriggerType
from app.services import execution_service

logger = logging.getLogger(__name__)


async def fire_due_schedules(db: Session) -> list[WorkflowExecution]:
    """
    Called by the ARQ periodic task every minute.
    Returns the list of executions that were enqueued.
    """
    now = datetime.now(UTC)

    executions: list[WorkflowExecution] = []
    deferred_trigger_ids: set[uuid.UUID] = set()
    while True:
        due_query = (
            db.query(Trigger)
            .join(Trigger.workflow)
            .filter(
                Trigger.type == TriggerType.SCHEDULE,
                Trigger.next_run_at <= now,
                Trigger.is_active.is_(True),
                Trigger.workflow.has(is_active=True),
            )
        )
        if deferred_trigger_ids:
            due_query = due_query.filter(~Trigger.id.in_(deferred_trigger_ids))
        trigger: Trigger | None = (
            due_query.order_by(Trigger.next_run_at, Trigger.id)
            .with_for_update(skip_locked=True, of=Trigger)
            .first()
        )
        if trigger is None:
            break

        workflow = trigger.workflow
        workflow_id = workflow.id
        user_id = workflow.user_id
        cron_expr = trigger.cron_expression or (trigger.config or {}).get("cron", "")
        timezone_name = trigger.timezone or (trigger.config or {}).get("timezone") or "UTC"
        scheduled_slot_db = trigger.next_run_at
        scheduled_for = scheduled_slot_db
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=UTC)
        scheduled_for = scheduled_for.astimezone(UTC)
        event_key = f"schedule:{trigger.id}:{scheduled_for.isoformat()}"

        # Capture the next slot, then enqueue idempotently before advancing the
        # trigger. If ARQ is unavailable, the due slot remains for the next poll.
        try:
            if (
                not cron_expr
                or len(cron_expr.split()) != 5
                or not croniter.is_valid(cron_expr)
            ):
                raise ValueError("Invalid cron expression in persisted schedule trigger")
            next_run_at = compute_next_run(cron_expr, now, timezone_name)
        except Exception:
            db.rollback()
            logger.exception("Invalid schedule for trigger %s; disabling it", trigger.id)
            invalid_trigger = db.get(Trigger, trigger.id)
            if invalid_trigger is not None:
                invalid_trigger.is_active = False
                db.commit()
            continue

        try:
            execution = await execution_service.enqueue_external_execution(
                db,
                workflow_id=workflow_id,
                user_id=user_id,
                trigger_type="schedule_trigger",
                input_data={
                    "cron": cron_expr,
                    "triggered_at": now.isoformat(),
                    "scheduled_for": scheduled_for.isoformat(),
                },
                event_key=event_key,
            )
        except Exception:
            # Leave the due slot unchanged; the next poll retries the same
            # idempotency key and re-enqueues the persisted queued execution.
            logger.exception(
                "Failed to enqueue schedule for workflow %s", workflow.id
            )
            deferred_trigger_ids.add(trigger.id)
            continue

        # enqueue_external_execution commits its execution row, so this is a
        # conditional advance rather than relying on the original row lock.
        # Competing pollers share event_key and ARQ job_id; only one may advance.
        advanced = (
            db.query(Trigger)
            .filter(
                Trigger.id == trigger.id,
                Trigger.next_run_at == scheduled_slot_db,
                Trigger.is_active.is_(True),
                Trigger.workflow.has(is_active=True),
            )
            .update({Trigger.next_run_at: next_run_at}, synchronize_session=False)
        )
        db.commit()
        if advanced == 1:
            executions.append(execution)
        else:
            deferred_trigger_ids.add(trigger.id)

    return executions


def compute_next_run(
    cron_expr: str,
    from_dt: datetime | None = None,
    timezone_name: str | None = None,
) -> datetime:
    """Return next cron occurrence as UTC, evaluating wall time in the IANA zone."""
    base = from_dt or datetime.now(UTC)
    zone = UTC if (timezone_name or "UTC") == "UTC" else ZoneInfo(timezone_name)
    local_base = base.astimezone(zone)
    it = croniter(cron_expr, local_base)
    last_local_slot = local_base.replace(tzinfo=None)
    base_utc = base.astimezone(UTC)
    # During the autumn DST fold, croniter can return the same wall-clock slot
    # twice with different UTC offsets. Treat that repeated local slot as one
    # occurrence and continue to the next distinct local cron time.
    for _ in range(10_000):
        candidate_utc = it.get_next(datetime).astimezone(UTC)
        candidate_local = candidate_utc.astimezone(zone)
        if (
            candidate_utc > base_utc
            and candidate_local.replace(tzinfo=None) > last_local_slot
        ):
            return candidate_utc
    raise ValueError("Cron expression did not produce a future local occurrence")
