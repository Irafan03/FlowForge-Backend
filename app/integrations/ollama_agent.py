"""Ollama Cloud chat integration used by the workflow AI Agent node."""

from __future__ import annotations

import json
import math
from numbers import Real
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config.settings import get_settings

_DEFAULT_TIMEOUT_SECONDS = 90
_MAX_TIMEOUT_SECONDS = 180


def execute_ai_agent(config: dict[str, Any]) -> dict[str, Any]:
    """Generate a response from Ollama using a prompt resolved by the workflow."""
    from app.engine.node_executor import NodeExecutionError

    settings = get_settings()
    api_key = settings.OLLAMA_API_KEY.strip()
    if not api_key:
        raise NodeExecutionError("ai_agent: OLLAMA_API_KEY is not configured")

    prompt = config.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise NodeExecutionError("ai_agent: 'prompt' must be a non-empty string")

    system_prompt = config.get("system_prompt", "")
    if not isinstance(system_prompt, str):
        raise NodeExecutionError("ai_agent: 'system_prompt' must be a string")

    output_mode = config.get("output_mode", "text")
    if output_mode not in {"text", "json"}:
        raise NodeExecutionError("ai_agent: 'output_mode' must be 'text' or 'json'")
    output_fields = config.get("output_fields", [])
    if not isinstance(output_fields, list) or any(not isinstance(field, str) or not field.strip() for field in output_fields):
        raise NodeExecutionError("ai_agent: 'output_fields' must be a list of non-empty field names")
    output_fields = list(dict.fromkeys(field.strip() for field in output_fields))
    if output_mode == "json" and not output_fields:
        raise NodeExecutionError("ai_agent: add at least one field for JSON output")

    model = config.get("model", settings.OLLAMA_MODEL)
    if not isinstance(model, str) or not model.strip():
        raise NodeExecutionError("ai_agent: 'model' must be a non-empty string")

    timeout = config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, Real)
        or not math.isfinite(float(timeout))
        or not 0 < timeout <= _MAX_TIMEOUT_SECONDS
    ):
        raise NodeExecutionError(
            f"ai_agent: 'timeout_seconds' must be greater than 0 and at most {_MAX_TIMEOUT_SECONDS}"
        )

    temperature = config.get("temperature", 0.2)
    if (
        isinstance(temperature, bool)
        or not isinstance(temperature, Real)
        or not math.isfinite(float(temperature))
        or not 0 <= temperature <= 2
    ):
        raise NodeExecutionError("ai_agent: 'temperature' must be a number from 0 to 2")

    max_tokens = config.get("max_tokens", 2048)
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 32768:
        raise NodeExecutionError("ai_agent: 'max_tokens' must be an integer from 1 to 32768")

    base_url = settings.OLLAMA_BASE_URL.strip().rstrip("/")
    parsed_url = urlparse(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise NodeExecutionError("ai_agent: OLLAMA_BASE_URL must be a valid HTTP(S) URL")

    messages: list[dict[str, str]] = []
    if output_mode == "json":
        requested_shape = json.dumps({field: "string" for field in output_fields}, ensure_ascii=False)
        json_instruction = (
            "Return only one valid JSON object with exactly the requested keys. "
            "Use a string value for every key. Do not include Markdown fences or other text.\n"
            f"Required JSON shape: {requested_shape}"
        )
        system_prompt = f"{system_prompt.strip()}\n\n{json_instruction}".strip()
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    request_body = {
        "model": model.strip(),
        "messages": messages,
        "stream": False,
        "options": {"temperature": float(temperature), "num_predict": max_tokens},
    }

    try:
        with httpx.Client(timeout=float(timeout), follow_redirects=False) as client:
            response = client.post(
                f"{base_url}/api/chat",
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_body,
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise NodeExecutionError(f"ai_agent: Ollama request timed out after {timeout:g}s") from exc
    except httpx.HTTPStatusError as exc:
        raise NodeExecutionError(
            f"ai_agent: Ollama returned HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise NodeExecutionError(f"ai_agent: could not connect to Ollama ({type(exc).__name__})") from exc

    try:
        result = response.json()
    except (ValueError, TypeError) as exc:
        raise NodeExecutionError("ai_agent: Ollama returned invalid JSON") from exc

    message = result.get("message") if isinstance(result, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise NodeExecutionError("ai_agent: Ollama response did not contain message content")

    output: dict[str, Any] = {
        "response": content,
        "model": result.get("model", model.strip()),
        "prompt_tokens": result.get("prompt_eval_count"),
        "completion_tokens": result.get("eval_count"),
    }
    if output_mode == "json":
        candidate = content.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError) as exc:
            raise NodeExecutionError("ai_agent: response is not valid JSON; retry or simplify the requested fields") from exc
        if not isinstance(data, dict):
            raise NodeExecutionError("ai_agent: JSON response must be an object")
        missing = [field for field in output_fields if field not in data]
        if missing:
            raise NodeExecutionError(f"ai_agent: JSON response is missing fields: {', '.join(missing)}")
        output["data"] = data
    return output
