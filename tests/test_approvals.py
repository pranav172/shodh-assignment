"""Unit tests for the Approval and Revision Resolver."""

import pytest
from shodh.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    AtomicCondition,
    Operator,
    RequirementsDocument,
    Severity,
    SourceRequirement,
)
from shodh.approvals import ApprovalResolver


@pytest.fixture
def base_requirements_doc():
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
    return RequirementsDocument(doc_id="REQ-TEST", version=1, rules=[r1, r2, r3, r4])


def test_effective_requirements_without_approvals(base_requirements_doc):
    resolver = ApprovalResolver()
    effective, findings = resolver.resolve(base_requirements_doc, [])

    assert len(effective) == 4
    assert len(findings) == 0
    # Values unchanged
    assert effective[2].condition.value == 30
    assert not effective[2].is_modified


def test_approved_change_modifies_requirement(base_requirements_doc):
    # Approved change: update waiting_minutes from 30 to 25
    approval = ApprovalRecord(
        change_id="CHG-001",
        target_rule_id="R3",
        target_version=1,
        status=ApprovalStatus.APPROVED,
        author="lead@company.com",
        timestamp="2026-03-01T10:00:00Z",
        patch={"condition": {"value": 25}},
    )
    resolver = ApprovalResolver()
    effective, findings = resolver.resolve(base_requirements_doc, [approval])

    assert len(findings) == 0
    r3 = next(r for r in effective if r.rule_id == "R3")
    assert r3.condition.value == 25
    assert r3.is_modified is True
    assert r3.applied_changes == ["CHG-001"]


def test_unapproved_suggestion_ignored(base_requirements_doc):
    # Pending suggestion to change to 20 should be ignored
    pending = ApprovalRecord(
        change_id="CHG-PENDING",
        target_rule_id="R3",
        target_version=1,
        status=ApprovalStatus.PENDING,
        author="developer@company.com",
        timestamp="2026-03-02T10:00:00Z",
        patch={"condition": {"value": 20}},
    )
    # Rejected suggestion to change action
    rejected = ApprovalRecord(
        change_id="CHG-REJECTED",
        target_rule_id="R1",
        target_version=1,
        status=ApprovalStatus.REJECTED,
        author="intern@company.com",
        timestamp="2026-03-02T11:00:00Z",
        patch={"action": "ignore"},
    )
    resolver = ApprovalResolver()
    effective, findings = resolver.resolve(base_requirements_doc, [pending, rejected])

    assert len(findings) == 0
    r3 = next(r for r in effective if r.rule_id == "R3")
    assert r3.condition.value == 30  # Still 30, not 20
    assert not r3.is_modified

    r1 = next(r for r in effective if r.rule_id == "R1")
    assert r1.action == "manual_review"


def test_contradictory_approvals_generate_blocker(base_requirements_doc):
    # Two approved records claiming conflicting values targeting the same rule version
    app1 = ApprovalRecord(
        change_id="CHG-A",
        target_rule_id="R3",
        target_version=1,
        status=ApprovalStatus.APPROVED,
        author="manager-1@company.com",
        timestamp="2026-03-01T10:00:00Z",
        patch={"condition": {"value": 25}},
    )
    app2 = ApprovalRecord(
        change_id="CHG-B",
        target_rule_id="R3",
        target_version=1,
        status=ApprovalStatus.APPROVED,
        author="manager-2@company.com",
        timestamp="2026-03-01T10:00:00Z",
        patch={"condition": {"value": 20}},
    )
    resolver = ApprovalResolver()
    effective, findings = resolver.resolve(base_requirements_doc, [app1, app2])

    # Must produce a BLOCKER finding, not choose one arbitrarily
    blockers = [f for f in findings if f.severity == Severity.BLOCKER]
    assert len(blockers) == 1
    assert "Contradictory" in blockers[0].issue
    assert blockers[0].rule_id == "R3"


def test_orphan_approval_warning(base_requirements_doc):
    orphan = ApprovalRecord(
        change_id="CHG-UNKNOWN",
        target_rule_id="R999",
        target_version=1,
        status=ApprovalStatus.APPROVED,
        author="manager@company.com",
        timestamp="2026-03-01T10:00:00Z",
        patch={"action": "special"},
    )
    resolver = ApprovalResolver()
    effective, findings = resolver.resolve(base_requirements_doc, [orphan])

    warnings = [f for f in findings if f.severity == Severity.WARNING]
    assert len(warnings) == 1
    assert warnings[0].rule_id == "R999"
