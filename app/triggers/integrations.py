"""Pull poll Gmail and Telegram triggers, deduplicating every provider event."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.integrations import gmail, telegram
from app.models.credential import Credential
from app.models.trigger import Trigger
from app.repositories import credential_repo
from app.services import credential_service, execution_service


def _credential_data(db: Session, credential_id: str, user_id: Any, kind: str) -> tuple[Credential, dict]:
    import uuid

    record = credential_repo.get_by_id(db, uuid.UUID(credential_id), user_id)
    if record is None or record.type != kind:
        raise ValueError("Integration credential not found")
    return record, credential_service.decrypt_data(record.encrypted_data)


async def poll_integrations(db: Session) -> int:
    triggers = db.query(Trigger).filter(
        Trigger.type.in_(["gmail_trigger", "telegram_trigger"]), Trigger.is_active.is_(True)
    ).all()
    count = 0
    for trigger in triggers:
        workflow = trigger.workflow
        if workflow is None or not workflow.is_active:
            continue
        config = dict(trigger.config or {})
        try:
            if trigger.type == "gmail_trigger":
                count += await _poll_gmail(db, trigger, workflow, config)
            elif trigger.type == "telegram_trigger":
                count += await _poll_telegram(db, trigger, workflow, config)
        except Exception:
            # Keep one broken integration from preventing other triggers from polling.
            import logging
            logging.getLogger(__name__).exception("Integration poll failed for trigger %s", trigger.id)
    return count


async def _poll_gmail(db: Session, trigger: Trigger, workflow: Any, config: dict) -> int:
    interval = max(30, int(config.get("polling_interval_seconds", 60)))
    last_polled = config.get("last_polled_at")
    if last_polled:
        try:
            last_polled_at = datetime.fromisoformat(last_polled)
            if last_polled_at.tzinfo is None:
                last_polled_at = last_polled_at.replace(tzinfo=UTC)
            if datetime.now(UTC) - last_polled_at < timedelta(seconds=interval):
                return 0
        except ValueError:
            pass
    record, data = _credential_data(db, config.get("credential_id", ""), workflow.user_id, "oauth2_google")
    settings = __import__("app.config.settings", fromlist=["get_settings"]).get_settings()
    expiry = data.get("expiry")
    expired = True
    if expiry:
        try:
            expired = datetime.fromisoformat(expiry.replace("Z", "+00:00")) <= datetime.now(UTC)
        except ValueError:
            pass
    if expired:
        data = gmail.refresh_access_token(data, settings)
        data["expiry"] = (datetime.now(UTC) + timedelta(seconds=int(data.get("expires_in", 3600)))).isoformat()
        record.encrypted_data = credential_service.encrypt_data(data)
        db.commit()
    token = data["access_token"]
    cursor = int(config.get("cursor_internal_ms", int(datetime.now(UTC).timestamp() * 1000)))
    query = " ".join(filter(None, [config.get("filter", ""), f"after:{max(0, cursor // 1000 - 2)}"]))
    result = gmail.list_messages(token, query)
    found = 0
    max_cursor = cursor
    while True:
        for item in result.get("messages", []):
            message = gmail.get_message(token, item["id"])
            internal_ms = int(message.get("internalDate", cursor))
            max_cursor = max(max_cursor, internal_ms)
            payload = gmail.message_summary(token, item["id"])
            event_key = f"gmail:{trigger.id}:{item['id']}"
            await execution_service.enqueue_external_execution(
                db, workflow.id, workflow.user_id, "gmail_trigger", payload, event_key
            )
            found += 1
        page = result.get("nextPageToken")
        if not page:
            break
        result = gmail.list_messages(token, query, page)
    polled_at = datetime.now(UTC)
    max_cursor = max(max_cursor, int(polled_at.timestamp() * 1000))
    config["cursor_internal_ms"] = max_cursor
    config["last_polled_at"] = polled_at.isoformat()
    trigger.config = config
    db.commit()
    return found


async def _poll_telegram(db: Session, trigger: Trigger, workflow: Any, config: dict) -> int:
    interval = max(1, int(config.get("polling_interval_seconds", 1)))
    last_polled = config.get("last_polled_at")
    if last_polled:
        try:
            if datetime.now(UTC) - datetime.fromisoformat(last_polled) < timedelta(seconds=interval):
                return 0
        except ValueError:
            pass
    allowed = {str(chat_id) for chat_id in config.get("allowed_chat_ids", [])}
    if not allowed:
        raise ValueError("Telegram trigger requires at least one allowed_chat_id")
    _record, data = _credential_data(db, config.get("credential_id", ""), workflow.user_id, "telegram_bot")
    # Pending updates are processed on the first poll after activation. The stored
    # offset also lets a reactivated workflow process messages received while paused.
    updates = telegram.get_updates(data["bot_token"], config.get("offset"))
    next_offset = config.get("offset")
    found = 0
    for update in updates:
        update_id = int(update["update_id"])
        next_offset = max(int(next_offset or 0), update_id + 1)
        message = update.get("message")
        if not message:
            continue
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        if allowed and chat_id not in allowed:
            continue
        payload = {
            "message_id": message.get("message_id"),
            "chat_id": chat_id,
            "from_user": {
                "id": (message.get("from") or {}).get("id"),
                "username": (message.get("from") or {}).get("username"),
            },
            "text": message.get("text", ""),
            "received_at": datetime.fromtimestamp(message.get("date", 0), UTC).isoformat(),
        }
        await execution_service.enqueue_external_execution(
            db, workflow.id, workflow.user_id, "telegram_trigger", payload,
            f"telegram:{trigger.id}:{update_id}",
        )
        found += 1
    if next_offset is not None:
        config["offset"] = int(next_offset)
    config["last_polled_at"] = datetime.now(UTC).isoformat()
    trigger.config = config
    db.commit()
    return found
