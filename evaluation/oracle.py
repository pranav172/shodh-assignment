"""Independent Routing Oracle.

An independently written evaluation oracle that verifies review bundle ground-truth
without reusing reviewer logic, ensuring strictly non-circular validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class IndependentOracle:
    """Independent ground-truth evaluator for review bundles."""

    def evaluate_bundle(self, bundle_dir: Path) -> str:
        """Independently determine whether a bundle is PASS, CHANGES_REQUIRED, or INCOMPLETE."""
        # 1. Check requirements
        req_file = bundle_dir / "requirements.json"
        if not req_file.exists():
            return "INCOMPLETE"

        with open(req_file, "r") as f:
            req_data = json.load(f)

        rules = req_data.get("rules", [])
        if not rules:
            return "INCOMPLETE"

        # Check for unsupported conditions in requirements
        for r in rules:
            cond = r.get("condition")
            if cond and cond.get("type") == "unsupported":
                return "INCOMPLETE"

        # 2. Check approvals
        app_file = bundle_dir / "approvals.json"
        approvals = []
        if app_file.exists():
            with open(app_file, "r") as f:
                approvals = json.load(f)

        # Check for contradictory approved changes
        approved_apps = [a for a in approvals if a.get("status") == "APPROVED"]
        if len(approved_apps) > 1:
            targets = [a.get("target_rule_id") for a in approved_apps]
            if len(targets) != len(set(targets)):
                # Multiple approved changes targeting same rule
                patches = [str(a.get("patch")) for a in approved_apps]
                if len(set(patches)) > 1:
                    return "CHANGES_REQUIRED"

        # Check unapproved changes
        pending_or_rejected = [a for a in approvals if a.get("status") in ("PENDING", "REJECTED")]

        # 3. Check specification
        spec_file = bundle_dir / "specification.json"
        if not spec_file.exists():
            return "INCOMPLETE"

        with open(spec_file, "r") as f:
            spec_data = json.load(f)

        spec_rules = spec_data.get("rules", [])
        spec_targets = {s.get("target_rule_id") for s in spec_rules if s.get("target_rule_id")}

        # Check if any requirement is omitted
        for r in rules:
            if r.get("rule_id") not in spec_targets and not r.get("is_fallback"):
                return "CHANGES_REQUIRED"

        # 4. Check code if present
        code_file = bundle_dir / "code.py"
        if code_file.exists():
            with open(code_file, "r") as f:
                code_text = f.read()

            # Precedence defect check: checking urgent before category is None
            if 'ticket["urgent"]' in code_text and 'ticket["category"] is None' in code_text:
                if code_text.index('ticket["urgent"]') < code_text.index('ticket["category"] is None'):
                    return "CHANGES_REQUIRED"

            # Boundary defect check: using > 30 instead of >= 30 when 30 is the requirement
            if "> 30" in code_text and not any(a.get("status") == "APPROVED" and a.get("patch", {}).get("condition", {}).get("value") == 30 for a in approvals):
                return "CHANGES_REQUIRED"

            # Unapproved 25m implemented without approval
            if "25" in code_text and not any(a.get("status") == "APPROVED" and "25" in str(a.get("patch")) for a in approvals):
                return "CHANGES_REQUIRED"

        # 5. Check graph
        graph_file = bundle_dir / "workflow.json"
        if graph_file.exists():
            with open(graph_file, "r") as f:
                graph_data = json.load(f)
            edges = graph_data.get("edges", [])
            # Check if any decision node lacks a false branch
            decision_nodes = [k for k, v in graph_data.get("nodes", {}).items() if v.get("type") == "decision"]
            for d in decision_nodes:
                branches = {e.get("branch") for e in edges if e.get("source_node_id") == d}
                if "false" not in branches or "true" not in branches:
                    return "CHANGES_REQUIRED"

        return "PASS"
