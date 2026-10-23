"""FlowForge ML inference service client."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

import httpx

from app.config.settings import get_settings

_DEFAULT_TIMEOUT = 15
_MAX_TIMEOUT = 60


def execute_ml_prediction(config: dict[str, Any]) -> dict[str, Any]:
    """Call FlowForge ML and validate its prediction response."""
    from app.engine.node_executor import NodeExecutionError

    model_id, input_data = config.get("model_id"), config.get("input")
    if not isinstance(model_id, str) or not model_id.strip():
        raise NodeExecutionError("ml_prediction: 'model_id' must be a non-empty string")
    if not isinstance(input_data, dict):
        raise NodeExecutionError("ml_prediction: 'input' must be an object")
    timeout = config.get("timeout_seconds", _DEFAULT_TIMEOUT)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, Real)
        or not math.isfinite(float(timeout))
        or not 0 < timeout <= _MAX_TIMEOUT
    ):
        raise NodeExecutionError(
            f"ml_prediction: 'timeout_seconds' must be greater than 0 and at most {_MAX_TIMEOUT}"
        )
    base_url = get_settings().FLOWFORGE_ML_URL.rstrip("/")
    if not base_url:
        raise NodeExecutionError("ml_prediction: FLOWFORGE_ML_URL is not configured")
    try:
        with httpx.Client(timeout=float(timeout)) as client:
            response = client.post(
                f"{base_url}/predict",
                json={"model_id": model_id, "input": input_data},
            )
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise NodeExecutionError(f"ml_prediction: request timed out after {timeout:g}s") from exc
    except httpx.HTTPStatusError as exc:
        raise NodeExecutionError(
            f"ml_prediction: ML service returned HTTP {exc.response.status_code}: "
            f"{exc.response.text[:500]}"
        ) from exc
    except httpx.RequestError as exc:
        raise NodeExecutionError(f"ml_prediction: connection error: {exc}") from exc
    except httpx.InvalidURL as exc:
        raise NodeExecutionError(f"ml_prediction: invalid service URL: {exc}") from exc
    try:
        result = response.json()
    except (ValueError, TypeError) as exc:
        raise NodeExecutionError("ml_prediction: ML service returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise NodeExecutionError("ml_prediction: response must be a JSON object")
    prediction, confidence = result.get("prediction"), result.get("confidence")
    raw_output, response_model_id = result.get("raw_output"), result.get("model_id")
    duration_ms = result.get("duration_ms")
    if not isinstance(prediction, str) or not prediction:
        raise NodeExecutionError("ml_prediction: response has invalid 'prediction'")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, Real)
        or not math.isfinite(float(confidence))
        or not 0 <= confidence <= 1
    ):
        raise NodeExecutionError("ml_prediction: response has invalid 'confidence'")
    if not isinstance(raw_output, dict):
        raise NodeExecutionError("ml_prediction: response has invalid 'raw_output'")
    if response_model_id != model_id:
        raise NodeExecutionError("ml_prediction: response model_id does not match request")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, Real)
        or not math.isfinite(float(duration_ms))
        or duration_ms < 0
    ):
        raise NodeExecutionError("ml_prediction: response has invalid 'duration_ms'")
    return {
        "prediction": prediction,
        "confidence": float(confidence),
        "raw_output": raw_output,
        "model_id": response_model_id,
        "duration_ms": float(duration_ms),
    }
