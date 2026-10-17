"""
Unit tests for the workflow engine:
- validate_graph
- ExecutionContext (template resolution, branch management)
- execute_node (handlers)
- run_workflow (runner, via in-memory SQLite)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.engine.context import ExecutionContext
from app.engine.node_executor import NodeExecutionError, execute_node
from app.engine.validators import validate_graph

# ── validate_graph ─────────────────────────────────────────────────────────────

class TestValidateGraph:
    def test_valid_minimal_graph(self, minimal_graph):
        validate_graph(minimal_graph)  # should not raise

    def test_no_trigger_raises(self):
        graph = {
            "nodes": [{"id": "n1", "type": "set_data", "config": {"fields": []}}],
            "edges": [],
        }
        with pytest.raises(Exception, match="trigger"):
            validate_graph(graph)

    def test_multiple_triggers_raises(self):
        graph = {
            "nodes": [
                {"id": "t1", "type": "manual_trigger", "config": {}},
                {"id": "t2", "type": "webhook_trigger", "config": {}},
            ],
            "edges": [],
        }
        with pytest.raises(Exception, match="Multiple"):
            validate_graph(graph)

    def test_edge_unknown_source_raises(self):
        graph = {
            "nodes": [{"id": "t1", "type": "manual_trigger", "config": {}}],
            "edges": [{"id": "e1", "source": "NONEXISTENT", "target": "t1"}],
        }
        with pytest.raises(Exception, match="unknown source"):
            validate_graph(graph)

    def test_cycle_detection(self):
        graph = {
            "nodes": [
                {"id": "t1", "type": "manual_trigger", "config": {}},
                {"id": "n1", "type": "set_data", "config": {"fields": []}},
                {"id": "n2", "type": "set_data", "config": {"fields": []}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "n1"},
                {"id": "e2", "source": "n1", "target": "n2"},
                {"id": "e3", "source": "n2", "target": "n1"},  # cycle
            ],
        }
        with pytest.raises(Exception, match="cycle"):
            validate_graph(graph)

    def test_if_node_missing_branches(self):
        graph = {
            "nodes": [
                {"id": "t1", "type": "manual_trigger", "config": {}},
                {"id": "if1", "type": "if_condition", "config": {"condition": "True"}},
                {"id": "a", "type": "set_data", "config": {"fields": []}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "if1"},
                # Only 'true' branch — missing 'false'
                {"id": "e2", "source": "if1", "target": "a", "source_handle": "true"},
            ],
        }
        with pytest.raises(Exception, match="false"):
            validate_graph(graph)

    def test_http_request_missing_url(self):
        graph = {
            "nodes": [
                {"id": "t1", "type": "manual_trigger", "config": {}},
                {"id": "h1", "type": "http_request", "config": {"method": "GET"}},  # no url
            ],
            "edges": [{"id": "e1", "source": "t1", "target": "h1"}],
        }
        with pytest.raises(Exception, match="url"):
            validate_graph(graph)


# ── ExecutionContext ───────────────────────────────────────────────────────────

class TestExecutionContext:
    def _ctx(self, input_data=None):
        return ExecutionContext(
            execution_id=str(uuid.uuid4()),
            workflow_graph={"nodes": [], "edges": []},
            input_data=input_data or {},
        )

    def test_set_and_get_output(self):
        ctx = self._ctx()
        ctx.set_output("n1", {"foo": "bar"})
        assert ctx.get_output("n1") == {"foo": "bar"}

    def test_resolve_literal_string(self):
        ctx = self._ctx()
        assert ctx.resolve("hello") == "hello"

    def test_resolve_template(self):
        ctx = self._ctx()
        ctx.set_output("n1", {"value": 42})
        assert ctx.resolve("{{n1.value}}") == 42

    def test_resolve_string_interpolation(self):
        ctx = self._ctx()
        ctx.set_output("n1", {"name": "world"})
        assert ctx.resolve("hello {{n1.name}}!") == "hello world!"

    def test_resolve_nested(self):
        ctx = self._ctx()
        ctx.set_output("n1", {"user": {"id": "abc"}})
        assert ctx.resolve("{{n1.user.id}}") == "abc"

    def test_resolve_input_data(self):
        ctx = self._ctx(input_data={"key": "val"})
        assert ctx.resolve("{{input_data.key}}") == "val"

    def test_resolve_unknown_node_raises(self):
        ctx = self._ctx()
        with pytest.raises(ValueError, match="MISSING"):
            ctx.resolve("{{MISSING.field}}")

    def test_branch_skipping(self):
        ctx = self._ctx()
        ctx.set_branch_result("if1", "true")
        edges = [
            {"source": "if1", "target": "true_node", "source_handle": "true"},
            {"source": "if1", "target": "false_node", "source_handle": "false"},
        ]
        assert ctx.should_execute("true_node", edges) is True
        assert ctx.should_execute("false_node", edges) is False

    def test_mark_skipped(self):
        ctx = self._ctx()
        ctx.mark_skipped("n1")
        assert ctx.is_skipped("n1") is True

    def test_resolve_dict(self):
        ctx = self._ctx()
        ctx.set_output("n1", {"x": 10})
        result = ctx.resolve({"a": "{{n1.x}}", "b": "literal"})
        assert result == {"a": 10, "b": "literal"}

    def test_resolve_list(self):
        ctx = self._ctx()
        ctx.set_output("n1", {"x": 10})
        assert ctx.resolve(["{{n1.x}}", "literal"]) == [10, "literal"]


# ── execute_node ──────────────────────────────────────────────────────────────

class TestExecuteNode:
    def _ctx(self):
        return ExecutionContext(
            execution_id=str(uuid.uuid4()),
            workflow_graph={"nodes": [], "edges": []},
        )

    def test_manual_trigger(self):
        ctx = self._ctx()
        node = {"id": "t1", "type": "manual_trigger", "config": {}}
        output = execute_node(node, ctx)
        assert "triggered_at" in output
        assert "input_data" in output

    def test_set_data(self):
        ctx = self._ctx()
        node = {
            "id": "s1",
            "type": "set_data",
            "config": {
                "fields": [
                    {"key": "name", "value": "Alice"},
                    {"key": "age", "value": 30},
                ]
            },
        }
        output = execute_node(node, ctx)
        assert output == {"name": "Alice", "age": 30}

    def test_if_condition_true(self):
        ctx = self._ctx()
        node = {"id": "if1", "type": "if_condition", "config": {"condition": "1 == 1"}}
        output = execute_node(node, ctx)
        assert output["result"] is True
        assert output["branch"] == "true"

    def test_if_condition_false(self):
        ctx = self._ctx()
        node = {"id": "if1", "type": "if_condition", "config": {"condition": "1 == 2"}}
        output = execute_node(node, ctx)
        assert output["result"] is False
        assert output["branch"] == "false"

    def test_if_condition_sets_branch_in_context(self):
        ctx = self._ctx()
        node = {"id": "if1", "type": "if_condition", "config": {"condition": "True"}}
        execute_node(node, ctx)
        assert ctx._branch_results["if1"] == "true"

    def test_unknown_node_type_raises(self):
        ctx = self._ctx()
        node = {"id": "x", "type": "nonexistent_type", "config": {}}
        with pytest.raises(NodeExecutionError, match="No handler"):
            execute_node(node, ctx)

    def test_set_data_with_template(self):
        ctx = self._ctx()
        ctx.set_output("prev", {"greeting": "hello"})
        node = {
            "id": "s1",
            "type": "set_data",
            "config": {"fields": [{"key": "msg", "value": "{{prev.greeting}} world"}]},
        }
        output = execute_node(node, ctx)
        assert output["msg"] == "hello world"

    def test_schedule_trigger(self):
        ctx = self._ctx()
        node = {
            "id": "t1",
            "type": "schedule_trigger",
            "config": {"cron": "0 * * * *"},
        }
        output = execute_node(node, ctx)
        assert "triggered_at" in output
        assert output["cron"] == "0 * * * *"


# ── Runner integration (SQLite) ────────────────────────────────────────────────

class TestRunner:
    def test_run_minimal_workflow(self, db, minimal_graph):
        """Runner persists NodeExecution rows and sets execution to SUCCESS."""
        from app.engine.runner import run_workflow
        from app.models.execution import ExecutionStatus, NodeExecutionStatus, WorkflowExecution

        # Create a user and workflow directly in SQLite
        from app.models.user import User
        from app.models.workflow import Workflow

        user = User(email="runner@test.com", hashed_password="x")
        db.add(user)
        db.flush()

        workflow = Workflow(
            user_id=user.id,
            name="Test",
            graph=minimal_graph,
            is_active=True,
        )
        db.add(workflow)
        db.flush()

        execution = WorkflowExecution(
            workflow_id=workflow.id,
            user_id=user.id,
            status=ExecutionStatus.QUEUED,
            trigger_type="manual_trigger",
            input_data={},
            created_at=datetime.now(UTC),
        )
        db.add(execution)
        db.commit()

        run_workflow(db, execution.id)

        db.refresh(execution)
        assert execution.status == ExecutionStatus.SUCCESS
        assert execution.duration_ms is not None

        node_executions = execution.node_executions
        assert len(node_executions) == 2  # trigger + set_data
        statuses = {ne.node_id: ne.status for ne in node_executions}
        assert statuses["trigger_1"] == NodeExecutionStatus.SUCCESS
        assert statuses["set_1"] == NodeExecutionStatus.SUCCESS

    def test_runner_skips_wrong_branch(self, db, if_branch_graph):
        """IF node (1==1) → true branch executes, false branch is SKIPPED."""
        from app.engine.runner import run_workflow
        from app.models.execution import ExecutionStatus, NodeExecutionStatus, WorkflowExecution
        from app.models.user import User
        from app.models.workflow import Workflow

        user = User(email="branch@test.com", hashed_password="x")
        db.add(user)
        db.flush()

        workflow = Workflow(
            user_id=user.id, name="IF Test", graph=if_branch_graph, is_active=True
        )
        db.add(workflow)
        db.flush()

        execution = WorkflowExecution(
            workflow_id=workflow.id,
            user_id=user.id,
            status=ExecutionStatus.QUEUED,
            trigger_type="manual_trigger",
            input_data={},
            created_at=datetime.now(UTC),
        )
        db.add(execution)
        db.commit()

        run_workflow(db, execution.id)

        db.refresh(execution)
        assert execution.status == ExecutionStatus.SUCCESS

        statuses = {ne.node_id: ne.status for ne in execution.node_executions}
        assert statuses["a"] == NodeExecutionStatus.SUCCESS
        assert statuses["b"] == NodeExecutionStatus.SKIPPED
