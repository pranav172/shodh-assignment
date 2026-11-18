"""Unit tests for the SHODH Rule Parser and Language Normalizer."""

import pytest
from shodh.contracts import Operator
from shodh.parser import RuleParser, normalize_action


def test_normalize_action():
    assert normalize_action("manual review") == "manual_review"
    assert normalize_action("priority queue") == "priority"
    assert normalize_action("escalation.") == "escalation"
    assert normalize_action("normal queue") == "normal"


def test_parse_canonical_business_rules():
    doc_text = """
    R1 Missing category -> manual review.
    R2 Otherwise, urgent ticket -> priority queue.
    R3 Otherwise, waiting >= 30 minutes -> escalation.
    All remaining tickets -> normal queue.
    """
    parser = RuleParser(default_source="support_policy.md")
    req_doc = parser.parse_document(doc_text, doc_id="REQ-TEST", version=1)

    assert len(req_doc.rules) == 4

    # R1
    r1 = req_doc.rules[0]
    assert r1.rule_id == "R1"
    assert r1.priority == 1
    assert r1.action == "manual_review"
    assert r1.condition.field == "category"
    assert r1.condition.operator == Operator.IS_NULL
    assert r1.evidence_location == "support_policy.md:2"

    # R2
    r2 = req_doc.rules[1]
    assert r2.rule_id == "R2"
    assert r2.priority == 2
    assert r2.action == "priority"
    assert r2.condition.field == "urgent"
    assert r2.condition.operator == Operator.EQ
    assert r2.condition.value is True

    # R3
    r3 = req_doc.rules[2]
    assert r3.rule_id == "R3"
    assert r3.priority == 3
    assert r3.action == "escalation"
    assert r3.condition.field == "waiting_minutes"
    assert r3.condition.operator == Operator.GE
    assert r3.condition.value == 30
    assert r3.condition.unit == "minutes"

    # R4 (Fallback)
    r4 = req_doc.rules[3]
    assert r4.priority == 4
    assert r4.action == "normal"
    assert r4.is_fallback is True
    assert r4.condition is None


def test_parse_boundary_variations():
    parser = RuleParser()

    # "at least 30 minutes"
    r_ge = parser.parse_line("R3: waiting at least 30 minutes -> escalation", 1, 1)
    assert r_ge.condition.operator == Operator.GE
    assert r_ge.condition.value == 30

    # "more than 30 minutes"
    r_gt = parser.parse_line("R3: waiting more than 30 minutes -> escalation", 2, 2)
    assert r_gt.condition.operator == Operator.GT
    assert r_gt.condition.value == 30


def test_parse_compound_conditions():
    parser = RuleParser()
    rule = parser.parse_line(
        "urgent ticket and category exists -> priority",
        1,
        1,
    )
    assert rule.condition.type == "compound"
    assert rule.condition.combinator == "and"
    assert len(rule.condition.conditions) == 2
    assert rule.condition.conditions[0].field == "urgent"
    assert rule.condition.conditions[1].field == "category"
    assert rule.condition.conditions[1].operator == Operator.IS_NOT_NULL


def test_unsupported_condition_retained_in_rule():
    parser = RuleParser()
    rule = parser.parse_line(
        "R9: If the customer tone is visibly frustrated -> vip_support",
        1,
        1,
    )
    assert rule.rule_id == "R9"
    assert rule.condition.type == "unsupported"
    assert rule.condition.flag == "UNSUPPORTED"
    assert "tone is visibly frustrated" in rule.condition.raw_text
    assert rule.action == "vip_support"
