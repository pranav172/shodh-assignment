"""Unit tests for Python AST Code Analyzer."""

import pytest
from shodh.contracts import Operator, PythonSnippet
from shodh.code_analyzer import CodeAnalyzer


def test_code_analyzer_extracts_canonical_buggy_snippet():
    code = """
if ticket["urgent"]:
    return "priority"
if ticket["category"] is None:
    return "manual_review"
if ticket["waiting_minutes"] > 30:
    return "escalation"
return "normal"
    """
    snippet = PythonSnippet(
        snippet_id="SNIP-BUGGY",
        file_path="workflow.py",
        line_start=1,
        line_end=8,
        code=code,
    )
    analyzer = CodeAnalyzer(snippet)
    assert len(analyzer.extracted_rules) == 4

    # Rule 0 is urgent check (Precedence bug!)
    assert analyzer.extracted_rules[0].condition.field == "urgent"
    assert analyzer.extracted_rules[0].action == "priority"

    # Rule 1 is category is None
    assert analyzer.extracted_rules[1].condition.field == "category"
    assert analyzer.extracted_rules[1].condition.operator == Operator.IS_NULL

    # Rule 2 is waiting_minutes > 30 (Boundary bug!)
    assert analyzer.extracted_rules[2].condition.field == "waiting_minutes"
    assert analyzer.extracted_rules[2].condition.operator == Operator.GT
    assert analyzer.extracted_rules[2].condition.value == 30

    # Simulation reveals the precedence defect
    # A ticket with category None and urgent True
    route, line = analyzer.simulate({"category": None, "urgent": True, "waiting_minutes": 10})
    assert route == "priority"  # Bug: returns priority instead of manual_review!


def test_code_analyzer_handles_operator_inversion():
    # Inverted condition: 30 <= ticket["waiting_minutes"]
    code = """
if 30 <= ticket["waiting_minutes"]:
    return "escalation"
return "normal"
    """
    snippet = PythonSnippet(
        snippet_id="SNIP-INVERTED",
        file_path="workflow.py",
        line_start=1,
        line_end=4,
        code=code,
    )
    analyzer = CodeAnalyzer(snippet)
    assert len(analyzer.extracted_rules) == 2

    # Should be normalized to waiting_minutes >= 30
    cond = analyzer.extracted_rules[0].condition
    assert cond.field == "waiting_minutes"
    assert cond.operator == Operator.GE
    assert cond.value == 30

    # Test simulation at boundary 30
    route, _ = analyzer.simulate({"waiting_minutes": 30})
    assert route == "escalation"
