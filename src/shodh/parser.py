"""Rule parser and supported language normalizer.

Converts business policy statements and natural-language conditions into
canonical, strongly-typed SourceRequirement and Condition objects while
preserving evidence locations and highlighting unsupported grammar.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple, Union
from shodh.contracts import (
    AtomicCondition,
    CompoundCondition,
    Condition,
    Operator,
    RequirementsDocument,
    SourceRequirement,
    TimeUnit,
    UnsupportedCondition,
)

# Standard field alias mapping
FIELD_ALIASES = {
    "waiting": "waiting_minutes",
    "waiting time": "waiting_minutes",
    "waiting_time": "waiting_minutes",
    "wait time": "waiting_minutes",
    "waiting_minutes": "waiting_minutes",
    "category": "category",
    "ticket category": "category",
    "urgent": "urgent",
    "urgency": "urgent",
    "priority": "priority",
}

# Action string normalizer
def normalize_action(action_str: str) -> str:
    cleaned = action_str.strip().lower().replace(" ", "_")
    cleaned = cleaned.rstrip(".")
    # Common mappings
    if cleaned in ("manual_review", "manual", "manual_queue"):
        return "manual_review"
    if cleaned in ("priority", "priority_queue"):
        return "priority"
    if cleaned in ("escalation", "escalate", "escalation_queue"):
        return "escalation"
    if cleaned in ("normal", "normal_queue", "standard", "standard_queue"):
        return "normal"
    return cleaned


class RuleParser:
    """Parses text business rules into validated RequirementsDocuments."""

    def __init__(self, default_source: str = "support_policy.md"):
        self.default_source = default_source

    def parse_document(self, text: str, doc_id: str = "REQ-DOC-1", version: int = 1) -> RequirementsDocument:
        """Parse multi-line policy document into RequirementsDocument."""
        lines = text.splitlines()
        rules: List[SourceRequirement] = []
        priority = 1

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            rule = self.parse_line(
                line=stripped,
                line_no=idx,
                priority=priority,
                version=version,
            )
            if rule:
                rules.append(rule)
                priority += 1

        return RequirementsDocument(
            doc_id=doc_id,
            version=version,
            rules=rules,
        )

    def parse_line(
        self,
        line: str,
        line_no: int,
        priority: int,
        version: int = 1,
    ) -> Optional[SourceRequirement]:
        """Parse a single rule line into a SourceRequirement."""
        raw_text = line.strip()

        # Extract Rule ID if present (e.g. "R1", "R2:", "[R3]")
        rule_id_match = re.match(r"^\[?([A-Za-z0-9_]+)\]?[:\.\s-]\s*(.*)$", line)
        if rule_id_match and rule_id_match.group(1).upper().startswith("R"):
            rule_id = rule_id_match.group(1).upper()
            content = rule_id_match.group(2).strip()
        else:
            rule_id = f"R{priority}"
            content = line

        # Split on action delimiter: '->' or 'route to' or 'assign to'
        action_match = re.search(r"\s*(?:->|route to|assign to)\s*(.+)$", content, re.IGNORECASE)
        if not action_match:
            # Fallback for catch-all statements like "All remaining tickets -> normal queue"
            if re.search(r"remaining\s+tickets", content, re.IGNORECASE):
                action = "normal"
                is_fallback = True
                condition = None
                return SourceRequirement(
                    rule_id=rule_id,
                    source=self.default_source,
                    line_start=line_no,
                    line_end=line_no,
                    version=version,
                    priority=priority,
                    condition=condition,
                    action=action,
                    raw_text=raw_text,
                    is_fallback=is_fallback,
                )
            return None

        condition_text = content[:action_match.start()].strip()
        raw_action = action_match.group(1).strip()
        action = normalize_action(raw_action)

        # Clean condition prefixes like "Otherwise,", "If", "When"
        clean_cond = re.sub(r"^(?:otherwise,?\s*|if\s*|when\s*)", "", condition_text, flags=re.IGNORECASE).strip()

        # Check for fallback / catch-all
        if re.search(r"^(?:all\s+)?remaining\s+tickets?|otherwise|default$", clean_cond, re.IGNORECASE):
            return SourceRequirement(
                rule_id=rule_id,
                source=self.default_source,
                line_start=line_no,
                line_end=line_no,
                version=version,
                priority=priority,
                condition=None,
                action=action,
                raw_text=raw_text,
                is_fallback=True,
            )

        condition = self.parse_condition(clean_cond)

        return SourceRequirement(
            rule_id=rule_id,
            source=self.default_source,
            line_start=line_no,
            line_end=line_no,
            version=version,
            priority=priority,
            condition=condition,
            action=action,
            raw_text=raw_text,
            is_fallback=False,
        )

    def parse_condition(self, text: str) -> Condition:
        """Parse condition string into an AtomicCondition, CompoundCondition, or UnsupportedCondition."""
        stripped = text.strip()

        # Check for logical OR (top-level)
        if " or " in stripped.lower():
            parts = re.split(r"\s+or\s+", stripped, flags=re.IGNORECASE)
            sub_conds = [self.parse_condition(p) for p in parts]
            return CompoundCondition(combinator="or", conditions=sub_conds)

        # Check for logical AND (top-level)
        if " and " in stripped.lower():
            parts = re.split(r"\s+and\s+", stripped, flags=re.IGNORECASE)
            sub_conds = [self.parse_condition(p) for p in parts]
            return CompoundCondition(combinator="and", conditions=sub_conds)

        # Parse atomic condition
        return self._parse_atomic(stripped)

    def _parse_atomic(self, text: str) -> Condition:
        """Parse single atomic condition."""
        s = text.strip()

        # 1. Missingness / Null checks
        # "Missing category", "category is missing", "category is null", "category is None"
        m_missing = re.match(r"^(?:missing\s+([a-zA-Z_0-9]+)|([a-zA-Z_0-9]+)\s+is\s+(?:missing|null|none))$", s, re.IGNORECASE)
        if m_missing:
            field_raw = m_missing.group(1) or m_missing.group(2)
            field = FIELD_ALIASES.get(field_raw.lower(), field_raw.lower())
            return AtomicCondition(field=field, operator=Operator.IS_NULL)

        # 2. Existence / Not Null checks
        # "category exists", "category is present", "category is not null"
        m_exists = re.match(r"^([a-zA-Z_0-9]+)\s+(?:exists|is\s+present|is\s+not\s+(?:null|none))$", s, re.IGNORECASE)
        if m_exists:
            field_raw = m_exists.group(1)
            field = FIELD_ALIASES.get(field_raw.lower(), field_raw.lower())
            return AtomicCondition(field=field, operator=Operator.IS_NOT_NULL)

        # 3. Numeric comparisons with optional units
        # e.g., "waiting >= 30 minutes", "waiting at least 30 min", "waiting > 30 minutes", "waiting <= 25"
        num_patterns = [
            (r"^([a-zA-Z_0-9\s]+?)\s*(?:>=|at least|is at least)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$", Operator.GE),
            (r"^([a-zA-Z_0-9\s]+?)\s*(?:<=|at most|is at most|up to)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$", Operator.LE),
            (r"^([a-zA-Z_0-9\s]+?)\s*(?:>|more than|exceeds|longer than)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$", Operator.GT),
            (r"^([a-zA-Z_0-9\s]+?)\s*(?:<|less than|under)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$", Operator.LT),
            (r"^([a-zA-Z_0-9\s]+?)\s*(?:==|equals|is)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$", Operator.EQ),
        ]
        for pattern, op in num_patterns:
            m = re.match(pattern, s, re.IGNORECASE)
            if m:
                field_raw = m.group(1).strip().lower()
                field = FIELD_ALIASES.get(field_raw, field_raw.replace(" ", "_"))
                val = float(m.group(2)) if "." in m.group(2) else int(m.group(2))
                unit = m.group(3).lower() if m.group(3) else ("minutes" if "waiting" in field else None)
                return AtomicCondition(field=field, operator=op, value=val, unit=unit)

        # 4. Boolean flags
        # "urgent ticket", "ticket is urgent", "urgent", "urgent is true"
        m_bool_true = re.match(r"^(?:(?:ticket\s+is\s+)?urgent(?:\s+ticket)?|([a-zA-Z_0-9]+)\s+is\s+true)$", s, re.IGNORECASE)
        if m_bool_true:
            field_raw = m_bool_true.group(1) or "urgent"
            field = FIELD_ALIASES.get(field_raw.lower(), field_raw.lower())
            return AtomicCondition(field=field, operator=Operator.EQ, value=True)

        m_bool_false = re.match(r"^(?:not\s+urgent(?:\s+ticket)?|ticket\s+is\s+not\s+urgent|([a-zA-Z_0-9]+)\s+is\s+false)$", s, re.IGNORECASE)
        if m_bool_false:
            field_raw = m_bool_false.group(1) or "urgent"
            field = FIELD_ALIASES.get(field_raw.lower(), field_raw.lower())
            return AtomicCondition(field=field, operator=Operator.EQ, value=False)

        # 5. String Equality: category is "billing"
        m_str_eq = re.match(r"^([a-zA-Z_0-9]+)\s+(?:is|==)\s+[\"']?([a-zA-Z_0-9]+)[\"']?$", s, re.IGNORECASE)
        if m_str_eq:
            field_raw = m_str_eq.group(1)
            field = FIELD_ALIASES.get(field_raw.lower(), field_raw.lower())
            val = m_str_eq.group(2)
            return AtomicCondition(field=field, operator=Operator.EQ, value=val)

        # Fallback: Content is unsupported or ambiguous
        return UnsupportedCondition(
            raw_text=text,
            reason="Expression does not match recognized deterministic grammar patterns",
            flag="UNSUPPORTED",
        )
