"""Unit tests for SHODH data contracts and schemas."""

import pytest
from pydantic import ValidationError

from shodh.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    AtomicCondition,
    CompoundCondition,
    Finding,
    Operator,
    RequirementsDocument,
    ReviewReport,
    ReviewStatus,
    Severity,
    SourceRequirement,
    SpecificationDocument,
    SpecificationRule,
    TimeUnit,
    UnsupportedCondition,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
)


def test_atomic_condition_numeric_and_units():
    cond = AtomicCondition(
        field="waiting_minutes",
        operator=Operator.GE,
        value=30,
        unit="minutes",
    )
    assert cond.operator == Operator.GE
    assert cond.normalized_numeric_value() == 30.0

    # 0.5 hours normalized to 30.0 minutes
    cond_hours = AtomicCondition(
        field="waiting_time",
        operator=Operator.GE,
        value=0.5,
        unit="hours",
    )
    assert cond_hours.normalized_numeric_value() == 30.0


def test_atomic_condition_null_checks():
    cond_null = AtomicCondition(
        field="category",
        operator=Operator.IS_NULL,
    )
    assert cond_null.operator == Operator.IS_NULL
    assert cond_null.value is None


def test_compound_condition_nested():
    c1 = AtomicCondition(field="urgent", operator=Operator.EQ, value=True)
    c2 = AtomicCondition(field="category", operator=Operator.IS_NOT_NULL)
    compound = CompoundCondition(
        combinator="and",
        conditions=[c1, c2],
    )
    assert compound.combinator == "and"
    assert len(compound.conditions) == 2

    # Validation failure: 'not' must have exactly 1 child
    with pytest.raises(ValidationError):
        CompoundCondition(combinator="not", conditions=[c1, c2])


def test_unsupported_condition_preservation():
    raw = "If sentiment score is highly distressed"
    unsupported = UnsupportedCondition(
        raw_text=raw,
        reason="Sentiment analysis is outside deterministic rule scope",
        flag="UNSUPPORTED",
    )
    assert unsupported.type == "unsupported"
    assert unsupported.raw_text == raw


def test_source_requirement_evidence_and_serialization():
    req = SourceRequirement(
        rule_id="R1",
        title="Missing category",
        source="support_policy.md",
        line_start=4,
        line_end=5,
        version=1,
        priority=1,
        condition=AtomicCondition(field="category", operator=Operator.IS_NULL),
        action="manual_review",
        raw_text="Missing category -> manual review.",
    )
    assert req.evidence_location == "support_policy.md:4-5"

    doc = RequirementsDocument(doc_id="REQ-SUPPORT-V1", version=1, rules=[req])
    serialized = doc.model_dump_json()
    deserialized = RequirementsDocument.model_validate_json(serialized)
    assert len(deserialized.rules) == 1
    assert deserialized.rules[0].rule_id == "R1"
    assert deserialized.rules[0].condition.field == "category"


def test_workflow_graph_structure():
    n1 = WorkflowNode(
        node_id="N_START",
        type=WorkflowNodeType.DECISION,
        rule_id="R1",
        condition=AtomicCondition(field="category", operator=Operator.IS_NULL),
    )
    n2 = WorkflowNode(
        node_id="N_MANUAL",
        type=WorkflowNodeType.ACTION,
        action="manual_review",
    )
    edge = WorkflowEdge(
        source_node_id="N_START",
        target_node_id="N_MANUAL",
        branch="true",
    )
    graph = WorkflowGraph(
        workflow_id="WF-SUPPORT-V1",
        version=1,
        entry_node_id="N_START",
        nodes={"N_START": n1, "N_MANUAL": n2},
        edges=[edge],
    )
    assert graph.entry_node_id == "N_START"
    assert len(graph.edges) == 1


def test_approval_record_validation():
    app = ApprovalRecord(
        change_id="CHG-001",
        target_rule_id="R3",
        target_version=1,
        status=ApprovalStatus.APPROVED,
        author="eng-lead@company.com",
        timestamp="2026-03-01T10:00:00Z",
        patch={"condition": {"value": 25}},
        notes="Lower escalation SLA from 30m to 25m",
    )
    assert app.status == ApprovalStatus.APPROVED
    assert app.patch["condition"]["value"] == 25


def test_review_report_with_counterexample():
    finding = Finding(
        finding_id="FIND-001",
        rule_id="R3",
        severity=Severity.BLOCKER,
        issue="Incorrect threshold boundary",
        expected="Escalation at 30 minutes",
        actual="Normal queue at 30 minutes",
        evidence="workflow.py:3",
        counterexample={
            "ticket": {"category": "billing", "urgent": False, "waiting_minutes": 30},
            "expected_route": "escalation",
            "actual_route": "normal",
        },
        correction="Replace > 30 with >= 30.",
    )
    report = ReviewReport(
        status=ReviewStatus.CHANGES_REQUIRED,
        summary="Evidenced blocker detected: threshold boundary mismatch",
        findings=[finding],
        coverage={"total_rules": 4, "verified_rules": 3, "unreviewed_rules": 0},
    )
    assert report.status == ReviewStatus.CHANGES_REQUIRED
    assert len(report.findings) == 1
    assert report.findings[0].counterexample["ticket"]["waiting_minutes"] == 30
