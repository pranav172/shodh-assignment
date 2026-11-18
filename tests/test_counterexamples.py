"""Unit tests for counterexample generation."""

import pytest
from shodh.contracts import (
    AtomicCondition,
    Operator,
    PythonSnippet,
    RequirementsDocument,
    SourceRequirement,
)
from shodh.approvals import ApprovalResolver
from shodh.code_analyzer import CodeAnalyzer
from shodh.counterexamples import CounterexampleGenerator


@pytest.fixture
def canonical_requirements():
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


def test_generate_counterexample_for_precedence_bug(canonical_requirements):
    # Snippet checks urgent before missing category
    code = """
if ticket["urgent"]:
    return "priority"
if ticket["category"] is None:
    return "manual_review"
if ticket["waiting_minutes"] >= 30:
    return "escalation"
return "normal"
    """
    snippet = PythonSnippet(snippet_id="SNIP-PREC", file_path="workflow.py", line_start=1, line_end=7, code=code)
    analyzer = CodeAnalyzer(snippet)

    generator = CounterexampleGenerator(canonical_requirements)
    ce = generator.find_counterexample(lambda t: analyzer.simulate(t)[0])

    assert ce is not None
    assert ce["ticket"]["category"] is None
    assert ce["ticket"]["urgent"] is True
    assert ce["expected_route"] == "manual_review"
    assert ce["actual_route"] == "priority"


def test_generate_counterexample_for_boundary_bug(canonical_requirements):
    # Snippet uses > 30 instead of >= 30
    code = """
if ticket["category"] is None:
    return "manual_review"
if ticket["urgent"]:
    return "priority"
if ticket["waiting_minutes"] > 30:
    return "escalation"
return "normal"
    """
    snippet = PythonSnippet(snippet_id="SNIP-BOUND", file_path="workflow.py", line_start=1, line_end=7, code=code)
    analyzer = CodeAnalyzer(snippet)

    generator = CounterexampleGenerator(canonical_requirements)
    ce = generator.find_counterexample(lambda t: analyzer.simulate(t)[0])

    assert ce is not None
    assert ce["ticket"]["waiting_minutes"] == 30
    assert ce["expected_route"] == "escalation"
    assert ce["actual_route"] == "normal"
