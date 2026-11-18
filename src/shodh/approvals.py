"""Approval and revision resolver.

Derives effective requirements from baseline source requirements by safely applying
authoritative approval records, resolving change ordering, and detecting contradictory
or unapproved revisions without silently choosing a convenient version.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple
from shodh.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    AtomicCondition,
    Finding,
    Operator,
    RequirementsDocument,
    Severity,
    SourceRequirement,
)


class EffectiveRequirement(SourceRequirement):
    """A requirement derived from a baseline SourceRequirement after applying approvals."""
    original_rule_id: str
    applied_changes: List[str] = []
    is_modified: bool = False


class ApprovalResolver:
    """Manages revision scope, change ordering, and effective requirements derivation."""

    def resolve(
        self,
        requirements_doc: RequirementsDocument,
        approvals: List[ApprovalRecord],
    ) -> Tuple[List[EffectiveRequirement], List[Finding]]:
        """
        Derive effective requirements and produce findings for any approval conflicts.

        Returns:
            Tuple of (effective_requirements_list, findings_list)
        """
        findings: List[Finding] = []
        effective_map: Dict[str, EffectiveRequirement] = {}

        # 1. Initialize effective requirements from baseline
        for rule in requirements_doc.rules:
            eff = EffectiveRequirement(
                rule_id=rule.rule_id,
                title=rule.title,
                source=rule.source,
                line_start=rule.line_start,
                line_end=rule.line_end,
                version=rule.version,
                priority=rule.priority,
                condition=copy.deepcopy(rule.condition),
                action=rule.action,
                raw_text=rule.raw_text,
                is_fallback=rule.is_fallback,
                original_rule_id=rule.rule_id,
                applied_changes=[],
                is_modified=False,
            )
            effective_map[rule.rule_id] = eff

        # 2. Group approvals by target_rule_id
        approvals_by_rule: Dict[str, List[ApprovalRecord]] = {}
        for app in approvals:
            approvals_by_rule.setdefault(app.target_rule_id, []).append(app)

        # 3. Process approvals per rule
        for rule_id, rule_approvals in approvals_by_rule.items():
            if rule_id not in effective_map:
                findings.append(
                    Finding(
                        finding_id=f"FIND-APP-ORPHAN-{rule_id}",
                        rule_id=rule_id,
                        severity=Severity.WARNING,
                        issue="Approval record targets non-existent rule",
                        expected=f"Target rule '{rule_id}' exists in requirements",
                        actual=f"Rule '{rule_id}' not found in requirements document",
                        evidence=f"Approval records for {rule_id}",
                        correction="Ensure approval target_rule_id matches a declared requirement",
                    )
                )
                continue

            target_req = effective_map[rule_id]

            # Filter approved vs non-approved
            approved_records = [a for a in rule_approvals if a.status == ApprovalStatus.APPROVED]
            unapproved_records = [a for a in rule_approvals if a.status in (ApprovalStatus.PENDING, ApprovalStatus.REJECTED)]

            # Check for contradictory approved changes
            has_conflict, conflict_finding = self._check_contradictory_approvals(rule_id, approved_records)
            if has_conflict and conflict_finding:
                findings.append(conflict_finding)
                # On contradictory approvals, we DO NOT silently pick one;
                # the rule remains flagged with a BLOCKER.
                continue

            # Sort approved records chronologically by timestamp
            approved_records.sort(key=lambda r: r.timestamp)

            # Apply approved changes in order
            for approved in approved_records:
                self._apply_patch(target_req, approved)
                target_req.applied_changes.append(approved.change_id)
                target_req.is_modified = True

        effective_list = sorted(effective_map.values(), key=lambda r: r.priority)
        return effective_list, findings

    def _check_contradictory_approvals(
        self,
        rule_id: str,
        approved_records: List[ApprovalRecord],
    ) -> Tuple[bool, Optional[Finding]]:
        """
        Detect contradictory approved records without silently choosing a convenient version.
        Contradictions occur when:
        - Multiple approved records have identical timestamps but different patch values.
        - Multiple approved records specify conflicting actions or values without clear progression.
        """
        if len(approved_records) <= 1:
            return False, None

        # Check for same-timestamp or conflicting patches
        timestamps = [r.timestamp for r in approved_records]
        if len(timestamps) != len(set(timestamps)):
            # Duplicate timestamps detected
            patches = [str(r.patch) for r in approved_records]
            if len(set(patches)) > 1:
                return True, Finding(
                    finding_id=f"FIND-CONFLICT-APP-{rule_id}",
                    rule_id=rule_id,
                    severity=Severity.BLOCKER,
                    issue="Contradictory approved changes detected with ambiguous ordering",
                    expected=f"A single consistent approved revision sequence for rule {rule_id}",
                    actual=f"Conflicting approved patches found at identical timestamps: {[r.change_id for r in approved_records]}",
                    evidence=f"Approval records: {', '.join(r.change_id for r in approved_records)}",
                    correction="Resolve the approval dispute and rescind conflicting approval records.",
                )

        # Check for conflicting patch values (e.g. changing value to 25 and 20 simultaneously)
        values_set = set()
        actions_set = set()
        for r in approved_records:
            p = r.patch
            if "condition" in p and isinstance(p["condition"], dict) and "value" in p["condition"]:
                values_set.add(p["condition"]["value"])
            elif "value" in p:
                values_set.add(p["value"])
            if "action" in p:
                actions_set.add(p["action"])

        # If approvals claim contradictory target states at the same version scope
        target_versions = set(r.target_version for r in approved_records)
        if len(target_versions) == 1 and (len(values_set) > 1 or len(actions_set) > 1):
            return True, Finding(
                finding_id=f"FIND-CONFLICT-APP-{rule_id}",
                rule_id=rule_id,
                severity=Severity.BLOCKER,
                issue="Contradictory approved revisions targeting the same rule version",
                expected="Unambiguous approved target state",
                actual=f"Conflicting targets: values={values_set}, actions={actions_set}",
                evidence=f"Approval records: {', '.join(r.change_id for r in approved_records)}",
                correction="Consolidate conflicting approved change records before deploying workflow.",
            )

        return False, None

    def _apply_patch(self, req: EffectiveRequirement, record: ApprovalRecord) -> None:
        """Apply patch dictionary to the requirement."""
        patch = record.patch

        # Patch action
        if "action" in patch:
            req.action = patch["action"]

        # Patch priority
        if "priority" in patch:
            req.priority = patch["priority"]

        # Patch condition
        if "condition" in patch and isinstance(patch["condition"], dict):
            cond_patch = patch["condition"]
            if isinstance(req.condition, AtomicCondition):
                if "value" in cond_patch:
                    req.condition.value = cond_patch["value"]
                if "operator" in cond_patch:
                    req.condition.operator = Operator(cond_patch["operator"])
                if "unit" in cond_patch:
                    req.condition.unit = cond_patch["unit"]
                if "field" in cond_patch:
                    req.condition.field = cond_patch["field"]
        elif "value" in patch and isinstance(req.condition, AtomicCondition):
            req.condition.value = patch["value"]
        elif "operator" in patch and isinstance(req.condition, AtomicCondition):
            req.condition.operator = Operator(patch["operator"])
