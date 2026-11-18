"""Counterexample Generator.

Synthesizes concrete ticket inputs that deterministically prove behavioral
mismatches between effective requirements and implementations (specification,
workflow graph, or Python code), using bounded exhaustive boundary testing.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Dict, List, Optional, Set
from shodh.contracts import (
    AtomicCondition,
    CompoundCondition,
    Condition,
)
from shodh.approvals import EffectiveRequirement
from shodh.rule_engine import route_ticket_by_requirements


class CounterexampleGenerator:
    """Generates concrete counterexample tickets through bounded boundary exploration."""

    def __init__(self, effective_requirements: List[EffectiveRequirement]):
        self.requirements = effective_requirements

    def find_counterexample(
        self,
        actual_routing_fn: Callable[[Dict[str, Any]], Optional[str]],
        target_rule_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search bounded input domain for a ticket where:
            expected_route != actual_route.

        Returns counterexample dictionary or None.
        """
        test_tickets = self.generate_test_tickets()

        for ticket in test_tickets:
            expected_result = route_ticket_by_requirements(self.requirements, ticket)
            if not expected_result:
                continue
            expected_route, matched_rule_id = expected_result

            # If target_rule_id specified, filter for tickets triggering or impacted by it
            if target_rule_id and matched_rule_id != target_rule_id:
                # Also consider tickets where target_rule was supposed to trigger
                target_req = next((r for r in self.requirements if r.rule_id == target_rule_id), None)
                if not target_req:
                    continue

            actual_route = actual_routing_fn(ticket)

            if actual_route and actual_route != expected_route:
                return {
                    "ticket": ticket,
                    "expected_route": expected_route,
                    "actual_route": actual_route,
                }

        return None

    def generate_test_tickets(self) -> List[Dict[str, Any]]:
        """
        Construct a bounded exhaustive test grid based on active fields,
        categories, boolean states, and numeric boundary values (T-1, T, T+1).
        """
        # Collect all threshold values
        thresholds: Set[float] = {25.0, 30.0}  # Core SLA standards
        for req in self.requirements:
            self._collect_thresholds(req.condition, thresholds)

        waiting_values: Set[float] = {0.0}
        for t in thresholds:
            waiting_values.add(max(0.0, t - 1.0))
            waiting_values.add(t)
            waiting_values.add(t + 1.0)

        # Categorical domains
        category_domain = [None, "billing", "technical"]
        urgent_domain = [True, False]
        waiting_domain = sorted(list(waiting_values))

        # Generate combinatorial product
        tickets = []
        for cat, urg, wait in itertools.product(category_domain, urgent_domain, waiting_domain):
            tickets.append({
                "category": cat,
                "urgent": urg,
                "waiting_minutes": int(wait) if wait.is_integer() else wait,
            })

        return tickets

    def _collect_thresholds(self, cond: Optional[Condition], thresholds: Set[float]) -> None:
        """Extract numeric thresholds from conditions."""
        if not cond:
            return
        if isinstance(cond, AtomicCondition):
            val = cond.normalized_numeric_value()
            if val is not None:
                thresholds.add(val)
        elif isinstance(cond, CompoundCondition):
            for child in cond.conditions:
                self._collect_thresholds(child, thresholds)
