"""
Webhook trigger: receives an inbound HTTP payload and fires the
associated workflow.

The Trigger row in the DB stores the webhook_secret for optional
HMAC-SHA256 signature verification (X-FlowForge-Signature header).

Lookup path: webhook_token → Trigger → Workflow.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models.execution import WorkflowExecution
from app.models.trigger import Trigger
from app.services import execution_service


async def fire_webhook_trigger(
    db: Session,
    trigger: Trigger,
    request: Request,
    payload: dict[str, Any],
) -> WorkflowExecution:
    """
    Validates the optional HMAC signature, then enqueues the execution.

    *trigger* must be the Trigger ORM object for the matched webhook_token.
    *payload* is the parsed JSON body of the incoming request.
    """
    workflow = trigger.workflow

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Associated workflow not found"
        )

    if not workflow.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow is not active",
        )

    # Optional HMAC verification
    if trigger.webhook_secret:
        _verify_signature(request, trigger.webhook_secret)

    return await execution_service.enqueue_execution(
        db,
        workflow_id=workflow.id,
        user_id=workflow.user_id,
        trigger_type="webhook_trigger",
        input_data=payload,
    )


def _verify_signature(request: Request, secret: str) -> None:
    """
    Verify the X-FlowForge-Signature header using HMAC-SHA256.
    Header format: "sha256=<hex_digest>"

    The raw request body must have been stashed on request.state.raw_body
    by the webhook endpoint before JSON parsing (see app/api/webhooks.py).
    """
    header = request.headers.get("X-FlowForge-Signature", "")
    if not header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed X-FlowForge-Signature header",
        )

    provided_sig = header[len("sha256="):]
    body_bytes: bytes = getattr(request.state, "raw_body", b"")

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(provided_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )
