"""Google Sheets API client for appending one row to an authorized sheet."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.engine.node_executor import NodeExecutionError

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


def append_row(config: dict[str, Any], access_token: str) -> dict[str, Any]:
    spreadsheet_id = config.get("spreadsheet_id")
    if not isinstance(spreadsheet_id, str) or not spreadsheet_id.strip():
        raise NodeExecutionError("google_sheets_append: 'spreadsheet_id' must be a non-empty string")

    cell_range = config.get("range")
    if not isinstance(cell_range, str) or not cell_range.strip():
        raise NodeExecutionError("google_sheets_append: 'range' must be a non-empty A1 range")

    values = config.get("values")
    if not isinstance(values, list) or not values:
        raise NodeExecutionError("google_sheets_append: 'values' must be a non-empty row array")
    if any(not _is_cell_value(value) for value in values):
        raise NodeExecutionError(
            "google_sheets_append: each value must be a string, number, boolean, or null"
        )

    escaped_id = quote(spreadsheet_id.strip(), safe="")
    escaped_range = quote(cell_range.strip(), safe="!$'()*,;:@")
    path = f"{SHEETS_API}/{escaped_id}/values/{escaped_range}:append"
    query = urlencode({"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"})
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            response = client.post(
                f"{path}?{query}",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"values": [values]},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        provider_message = ""
        try:
            payload = exc.response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                provider_message = error["message"].strip()[:300]
        except (ValueError, TypeError):
            pass
        detail = f": {provider_message}" if provider_message else ""
        raise NodeExecutionError(
            f"google_sheets_append: Google Sheets returned HTTP {exc.response.status_code}{detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise NodeExecutionError(
            f"google_sheets_append: could not connect to Google Sheets ({type(exc).__name__})"
        ) from exc

    try:
        result = response.json()
    except (ValueError, TypeError) as exc:
        raise NodeExecutionError("google_sheets_append: Google Sheets returned invalid JSON") from exc
    if not isinstance(result, dict) or not isinstance(result.get("updates"), dict):
        raise NodeExecutionError("google_sheets_append: Google Sheets returned an invalid response")

    updates = result["updates"]
    return {
        "spreadsheet_id": result.get("spreadsheetId", spreadsheet_id.strip()),
        "updated_range": updates.get("updatedRange"),
        "updated_rows": updates.get("updatedRows"),
    }


def _is_cell_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, Real) and math.isfinite(float(value))
