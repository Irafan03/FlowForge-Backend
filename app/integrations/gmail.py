"""Small Gmail API client built on the project's existing httpx dependency."""

from __future__ import annotations

import base64
import email.utils
import logging
from email.message import EmailMessage
from typing import Any

import httpx

from app.engine.node_executor import NodeExecutionError

GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
logger = logging.getLogger(__name__)


def _safe_oauth_error_code(response: httpx.Response) -> str:
    """Extract only a provider error identifier; never log response bodies or tokens."""
    try:
        value = response.json().get("error")
    except (ValueError, AttributeError):
        return "unknown"
    if isinstance(value, str) and value in {
        "invalid_client",
        "invalid_grant",
        "invalid_request",
        "invalid_scope",
        "unauthorized_client",
        "unsupported_grant_type",
    }:
        return value
    return "unknown"


def exchange_code(code: str, settings: Any) -> dict[str, Any]:
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    if response.is_error:
        logger.warning(
            "Google OAuth authorization-code exchange rejected (HTTP %s, error=%s)",
            response.status_code,
            _safe_oauth_error_code(response),
        )
        raise NodeExecutionError("Google OAuth token exchange failed")
    return response.json()


def refresh_access_token(data: dict[str, Any], settings: Any) -> dict[str, Any]:
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": data["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if response.is_error:
        raise NodeExecutionError("Google OAuth token refresh failed")
    refreshed = response.json()
    data.update(refreshed)
    return data


def _request(method: str, path: str, token: str, **kwargs: Any) -> dict[str, Any]:
    response = httpx.request(
        method,
        f"{GMAIL_API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
        **kwargs,
    )
    if response.is_error:
        raise NodeExecutionError(f"Gmail API request failed ({response.status_code})")
    return response.json() if response.content else {}


def send_message(token: str, config: dict[str, Any]) -> dict[str, Any]:
    message = EmailMessage()
    message["To"] = config["to"]
    message["Subject"] = config.get("subject", "")
    if config.get("cc"):
        message["Cc"] = config["cc"]
    body = config.get("body_html", config.get("body", ""))
    message.add_alternative(body, subtype="html")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    result = _request("POST", "/users/me/messages/send", token, json={"raw": raw})
    return {"message_id": result.get("id")}


def list_messages(token: str, query: str, page_token: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"q": query, "maxResults": 100}
    if page_token:
        params["pageToken"] = page_token
    return _request("GET", "/users/me/messages", token, params=params)


def get_message(token: str, message_id: str) -> dict[str, Any]:
    return _request("GET", f"/users/me/messages/{message_id}", token, params={"format": "full"})


def message_summary(token: str, message_id: str) -> dict[str, Any]:
    message = get_message(token, message_id)
    headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
    body = ""
    parts = message.get("payload", {}).get("parts", [])
    for part in [message.get("payload", {}), *parts]:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            value = part["body"]["data"]
            body = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode(errors="replace")
            break
    sender = email.utils.parseaddr(headers.get("from", ""))[1]
    received_at = headers.get("date", "")
    if received_at:
        try:
            received_at = email.utils.parsedate_to_datetime(received_at).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    return {
        "message_id": message_id,
        "from": sender,
        "subject": headers.get("subject", ""),
        "body_text": body,
        "received_at": received_at,
        "labels": message.get("labelIds", []),
    }
