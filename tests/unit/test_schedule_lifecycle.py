from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from fastapi import HTTPException

from app.models.execution import WorkflowExecution
from app.models.trigger import Trigger, TriggerType
from app.models.user import User
from app.models.workflow import Workflow
from app.repositories import workflow_repo
from app.triggers.schedule import compute_next_run, fire_due_schedules


def _schedule_graph(cron: str = "*/5 * * * *", timezone_name: str = "UTC") -> dict:
    return {
        "nodes": [{"id": "schedule", "type": "schedule_trigger", "config": {
            "cron": cron, "timezone": timezone_name,
        }}],
        "edges": [],
    }


def _user(db) -> User:
    user = User(email="schedule@example.com", hashed_password="hash")
    db.add(user)
    db.commit()
    return user


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def test_schedule_trigger_created_and_updated_from_graph(db):
    user = _user(db)
    workflow = workflow_repo.create(db, user.id, "Schedule", None, _schedule_graph())
    trigger = db.query(Trigger).filter_by(workflow_id=workflow.id).one()

    assert trigger.type == TriggerType.SCHEDULE
    assert trigger.config == {"cron": "*/5 * * * *", "timezone": "UTC"}
    assert trigger.cron_expression == "*/5 * * * *"
    assert trigger.timezone == "UTC"
    assert _utc(trigger.next_run_at) > datetime.now(UTC)
    assert trigger.is_active is False

    workflow_repo.update(db, workflow, {"graph": _schedule_graph("0 9 * * 1", "UTC")})
    db.refresh(trigger)
    assert db.query(Trigger).filter_by(workflow_id=workflow.id).count() == 1
    assert trigger.cron_expression == "0 9 * * 1"
    assert trigger.timezone == "UTC"


def test_activation_deactivation_and_trigger_replacement(db):
    user = _user(db)
    workflow = workflow_repo.create(db, user.id, "Schedule", None, _schedule_graph())
    trigger = db.query(Trigger).filter_by(workflow_id=workflow.id).one()

    workflow_repo.set_active(db, workflow, True)
    db.refresh(trigger)
    assert trigger.is_active is True
    assert _utc(trigger.next_run_at) > datetime.now(UTC)

    workflow_repo.set_active(db, workflow, False)
    db.refresh(trigger)
    assert trigger.is_active is False

    replacement = {"nodes": [{"id": "manual", "type": "manual_trigger", "config": {}}], "edges": []}
    workflow_repo.update(db, workflow, {"graph": replacement})
    assert db.query(Trigger).filter_by(workflow_id=workflow.id).count() == 0
    workflow_repo.update(db, workflow, {"graph": _schedule_graph()})
    assert db.query(Trigger).filter_by(workflow_id=workflow.id).count() == 1


@pytest.mark.parametrize(
    "cron,zone",
    [("not cron", "UTC"), ("* * * * *", "Mars/Olympus")],
)
def test_invalid_schedule_config_is_rejected_without_persistence(db, cron, zone):
    user = _user(db)
    with pytest.raises(HTTPException) as exc:
        workflow_repo.create(db, user.id, "Invalid", None, _schedule_graph(cron, zone))
    assert exc.value.status_code == 422
    assert db.query(Workflow).count() == 0
    assert db.query(Trigger).count() == 0


def _has_paris_zone() -> bool:
    try:
        ZoneInfo("Europe/Paris")
    except ZoneInfoNotFoundError:
        return False
    return True


@pytest.mark.skipif(not _has_paris_zone(), reason="IANA tzdata is not installed")
def test_compute_next_run_uses_timezone_and_returns_utc():
    base = datetime(2026, 1, 1, 8, 59, tzinfo=UTC)
    result = compute_next_run("0 10 * * *", base, "Europe/Paris")
    assert result == datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


