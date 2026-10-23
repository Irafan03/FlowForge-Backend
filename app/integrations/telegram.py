"""Telegram Bot API helpers using httpx."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.engine.node_executor import NodeExecutionError


_TELEGRAM_BOT_URL = re.compile(r"(https://api\.telegram\.org/bot)[^/]+(/)")


class _RedactTelegramTokenFilter(logging.Filter):
    """Prevent HTTPX's request log from exposing the Bot API token in its URL."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _TELEGRAM_BOT_URL.sub(r"\1[REDACTED]\2", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


_httpx_logger = logging.getLogger("httpx")
if not any(isinstance(item, _RedactTelegramTokenFilter) for item in _httpx_logger.filters):
    _httpx_logger.addFilter(_RedactTelegramTokenFilter())


def _call(token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/{method}", json=payload or {}, timeout=20
        )
    except httpx.RequestError as exc:
        raise NodeExecutionError("Telegram API request failed") from exc
    if response.is_error:
        raise NodeExecutionError(f"Telegram API request failed ({response.status_code})")
    result = response.json()
    if not result.get("ok"):
        raise NodeExecutionError("Telegram API rejected the request")
    return result.get("result")


def send_message(token: str, config: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"chat_id": config["chat_id"], "text": config["text"]}
    if config.get("parse_mode"):
        payload["parse_mode"] = config["parse_mode"]
    message = _call(token, "sendMessage", payload)
    return {"message_id": message["message_id"], "chat_id": str(message["chat"]["id"])}


def get_updates(token: str, offset: int | None = None) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    return _call(token, "getUpdates", payload)
