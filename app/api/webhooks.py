"""
Inbound webhook endpoint:

  POST /webhooks/{token}

Lookup: token → Trigger → Workflow → enqueue execution.
Raw body is stashed on request.state so the HMAC verification in
triggers/webhook.py can read it before JSON parsing discards the bytes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.trigger import Trigger, TriggerType
from app.schemas.execution import ExecutionEnqueuedRead
from app.triggers.webhook import fire_webhook_trigger

from fastapi import Depends

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/{token}",
    response_model=ExecutionEnqueuedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive an inbound webhook and trigger the associated workflow",
)
async def receive_webhook(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> ExecutionEnqueuedRead:
    # Stash raw body for HMAC verification (must read before JSON parsing)
    raw_body = await request.body()
    request.state.raw_body = raw_body

    # Parse JSON payload (lenient — return {} if not JSON)
    try:
        payload: dict[str, Any] = await request.json()
        if not isinstance(payload, dict):
            payload = {"data": payload}
    except Exception:
        payload = {}

    # Lookup trigger by token (eager-load workflow)
    trigger: Trigger | None = (
        db.query(Trigger)
        .options(joinedload(Trigger.workflow))
        .filter(
            Trigger.webhook_token == token,
            Trigger.type == TriggerType.WEBHOOK,
        )
        .first()
    )

    if not trigger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook token not found",
        )

    execution = await fire_webhook_trigger(db, trigger, request, payload)
    return ExecutionEnqueuedRead(
        execution_id=execution.id,
        status=execution.status,
        workflow_id=execution.workflow_id,
        created_at=execution.created_at,
    )