@pytest.mark.skipif(not _has_paris_zone(), reason="IANA tzdata is not installed")
def test_dst_fall_transition_does_not_return_the_same_occurrence_twice():
    first = compute_next_run(
        "30 2 * * *", datetime(2026, 10, 25, 0, 29, tzinfo=UTC), "Europe/Paris"
    )
    second = compute_next_run("30 2 * * *", first, "Europe/Paris")
    assert first == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert second == datetime(2026, 10, 26, 1, 30, tzinfo=UTC)


@pytest.mark.skipif(not _has_paris_zone(), reason="IANA tzdata is not installed")
def test_dst_spring_transition_uses_the_next_existing_local_slot():
    next_run = compute_next_run(
        "30 2 * * *", datetime(2026, 3, 28, 2, 31, tzinfo=UTC), "Europe/Paris"
    )
    assert next_run.astimezone(ZoneInfo("Europe/Paris")).date().isoformat() == "2026-03-29"
    assert next_run.astimezone(ZoneInfo("Europe/Paris")).hour == 3


@pytest.mark.asyncio
async def test_worker_polls_due_active_schedules_once_and_respects_workflow_status(
    db, monkeypatch
):
    user = _user(db)
    active = workflow_repo.create(db, user.id, "Active", None, _schedule_graph("* * * * *"))
    inactive = workflow_repo.create(db, user.id, "Inactive", None, _schedule_graph("* * * * *"))
    workflow_repo.set_active(db, active, True)
    active_trigger = db.query(Trigger).filter_by(workflow_id=active.id).one()
    inactive_trigger = db.query(Trigger).filter_by(workflow_id=inactive.id).one()
    active_trigger.next_run_at = datetime.now(UTC) - timedelta(days=2)
    inactive_trigger.next_run_at = datetime.now(UTC) - timedelta(minutes=2)
    db.commit()

    enqueued = []

    async def fake_enqueue(_db, workflow_id, user_id, trigger_type, input_data, event_key):
        enqueued.append((workflow_id, trigger_type, input_data["cron"], event_key))
        return SimpleNamespace(workflow_id=workflow_id)

    monkeypatch.setattr(
        "app.services.execution_service.enqueue_external_execution", fake_enqueue
    )
    first = await fire_due_schedules(db)
    second = await fire_due_schedules(db)

    assert len(first) == 1
    assert second == []
    assert enqueued[0][:3] == (active.id, "schedule_trigger", "* * * * *")
    assert "schedule:" + str(active_trigger.id) + ":" in enqueued[0][3]
    db.refresh(active_trigger)
    assert _utc(active_trigger.next_run_at) > datetime.now(UTC)


@pytest.mark.asyncio
async def test_worker_retries_failed_enqueue_for_same_occurrence_without_duplicate_execution(
    db, monkeypatch
):
    user = _user(db)
    workflow = workflow_repo.create(db, user.id, "Retry schedule", None, _schedule_graph("* * * * *"))
    workflow_repo.set_active(db, workflow, True)
    trigger = db.query(Trigger).filter_by(workflow_id=workflow.id).one()
    trigger.next_run_at = datetime.now(UTC) - timedelta(minutes=2)
    due_at = _utc(trigger.next_run_at)
    db.commit()

    enqueue_attempts = []

    async def flaky_enqueue(execution_id: str):
        enqueue_attempts.append(execution_id)
        if len(enqueue_attempts) == 1:
            raise ConnectionError("isolated fake ARQ failure")

    monkeypatch.setattr("app.services.execution_service._enqueue_arq", flaky_enqueue)

    assert await fire_due_schedules(db) == []
    db.refresh(trigger)
    assert _utc(trigger.next_run_at) == due_at
    assert db.query(WorkflowExecution).count() == 1
    first_execution = db.query(WorkflowExecution).one()
    first_key = first_execution.trigger_event_key

    result = await fire_due_schedules(db)

    assert len(result) == 1
    assert enqueue_attempts == [str(first_execution.id), str(first_execution.id)]
    assert db.query(WorkflowExecution).count() == 1
    assert db.query(WorkflowExecution).one().trigger_event_key == first_key
    db.refresh(trigger)
    assert _utc(trigger.next_run_at) > datetime.now(UTC)
