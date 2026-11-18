"""Unit tests for workflow graph analyzer and simulation."""

import pytest
from shodh.contracts import (
    AtomicCondition,
    Operator,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
)
from shodh.graph_analyzer import GraphAnalyzer


@pytest.fixture
def valid_workflow_graph():
    # N1: Category missing?
    n1 = WorkflowNode(node_id="N_CAT", type=WorkflowNodeType.DECISION, rule_id="R1", condition=AtomicCondition(field="category", operator=Operator.IS_NULL))
    # N2: Action manual_review
    n2 = WorkflowNode(node_id="N_ACT_MANUAL", type=WorkflowNodeType.ACTION, action="manual_review")
    # N3: Urgent?
    n3 = WorkflowNode(node_id="N_URGENT", type=WorkflowNodeType.DECISION, rule_id="R2", condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True))
    # N4: Action priority
    n4 = WorkflowNode(node_id="N_ACT_PRIORITY", type=WorkflowNodeType.ACTION, action="priority")
    # N5: Action normal
    n5 = WorkflowNode(node_id="N_ACT_NORMAL", type=WorkflowNodeType.ACTION, action="normal")

    edges = [
        WorkflowEdge(source_node_id="N_CAT", target_node_id="N_ACT_MANUAL", branch="true"),
        WorkflowEdge(source_node_id="N_CAT", target_node_id="N_URGENT", branch="false"),
        WorkflowEdge(source_node_id="N_URGENT", target_node_id="N_ACT_PRIORITY", branch="true"),
        WorkflowEdge(source_node_id="N_URGENT", target_node_id="N_ACT_NORMAL", branch="false"),
    ]

    return WorkflowGraph(
        workflow_id="WF-VALID",
        version=1,
        entry_node_id="N_CAT",
        nodes={"N_CAT": n1, "N_ACT_MANUAL": n2, "N_URGENT": n3, "N_ACT_PRIORITY": n4, "N_ACT_NORMAL": n5},
        edges=edges,
    )


def test_graph_simulation_routing(valid_workflow_graph):
    analyzer = GraphAnalyzer(valid_workflow_graph)

    # Missing category -> manual_review
    res, path = analyzer.simulate({"category": None, "urgent": True})
    assert res == "manual_review"
    assert path == ["N_CAT", "N_ACT_MANUAL"]

    # Category present, urgent -> priority
    res, path = analyzer.simulate({"category": "billing", "urgent": True})
    assert res == "priority"
    assert path == ["N_CAT", "N_URGENT", "N_ACT_PRIORITY"]

    # Category present, not urgent -> normal
    res, path = analyzer.simulate({"category": "billing", "urgent": False})
    assert res == "normal"
    assert path == ["N_CAT", "N_URGENT", "N_ACT_NORMAL"]


def test_graph_detects_dead_node(valid_workflow_graph):
    # Add a node not connected to anything
    dead = WorkflowNode(node_id="N_DEAD", type=WorkflowNodeType.ACTION, action="escalation")
    valid_workflow_graph.nodes["N_DEAD"] = dead

    analyzer = GraphAnalyzer(valid_workflow_graph)
    dead_nodes = analyzer.find_dead_or_unreachable_nodes()
    assert "N_DEAD" in dead_nodes

    findings = analyzer.check_against_requirements([])
    assert any("Unreachable" in f.issue for f in findings)


def test_graph_detects_missing_branch(valid_workflow_graph):
    # Remove the false branch from N_URGENT
    valid_workflow_graph.edges = [e for e in valid_workflow_graph.edges if not (e.source_node_id == "N_URGENT" and e.branch == "false")]

    analyzer = GraphAnalyzer(valid_workflow_graph)
    missing = analyzer.find_missing_branches()
    assert ("N_URGENT", "false") in missing
