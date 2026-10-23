"""PostgreSQL-backed schedule lifecycle checks (requires TEST_DATABASE_URL)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.trigger import Trigger, TriggerType
from app.models.user import User
from app.repositories import workflow_repo
from app.triggers.schedule import fire_due_schedules


def _graph(cron: str, timezone_name: str = "UTC") -> dict:
    return {
        "nodes": [{"id": "schedule", "type": "schedule_trigger", "config": {
            "cron": cron, "timezone": timezone_name,
        }}],
        "edges": [],
    }


def test_postgres_schedule_create_update_activation_and_replacement(postgres_engine, db):
    user = User(email="phase7b-schedule@example.com", hashed_password="hash")
    db.add(user)
    db.flush()
    workflow = workflow_repo.create(db, user.id, "Schedule lifecycle", None, _graph("0 9 * * *"))
    trigger = db.query(Trigger).filter_by(workflow_id=workflow.id).one()
    assert trigger.type == TriggerType.SCHEDULE
    assert trigger.cron_expression == "0 9 * * *"
    assert trigger.timezone == "UTC"
    assert trigger.next_run_at is not None

    workflow_repo.update(
        db, workflow, {"graph": _graph("30 9 * * 1", "UTC")}
    )
    db.refresh(trigger)
    assert trigger.cron_expression == "30 9 * * 1"
    assert trigger.timezone == "UTC"
    assert trigger.next_run_at > datetime.now(UTC)

    workflow_repo.set_active(db, workflow, True)
    db.refresh(trigger)
    assert workflow.is_active and trigger.is_active
    workflow_repo.set_active(db, workflow, False)
    db.refresh(trigger)
    assert not workflow.is_active and not trigger.is_active

    workflow_repo.update(
        db,
        workflow,
        {"graph": {"nodes": [{"id": "manual", "type": "manual_trigger", "config": {}}], "edges": []}},
    )
    assert db.query(Trigger).filter_by(workflow_id=workflow.id).count() == 0


async def test_postgres_worker_claims_due_schedule_once_and_filters_inactive(
    postgres_engine, db, monkeypatch
):
    user = User(email="phase7b-worker@example.com", hashed_password="hash")
    db.add(user)
    db.flush()
    active = workflow_repo.create(db, user.id, "Active schedule", None, _graph("* * * * *"))
    inactive = workflow_repo.create(db, user.id, "Inactive schedule", None, _graph("* * * * *"))
    workflow_repo.set_active(db, active, True)
    for trigger in db.query(Trigger).filter(Trigger.workflow_id.in_([active.id, inactive.id])):
        trigger.next_run_at = datetime.now(UTC) - timedelta(minutes=2)
    db.commit()

    enqueued = []

    async def fake_enqueue(_db, workflow_id, user_id, trigger_type, input_data, event_key):
        enqueued.append(workflow_id)
        return SimpleNamespace(workflow_id=workflow_id)

    monkeypatch.setattr(
        "app.services.execution_service.enqueue_external_execution", fake_enqueue
    )
    assert len(await fire_due_schedules(db)) == 1
    assert await fire_due_schedules(db) == []
    assert enqueued == [active.id]
