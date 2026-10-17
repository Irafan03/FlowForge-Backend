"""
ExecutionContext holds the mutable state of a running workflow execution:
- outputs collected from each completed node
- branch decisions made by IF nodes
- template resolution against those outputs

The context lives entirely in worker memory and is NOT persisted as-is.
Individual node outputs are persisted to node_executions by the runner.
"""

import uuid
import re
from typing import Any

from sqlalchemy.orm import Session


class ExecutionContext:
    def __init__(
        self,
        execution_id: str,
        workflow_graph: dict[str, Any],
        input_data: dict[str, Any] | None = None,
        db: Session | None = None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.graph = workflow_graph
        self.input_data = input_data or {}
        self.db = db
        self.user_id = user_id

        # node_id → output dict
        self._outputs: dict[str, dict[str, Any]] = {}
        # IF node_id → "true" | "false"
        self._branch_results: dict[str, str] = {}
        # Set of node IDs that should be skipped (wrong branch)
        self._skipped_nodes: set[str] = set()

    def get_credential(self, credential_id: str, expected_type: str | None = None) -> dict[str, Any]:
        """Return decrypted credential data only when it belongs to this execution's user."""
        if self.db is None or self.user_id is None:
            raise ValueError("Credential access is unavailable outside an authenticated execution")
        from app.repositories import credential_repo
        from app.services.credential_service import decrypt_data

        try:
            parsed_id = uuid.UUID(credential_id)
        except (ValueError, TypeError) as exc:
            raise ValueError("Credential not found") from exc
        credential = credential_repo.get_by_id(self.db, parsed_id, self.user_id)
        if credential is None or (expected_type and credential.type != expected_type):
            raise ValueError("Credential not found")
        return decrypt_data(credential.encrypted_data)

    # ── Output management ─────────────────────────────────────────────────────

    def set_output(self, node_id: str, output: dict[str, Any]) -> None:
        self._outputs[node_id] = output

    def get_output(self, node_id: str) -> dict[str, Any] | None:
        return self._outputs.get(node_id)

    # ── Branch management ─────────────────────────────────────────────────────

    def set_branch_result(self, if_node_id: str, result: str) -> None:
        """result must be 'true' or 'false'."""
        assert result in ("true", "false")
        self._branch_results[if_node_id] = result

    def mark_skipped(self, node_id: str) -> None:
        self._skipped_nodes.add(node_id)

    def is_skipped(self, node_id: str) -> bool:
        return node_id in self._skipped_nodes

    def should_execute(self, node_id: str, graph_edges: list[dict]) -> bool:
        """
        Returns False if every incoming edge to this node comes from an IF node
        whose branch result does NOT match the edge's source_handle.
        """
        if node_id in self._skipped_nodes:
            return False

        incoming = [e for e in graph_edges if e["target"] == node_id]
        if not incoming:
            return True  # no incoming edges → it's the trigger, always execute

        for edge in incoming:
            src = edge["source"]
            handle = edge.get("source_handle")
            if src in self._branch_results:
                # This is an outgoing edge from an IF node
                if handle != self._branch_results[src]:
                    # Wrong branch — mark this node skipped
                    self._skipped_nodes.add(node_id)
                    return False
        return True

    # ── Template resolution ───────────────────────────────────────────────────

    _TEMPLATE_RE = re.compile(r"\{\{([^}]+)\}\}")

    def resolve(self, value: Any) -> Any:
        """
        Recursively resolve {{node_id.field.subfield}} templates in a value.
        Supports strings, dicts, lists. Other types returned as-is.
        Raises ValueError for unresolvable references.
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def _resolve_string(self, s: str) -> Any:
        matches = self._TEMPLATE_RE.findall(s)
        if not matches:
            return s

        # If the entire string is a single template, return the typed value
        full_match = self._TEMPLATE_RE.fullmatch(s)
        if full_match:
            return self._lookup(full_match.group(1).strip())

        # Otherwise substitute all templates into the string
        def replacer(m: re.Match) -> str:
            val = self._lookup(m.group(1).strip())
            return str(val)

        return self._TEMPLATE_RE.sub(replacer, s)

    def _lookup(self, path: str) -> Any:
        """
        Resolve a dotted path like 'node_id.body.user_id' against stored outputs.
        Also supports 'input_data.key' to access the execution's input_data.
        """
        parts = path.split(".")
        root = parts[0]

        if root == "input_data":
            obj: Any = self.input_data
        elif root in self._outputs:
            obj = self._outputs[root]
        else:
            raise ValueError(
                f"Unresolved template reference: '{{{{ {path} }}}}'. "
                f"Node '{root}' has not been executed yet or does not exist."
            )

        for part in parts[1:]:
            if isinstance(obj, dict):
                if part not in obj:
                    raise ValueError(
                        f"Template path '{{{{ {path} }}}}': key '{part}' not found."
                    )
                obj = obj[part]
            else:
                raise ValueError(
                    f"Template path '{{{{ {path} }}}}': cannot traverse into non-dict at '{part}'."
                )
        return obj

    def resolve_node_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve all templates in a node's config dict."""
        return self.resolve(config)  # type: ignore[return-value]
