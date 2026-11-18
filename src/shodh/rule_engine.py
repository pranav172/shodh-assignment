"""Semantic rule engine and specification checker.

Evaluates conditions against ticket payloads, checks semantic equivalence between
conditions, and validates structured specifications against effective requirements.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union
from shodh.contracts import (
    AtomicCondition,
    CompoundCondition,
    Condition,
    Finding,
    Operator,
    Severity,
    SpecificationDocument,
    SpecificationRule,
    UnsupportedCondition,
)
from shodh.approvals import EffectiveRequirement


def eval_atomic_condition(cond: AtomicCondition, ticket: Dict[str, Any]) -> bool:
    """Evaluate an AtomicCondition against a ticket dictionary."""
    field_val = ticket.get(cond.field)

    if cond.operator == Operator.IS_NULL:
        return field_val is None
    if cond.operator == Operator.IS_NOT_NULL:
        return field_val is not None

    # If field is missing and we're not checking is_null, comparison is False
    if field_val is None:
        return False

    # Normalize numeric units if applicable
    target_val = cond.value
    if cond.unit and isinstance(target_val, (int, float)):
        normalized_num = cond.normalized_numeric_value()
        if normalized_num is not None:
            target_val = normalized_num

    # For numeric comparison, cast field_val if possible
    if isinstance(target_val, (int, float)) and not isinstance(target_val, bool):
        try:
            field_val = float(field_val)
            target_val = float(target_val)
        except (ValueError, TypeError):
            return False

    if cond.operator == Operator.EQ:
        return field_val == target_val
    if cond.operator == Operator.NE:
        return field_val != target_val
    if cond.operator == Operator.GT:
        return field_val > target_val
    if cond.operator == Operator.GE:
        return field_val >= target_val
    if cond.operator == Operator.LT:
        return field_val < target_val
    if cond.operator == Operator.LE:
        return field_val <= target_val
    if cond.operator == Operator.IN:
        return field_val in target_val
    if cond.operator == Operator.NOT_IN:
        return field_val not in target_val

    return False


def eval_condition(cond: Optional[Condition], ticket: Dict[str, Any]) -> bool:
    """Evaluate any Condition (Atomic, Compound, Unsupported) against a ticket."""
    if cond is None:
        return True  # Catch-all fallback matches everything

    if isinstance(cond, UnsupportedCondition):
        return False  # Unsupported cannot be deterministically evaluated

    if isinstance(cond, AtomicCondition):
        return eval_atomic_condition(cond, ticket)

    if isinstance(cond, CompoundCondition):
        if cond.combinator == "and":
            return all(eval_condition(c, ticket) for c in cond.conditions)
        elif cond.combinator == "or":
            return any(eval_condition(c, ticket) for c in cond.conditions)
        elif cond.combinator == "not":
            return not eval_condition(cond.conditions[0], ticket)

    return False


def route_ticket_by_requirements(
    requirements: List[EffectiveRequirement],
    ticket: Dict[str, Any],
) -> Optional[Tuple[str, str]]:
    """
    Simulate ticket routing through ordered requirements.
    Returns (action, matched_rule_id) or None.
    """
    for req in sorted(requirements, key=lambda r: r.priority):
        if req.is_fallback or eval_condition(req.condition, ticket):
            return req.action, req.rule_id
    return None


def conditions_are_semantically_equivalent(
    c1: Optional[Condition],
    c2: Optional[Condition],
) -> bool:
    """
    Check if two conditions are semantically equivalent within supported grammar.
    """
    if c1 is None and c2 is None:
        return True
    if c1 is None or c2 is None:
        return False

    if isinstance(c1, AtomicCondition) and isinstance(c2, AtomicCondition):
        if c1.field != c2.field:
            return False
        if c1.operator != c2.operator:
            return False
        # Normalize numeric values
        v1 = c1.normalized_numeric_value()
        v2 = c2.normalized_numeric_value()
        if v1 is not None and v2 is not None:
            return abs(v1 - v2) < 1e-6
        return c1.value == c2.value

    if isinstance(c1, CompoundCondition) and isinstance(c2, CompoundCondition):
        if c1.combinator != c2.combinator:
            return False
        if len(c1.conditions) != len(c2.conditions):
            return False
        # Check all child conditions match
        return all(
            any(conditions_are_semantically_equivalent(sc1, sc2) for sc2 in c2.conditions)
            for sc1 in c1.conditions
        )

    return False


class SpecificationChecker:
    """Validates structured specification against effective requirements."""

    def check(
        self,
        effective_requirements: List[EffectiveRequirement],
        spec_doc: SpecificationDocument,
    ) -> List[Finding]:
        """
        Verify that every effective requirement exists in the specification,
        checking for omitted rules, changed thresholds, operator mismatches,
        and action discrepancies.
        """
        findings: List[Finding] = []
        spec_by_target = {s.target_rule_id: s for s in spec_doc.rules if s.target_rule_id}

        for req in effective_requirements:
            rule_id = req.rule_id
            spec_rule = spec_by_target.get(rule_id)

            # 1. Missing / Omitted Requirement
            if not spec_rule:
                findings.append(
                    Finding(
                        finding_id=f"FIND-SPEC-MISSING-{rule_id}",
                        rule_id=rule_id,
                        severity=Severity.BLOCKER,
                        issue="Requirement omitted from specification",
                        expected=f"Specification includes rule for '{rule_id}' with action '{req.action}'",
                        actual=f"Rule '{rule_id}' is completely missing from specification '{spec_doc.spec_id}'",
                        evidence=req.evidence_location,
                        correction=f"Add specification rule mapping to '{rule_id}'.",
                    )
                )
                continue

            # 2. Action Mismatch
            if spec_rule.action != req.action:
                findings.append(
                    Finding(
                        finding_id=f"FIND-SPEC-ACTION-{rule_id}",
                        rule_id=rule_id,
                        severity=Severity.BLOCKER,
                        issue="Specification action mismatch",
                        expected=f"Action '{req.action}'",
                        actual=f"Action '{spec_rule.action}'",
                        evidence=spec_rule.evidence or spec_doc.spec_id,
                        correction=f"Change specification action from '{spec_rule.action}' to '{req.action}'.",
                    )
                )

            # 3. Priority / Precedence Mismatch
            if spec_rule.priority != req.priority:
                findings.append(
                    Finding(
                        finding_id=f"FIND-SPEC-PRIORITY-{rule_id}",
                        rule_id=rule_id,
                        severity=Severity.BLOCKER,
                        issue="Incorrect rule precedence in specification",
                        expected=f"Priority {req.priority}",
                        actual=f"Priority {spec_rule.priority}",
                        evidence=spec_rule.evidence or spec_doc.spec_id,
                        correction=f"Reorder specification rule to priority {req.priority}.",
                    )
                )

            # 4. Condition Semantic Equivalence Check
            if not conditions_are_semantically_equivalent(req.condition, spec_rule.condition):
                # Pinpoint exact difference
                issue_desc = "Specification condition semantic mismatch"
                expected_desc = str(req.condition)
                actual_desc = str(spec_rule.condition)

                if isinstance(req.condition, AtomicCondition) and isinstance(spec_rule.condition, AtomicCondition):
                    if req.condition.operator != spec_rule.condition.operator:
                        issue_desc = "Incorrect comparison operator boundary in specification"
                        expected_desc = f"Operator '{req.condition.operator.value}'"
                        actual_desc = f"Operator '{spec_rule.condition.operator.value}'"
                    elif req.condition.normalized_numeric_value() != spec_rule.condition.normalized_numeric_value():
                        issue_desc = "Altered threshold value in specification"
                        expected_desc = f"Threshold {req.condition.normalized_numeric_value()}"
                        actual_desc = f"Threshold {spec_rule.condition.normalized_numeric_value()}"

                findings.append(
                    Finding(
                        finding_id=f"FIND-SPEC-COND-{rule_id}",
                        rule_id=rule_id,
                        severity=Severity.BLOCKER,
                        issue=issue_desc,
                        expected=expected_desc,
                        actual=actual_desc,
                        evidence=spec_rule.evidence or spec_doc.spec_id,
                        correction=f"Align specification condition with effective requirement: {req.raw_text or expected_desc}",
                    )
                )

        return findings
