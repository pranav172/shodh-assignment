"""Unit tests for semantic rule engine and specification checker."""

import pytest
from shodh.contracts import (
    AtomicCondition,
    Operator,
    RequirementsDocument,
    Severity,
    SourceRequirement,
    SpecificationDocument,
    SpecificationRule,
)
from shodh.approvals import ApprovalResolver
from shodh.rule_engine import (
    SpecificationChecker,
    conditions_are_semantically_equivalent,
    eval_condition,
    route_ticket_by_requirements,
)


@pytest.fixture
def effective_requirements():
    r1 = SourceRequirement(
        rule_id="R1",
        source="support_policy.md",
        line_start=1,
        priority=1,
        condition=AtomicCondition(field="category", operator=Operator.IS_NULL),
        action="manual_review",
    )
    r2 = SourceRequirement(
        rule_id="R2",
        source="support_policy.md",
        line_start=2,
        priority=2,
        condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True),
        action="priority",
    )
    r3 = SourceRequirement(
        rule_id="R3",
        source="support_policy.md",
        line_start=3,
        priority=3,
        condition=AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=30, unit="minutes"),
        action="escalation",
    )
    r4 = SourceRequirement(
        rule_id="R4",
        source="support_policy.md",
        line_start=4,
        priority=4,
        condition=None,
        action="normal",
        is_fallback=True,
    )
    doc = RequirementsDocument(doc_id="REQ-TEST", version=1, rules=[r1, r2, r3, r4])
    effective, _ = ApprovalResolver().resolve(doc, [])
    return effective


def test_eval_condition_ticket():
    cond = AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=30, unit="minutes")
    assert eval_condition(cond, {"waiting_minutes": 30}) is True
    assert eval_condition(cond, {"waiting_minutes": 29}) is False
    assert eval_condition(cond, {"waiting_minutes": 31}) is True


def test_semantic_equivalence_units():
    c1 = AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=30, unit="minutes")
    c2 = AtomicCondition(field="waiting_minutes", operator=Operator.GE, value=0.5, unit="hours")
    assert conditions_are_semantically_equivalent(c1, c2)


def test_specification_checker_detects_omission(effective_requirements):
    # Spec omitting R1
    s2 = SpecificationRule(
        spec_rule_id="S2",
        target_rule_id="R2",
        priority=1,
        condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True),
        action="priority",
    )
    spec_doc = SpecificationDocument(spec_id="SPEC-DEFECT", version=1, rules=[s2])
    checker = SpecificationChecker()
    findings = checker.check(effective_requirements, spec_doc)

    missing_r1 = [f for f in findings if f.rule_id == "R1"]
    assert len(missing_r1) == 1
    assert "omitted" in missing_r1[0].issue.lower()


def test_specification_checker_detects_boundary_defect(effective_requirements):
    # Spec using > 30 instead of >= 30
    s1 = SpecificationRule(spec_rule_id="S1", target_rule_id="R1", priority=1, condition=AtomicCondition(field="category", operator=Operator.IS_NULL), action="manual_review")
    s2 = SpecificationRule(spec_rule_id="S2", target_rule_id="R2", priority=2, condition=AtomicCondition(field="urgent", operator=Operator.EQ, value=True), action="priority")
    s3 = SpecificationRule(spec_rule_id="S3", target_rule_id="R3", priority=3, condition=AtomicCondition(field="waiting_minutes", operator=Operator.GT, value=30), action="escalation")
    s4 = SpecificationRule(spec_rule_id="S4", target_rule_id="R4", priority=4, condition=None, action="normal", is_fallback=True)

    spec_doc = SpecificationDocument(spec_id="SPEC-GT", version=1, rules=[s1, s2, s3, s4])
    checker = SpecificationChecker()
    findings = checker.check(effective_requirements, spec_doc)

    boundary_f = [f for f in findings if f.rule_id == "R3"]
    assert len(boundary_f) == 1
    assert "operator boundary" in boundary_f[0].issue.lower()
