"""Integration tests for the WorkflowReviewer."""

import pytest
from shodh.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    AtomicCondition,
    Operator,
    PythonSnippet,
    RequirementsDocument,
    ReviewStatus,
    Severity,
    SourceRequirement,
    SpecificationDocument,
    SpecificationRule,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
)
from shodh.model_client import FakeModelClient
from shodh.reviewer import WorkflowReviewer


@pytest.fixture
def canonical_bundle():
    # Requirements
    r1 = SourceRequirement(rule_id="R1", source="support_policy.md", line_start=1, priority=1, condition=AtomicCondition(field="category", operator=Operator.IS_NULL), action="manual_review")
    r2 = SourceRequirement(rule_id="R2", source="support_policy.md", line_start=2, priority=2, condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True), action="priority")
    r3 = SourceRequirement(rule_id="R3", source="support_policy.md", line_start=3, priority=3, condition=AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=30, unit="minutes"), action="escalation")
    r4 = SourceRequirement(rule_id="R4", source="support_policy.md", line_start=4, priority=4, condition=None, action="normal", is_fallback=True)
    reqs = RequirementsDocument(doc_id="REQ-CANONICAL", version=1, rules=[r1, r2, r3, r4])

    # Specification
    s1 = SpecificationRule(spec_rule_id="S1", target_rule_id="R1", priority=1, condition=AtomicCondition(field="category", operator=Operator.IS_NULL), action="manual_review")
    s2 = SpecificationRule(spec_rule_id="S2", target_rule_id="R2", priority=2, condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True), action="priority")
    s3 = SpecificationRule(spec_rule_id="S3", target_rule_id="R3", priority=3, condition=AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=30, unit="minutes"), action="escalation")
    s4 = SpecificationRule(spec_rule_id="S4", target_rule_id="R4", priority=4, condition=None, action="normal", is_fallback=True)
    spec = SpecificationDocument(spec_id="SPEC-CANONICAL", version=1, rules=[s1, s2, s3, s4])

    # Workflow Graph
    nodes = {
        "N1": WorkflowNode(node_id="N1", type=WorkflowNodeType.DECISION, rule_id="R1", condition=AtomicCondition(field="category", operator=Operator.IS_NULL)),
        "ACT_MANUAL": WorkflowNode(node_id="ACT_MANUAL", type=WorkflowNodeType.ACTION, action="manual_review"),
        "N2": WorkflowNode(node_id="N2", type=WorkflowNodeType.DECISION, rule_id="R2", condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True)),
        "ACT_PRIORITY": WorkflowNode(node_id="ACT_PRIORITY", type=WorkflowNodeType.ACTION, action="priority"),
        "N3": WorkflowNode(node_id="N3", type=WorkflowNodeType.DECISION, rule_id="R3", condition=AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=30, unit="minutes")),
        "ACT_ESCALATE": WorkflowNode(node_id="ACT_ESCALATE", type=WorkflowNodeType.ACTION, action="escalation"),
        "ACT_NORMAL": WorkflowNode(node_id="ACT_NORMAL", type=WorkflowNodeType.ACTION, action="normal"),
    }
    edges = [
        WorkflowEdge(source_node_id="N1", target_node_id="ACT_MANUAL", branch="true"),
        WorkflowEdge(source_node_id="N1", target_node_id="N2", branch="false"),
        WorkflowEdge(source_node_id="N2", target_node_id="ACT_PRIORITY", branch="true"),
        WorkflowEdge(source_node_id="N2", target_node_id="N3", branch="false"),
        WorkflowEdge(source_node_id="N3", target_node_id="ACT_ESCALATE", branch="true"),
        WorkflowEdge(source_node_id="N3", target_node_id="ACT_NORMAL", branch="false"),
    ]
    graph = WorkflowGraph(workflow_id="WF-CANONICAL", version=1, entry_node_id="N1", nodes=nodes, edges=edges)

    # Python Code
    code = """
if ticket["category"] is None:
    return "manual_review"
if ticket["urgent"]:
    return "priority"
if ticket["waiting_minutes"] >= 30:
    return "escalation"
return "normal"
    """
    snippet = PythonSnippet(snippet_id="SNIP-CANONICAL", file_path="workflow.py", line_start=1, line_end=8, code=code)

    return reqs, spec, graph, snippet


def test_reviewer_passes_valid_bundle(canonical_bundle):
    reqs, spec, graph, snippet = canonical_bundle
    reviewer = WorkflowReviewer()
    report = reviewer.review(
        requirements_doc=reqs,
        spec_doc=spec,
        workflow_graph=graph,
        code_snippet=snippet,
    )

    assert report.status == ReviewStatus.PASS
    assert len(report.findings) == 0
    assert report.coverage["verified_rules"] == 4


def test_reviewer_flags_code_discrepancy_with_counterexample(canonical_bundle):
    reqs, spec, graph, _ = canonical_bundle

    # Buggy code snippet (precedence bug)
    buggy_code = """
if ticket["urgent"]:
    return "priority"
if ticket["category"] is None:
    return "manual_review"
if ticket["waiting_minutes"] >= 30:
    return "escalation"
return "normal"
    """
    snippet = PythonSnippet(snippet_id="SNIP-BUGGY", file_path="workflow.py", line_start=1, line_end=8, code=buggy_code)

    reviewer = WorkflowReviewer()
    report = reviewer.review(
        requirements_doc=reqs,
        spec_doc=spec,
        workflow_graph=graph,
        code_snippet=snippet,
    )

    assert report.status == ReviewStatus.CHANGES_REQUIRED
    blockers = [f for f in report.findings if f.severity == Severity.BLOCKER]
    assert len(blockers) >= 1

    # Counterexample attached
    code_f = next(f for f in blockers if "Python" in f.issue)
    assert code_f.counterexample is not None
    assert code_f.counterexample["ticket"]["category"] is None
    assert code_f.counterexample["ticket"]["urgent"] is True


def test_reviewer_handles_model_timeout_gracefully(canonical_bundle):
    reqs, spec, graph, snippet = canonical_bundle
    fake_timeout_client = FakeModelClient(mode="timeout")
    reviewer = WorkflowReviewer(model_client=fake_timeout_client)

    # Should not crash; records warning finding
    report = reviewer.review(
        requirements_doc=reqs,
        spec_doc=spec,
        workflow_graph=graph,
        code_snippet=snippet,
    )
    assert any("TimeoutError" in f.issue for f in report.findings)
