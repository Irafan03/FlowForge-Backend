"""
Node executor: dispatches a node to the correct integration handler
based on node.type, then returns the output dict.

No arbitrary code execution — only predefined handlers are invoked.
"""

from typing import Any

from app.engine.context import ExecutionContext


def execute_node(node: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
    """
    Resolves config templates, then dispatches to the appropriate handler.
    Returns the node's output dict.
    Raises NodeExecutionError on failure.
    """
    node_type: str = node["type"]
    raw_config: dict[str, Any] = node.get("config", {})

    # Resolve {{template}} references in config before passing to handler
    resolved_config = context.resolve_node_config(raw_config)

    handler = _HANDLERS.get(node_type)
    if handler is None:
        raise NodeExecutionError(f"No handler registered for node type: '{node_type}'")

    return handler(node, resolved_config, context)


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_manual_trigger(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    from datetime import datetime, timezone
    return {
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "input_data": context.input_data,
    }


def _handle_webhook_trigger(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    # input_data contains the webhook payload set at trigger time
    return {
        "payload": context.input_data,
    }


def _handle_set_data(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    """
    Sets/transforms fields. Each field in config['fields'] is:
    { "key": "output_key", "value": "<literal or {{template>>}" }
    """
    output: dict[str, Any] = {}
    fields = config.get("fields", [])
    for field_def in fields:
        key = field_def.get("key")
        value = field_def.get("value")
        if key:
            # value may itself be a template — already resolved by context.resolve
            output[key] = value
    return output


def _handle_if_condition(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    """
    Evaluates a condition string using simpleeval (no exec/eval).
    Sets branch result in context.
    """
    from simpleeval import EvalWithCompoundTypes, InvalidExpression

    condition_str: str = config["condition"]

    # Build names dict from all current outputs for simpleeval
    names: dict[str, Any] = {}
    for node_id, output in context._outputs.items():
        names[node_id] = output
    names["input_data"] = context.input_data

    try:
        evaluator = EvalWithCompoundTypes(names=names)
        result = bool(evaluator.eval(condition_str))
    except (InvalidExpression, Exception) as exc:
        raise NodeExecutionError(
            f"IF condition evaluation failed for '{condition_str}': {exc}"
        ) from exc

    branch = "true" if result else "false"
    context.set_branch_result(node["id"], branch)

    return {"result": result, "branch": branch, "condition": condition_str}


def _handle_http_request(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    """Delegates to app.integrations.http_request — includes SSRF protection."""
    from app.integrations.http_request import execute_http_request
    return execute_http_request(config)


def _handle_gmail_send(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.integrations import gmail

    _, token = _google_token(config, context)
    result = gmail.send_message(token, config)
    result["sent_at"] = datetime.now(timezone.utc).isoformat()
    return result


def _handle_telegram_send(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    from datetime import datetime, timezone

    credential = context.get_credential(config.get("credential_id", ""), "telegram_bot")
    from app.integrations.telegram import send_message

    result = send_message(credential["bot_token"], config)
    result["sent_at"] = datetime.now(timezone.utc).isoformat()
    return result


def _handle_ml_prediction(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    raise NodeExecutionError("ml_prediction is not implemented in Phase 1")


def _handle_gmail_trigger(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    return context.input_data


def _handle_telegram_trigger(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    return context.input_data


def _handle_schedule_trigger(
    node: dict, config: dict, context: ExecutionContext
) -> dict[str, Any]:
    from datetime import datetime, timezone
    return {
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "cron": config.get("cron", ""),
    }


# ── Handler registry ──────────────────────────────────────────────────────────

_HANDLERS: dict[str, Any] = {
    "manual_trigger": _handle_manual_trigger,
    "webhook_trigger": _handle_webhook_trigger,
    "schedule_trigger": _handle_schedule_trigger,
    "set_data": _handle_set_data,
    "if_condition": _handle_if_condition,
    "http_request": _handle_http_request,
    "gmail_trigger": _handle_gmail_trigger,
    "telegram_trigger": _handle_telegram_trigger,
    "gmail_send": _handle_gmail_send,
    "telegram_send": _handle_telegram_send,
    "ml_prediction": _handle_ml_prediction,
}


def _google_token(config: dict[str, Any], context: ExecutionContext) -> tuple[dict, str]:
    import uuid
    from datetime import datetime, timedelta, timezone

    from app.integrations.gmail import refresh_access_token
    from app.models.credential import Credential
    from app.services.credential_service import encrypt_data

    try:
        credential_id = uuid.UUID(config.get("credential_id", ""))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NodeExecutionError("Google credential not found") from exc
    record = context.db.query(Credential).filter(
        Credential.id == credential_id, Credential.user_id == context.user_id,
        Credential.type == "oauth2_google",
    ).first() if context.db is not None and context.user_id is not None else None
    if record is None:
        raise NodeExecutionError("Google credential not found")
    data = context.get_credential(str(credential_id), "oauth2_google")
    expiry = data.get("expiry")
    if expiry:
        try:
            expired = datetime.fromisoformat(expiry.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            expired = True
    else:
        expired = True
    if expired:
        from app.config.settings import get_settings

        data = refresh_access_token(data, get_settings())
        data["expiry"] = (
            datetime.now(timezone.utc)
            + timedelta(seconds=int(data.get("expires_in", 3600)))
        ).isoformat()
        record.encrypted_data = encrypt_data(data)
        context.db.commit()
    return data, data["access_token"]


class NodeExecutionError(Exception):
    """Raised when a node fails during execution."""
