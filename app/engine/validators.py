"""
Graph validators: structural and semantic validation of a workflow graph.
All validation raises HTTPException with clear messages so the API can
return them directly to the client.

Rules enforced:
- Exactly one trigger node (type ends with '_trigger')
- All edge source/target IDs reference existing nodes
- No cycles (DAG enforcement via DFS)
- IF nodes have at least one outgoing edge labelled 'true' and 'false'
- Required config fields are present per node type
"""

import re
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, status

TRIGGER_TYPES = {
    "manual_trigger",
    "webhook_trigger",
    "schedule_trigger",
    "gmail_trigger",
    "telegram_trigger",
}

# Required config keys per node type
REQUIRED_CONFIG: dict[str, list[str]] = {
    "http_request": ["url", "method"],
    "if_condition": ["condition"],
    "set_data": ["fields"],
    "gmail_send": ["credential_id", "to", "subject"],
    "telegram_send": ["credential_id", "chat_id", "text"],
    "ml_prediction": ["model_id", "input"],
    "ai_agent": ["prompt"],
    "google_sheets_append": ["credential_id", "spreadsheet_id", "range", "values"],
    "manual_trigger": [],
    "webhook_trigger": [],
    "schedule_trigger": [],
    "gmail_trigger": ["credential_id"],
    "telegram_trigger": ["credential_id"],
}


def validate_graph(graph: dict[str, Any]) -> None:
    """
    Validates the graph dict. Raises HTTPException(422) on any violation.
    Called at workflow save-time and again right before execution.
    """
    nodes: list[dict] = graph.get("nodes", [])
    edges: list[dict] = graph.get("edges", [])

    if not nodes:
        _fail("Graph must contain at least one node")

    node_ids = {n["id"] for n in nodes}

    # 1. Exactly one trigger
    trigger_nodes = [n for n in nodes if n["type"] in TRIGGER_TYPES]
    if len(trigger_nodes) == 0:
        _fail("Workflow must have exactly one trigger node")
    if len(trigger_nodes) > 1:
        ids = [n["id"] for n in trigger_nodes]
        _fail(f"Multiple trigger nodes found: {ids}. Only one is allowed.")

    # 2. Edge endpoints reference real nodes
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in node_ids:
            _fail(f"Edge references unknown source node: '{src}'")
        if tgt not in node_ids:
            _fail(f"Edge references unknown target node: '{tgt}'")

    # 3. Cycle detection via DFS
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])

    visited: set[str] = set()
    rec_stack: set[str] = set()

    def _dfs(node_id: str) -> bool:
        visited.add(node_id)
        rec_stack.add(node_id)
        for neighbor in adjacency[node_id]:
            if neighbor not in visited:
                if _dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node_id)
        return False

    for n in nodes:
        if n["id"] not in visited:
            if _dfs(n["id"]):
                _fail(
                    "Graph contains a cycle. "
                    "Workflows must be directed acyclic graphs (DAGs)."
                )

    # 4. IF nodes must have both 'true' and 'false' outgoing branches
    for node in nodes:
        if node["type"] == "if_condition":
            handles = {e.get("source_handle") for e in edges if e.get("source") == node["id"]}
            missing = {"true", "false"} - handles
            if missing:
                _fail(
                    f"IF node '{node['id']}' is missing outgoing branches: {missing}. "
                    "Both 'true' and 'false' branches are required."
                )

    # 5. Required config fields
    for node in nodes:
        required = REQUIRED_CONFIG.get(node["type"], [])
        config = node.get("config", {})
        for field in required:
            if field not in config or config[field] in (None, ""):
                _fail(
                    f"Node '{node['id']}' (type={node['type']!r}) is missing "
                    f"required config field: '{field}'"
                )
        if node["type"] == "http_request":
            credential_id = config.get("credential_id")
            credential_type = config.get("credential_type")
            if credential_id and credential_type not in {"api_key", "http_header"}:
                _fail("HTTP Request credential_type must be 'api_key' or 'http_header'")
            if credential_type and not credential_id:
                _fail("HTTP Request credential_type requires credential_id")
        if node["type"] == "telegram_trigger":
            _validate_telegram_trigger_config(node["id"], config)


def _validate_telegram_trigger_config(node_id: str, config: dict[str, Any]) -> None:
    allowed = config.get("allowed_chat_ids")
    if not isinstance(allowed, list) or not allowed:
        _fail(
            f"Telegram trigger node '{node_id}' requires a non-empty 'allowed_chat_ids' list"
        )
    for index, chat_id in enumerate(allowed):
        valid_id = (
            isinstance(chat_id, int) and not isinstance(chat_id, bool)
        ) or (isinstance(chat_id, str) and re.fullmatch(r"-?\d+", chat_id) is not None)
        if not valid_id:
            _fail(
                f"Telegram trigger node '{node_id}' has invalid 'allowed_chat_ids' item "
                f"at index {index}; each chat ID must be an integer or signed integer string"
            )
    normalized_ids = [str(chat_id) for chat_id in allowed]
    if len(normalized_ids) != len(set(normalized_ids)):
        _fail(f"Telegram trigger node '{node_id}' has duplicate values in 'allowed_chat_ids'")

    interval = config.get("polling_interval_seconds", 1)
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 3600:
        _fail(
            f"Telegram trigger node '{node_id}' has invalid 'polling_interval_seconds'; "
            "expected an integer from 1 to 3600 seconds"
        )


def _fail(message: str) -> None:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)
