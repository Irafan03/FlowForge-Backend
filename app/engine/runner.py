"""
Workflow graph runner.

Responsibilities:
1. Topological sort of the DAG.
2. Walk nodes in order, skip branches pruned by IF nodes.
3. Persist a NodeExecution row for every node (success, failed, or skipped).
4. Update WorkflowExecution status + timing.

Called exclusively from the ARQ worker.
"""

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.engine.context import ExecutionContext
from app.engine.node_executor import NodeExecutionError, execute_node
from app.models.execution import ExecutionStatus, NodeExecutionStatus
from app.repositories import execution_repo


def run_workflow(
    db: Session,
    execution_id: uuid.UUID,
) -> None:
    """
    Entry point called by the ARQ worker.
    Loads the execution + workflow, runs the graph, persists all results.
    """
    execution = execution_repo.get_by_id_internal(db, execution_id)
    if execution is None:
        raise ValueError(f"Execution {execution_id} not found")

    # Guard: do not re-run a completed/cancelled execution
    if execution.status in (
        ExecutionStatus.SUCCESS,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
    ):
        return

    workflow = execution.workflow
    graph: dict[str, Any] = workflow.graph

    # Mark as running
    started_at = datetime.now(timezone.utc)
    execution_repo.update_status(
        db, execution, ExecutionStatus.RUNNING, started_at=started_at
    )

    context = ExecutionContext(
        execution_id=str(execution_id),
        workflow_graph=graph,
        input_data=execution.input_data or {},
        db=db,
        user_id=execution.user_id,
    )

    try:
        ordered_nodes = _topological_sort(graph)
        _execute_nodes(db, execution_id, graph, ordered_nodes, context)
    except Exception as exc:
        # Unexpected runner-level failure
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        execution_repo.update_status(
            db,
            execution,
            ExecutionStatus.FAILED,
            error=str(exc),
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
        raise

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    # Determine final status: failed if any node failed
    node_execs = execution_repo.get_by_id_internal(db, execution_id)
    any_failed = any(
        ne.status == NodeExecutionStatus.FAILED
        for ne in (node_execs.node_executions if node_execs else [])
    )
    final_status = ExecutionStatus.FAILED if any_failed else ExecutionStatus.SUCCESS

    execution_repo.update_status(
        db,
        execution,
        final_status,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )


def _execute_nodes(
    db: Session,
    execution_id: uuid.UUID,
    graph: dict[str, Any],
    ordered_nodes: list[dict[str, Any]],
    context: ExecutionContext,
) -> None:
    """Walk nodes in topological order, execute or skip each one."""
    edges: list[dict] = graph.get("edges", [])

    for node in ordered_nodes:
        node_id: str = node["id"]
        node_type: str = node["type"]

        # Determine whether this node should run
        if not context.should_execute(node_id, edges):
            execution_repo.create_node_execution(
                db,
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                status=NodeExecutionStatus.SKIPPED,
            )
            continue

        # Mark pending → running (we write directly as RUNNING then update)
        node_started = datetime.now(timezone.utc)

        try:
            output = execute_node(node, context)
            node_finished = datetime.now(timezone.utc)
            duration_ms = int((node_finished - node_started).total_seconds() * 1000)

            context.set_output(node_id, output)

            execution_repo.create_node_execution(
                db,
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                status=NodeExecutionStatus.SUCCESS,
                output=output,
                started_at=node_started,
                finished_at=node_finished,
                duration_ms=duration_ms,
            )

        except NodeExecutionError as exc:
            node_finished = datetime.now(timezone.utc)
            duration_ms = int((node_finished - node_started).total_seconds() * 1000)

            execution_repo.create_node_execution(
                db,
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                status=NodeExecutionStatus.FAILED,
                error=str(exc),
                started_at=node_started,
                finished_at=node_finished,
                duration_ms=duration_ms,
            )
            # Skip all downstream nodes after a failure
            _propagate_skip(node_id, graph, context)

        except Exception as exc:
            # Unexpected error — treat as node failure too
            node_finished = datetime.now(timezone.utc)
            duration_ms = int((node_finished - node_started).total_seconds() * 1000)

            execution_repo.create_node_execution(
                db,
                execution_id=execution_id,
                node_id=node_id,
                node_type=node_type,
                status=NodeExecutionStatus.FAILED,
                error=f"Unexpected error: {exc}",
                started_at=node_started,
                finished_at=node_finished,
                duration_ms=duration_ms,
            )
            _propagate_skip(node_id, graph, context)


def _propagate_skip(
    failed_node_id: str,
    graph: dict[str, Any],
    context: ExecutionContext,
) -> None:
    """Mark all nodes reachable from failed_node_id as skipped."""
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in graph.get("edges", []):
        adjacency[edge["source"]].append(edge["target"])

    queue = deque(adjacency[failed_node_id])
    while queue:
        node_id = queue.popleft()
        if not context.is_skipped(node_id):
            context.mark_skipped(node_id)
            queue.extend(adjacency[node_id])


def _topological_sort(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Kahn's algorithm — returns nodes in a valid execution order (BFS topo sort).
    Assumes the graph is a valid DAG (validated before execution).
    """
    nodes: list[dict] = graph.get("nodes", [])
    edges: list[dict] = graph.get("edges", [])

    node_map: dict[str, dict] = {n["id"]: n for n in nodes}

    # Build in-degree and adjacency
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        adjacency[src].append(tgt)
        in_degree[tgt] += 1

    # Start with all zero-in-degree nodes (the trigger)
    queue: deque[str] = deque(
        node_id for node_id, deg in in_degree.items() if deg == 0
    )
    result: list[dict] = []

    while queue:
        node_id = queue.popleft()
        result.append(node_map[node_id])
        for neighbor in adjacency[node_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(nodes):
        raise ValueError(
            "Topological sort failed: graph contains a cycle. "
            "This should have been caught by validate_graph()."
        )

    return result
