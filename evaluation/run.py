"""Single CPU-only evaluation benchmark runner for SHODH reviewer.

Loads all 12 frozen evaluation bundles, compares against independent oracle labels,
computes metrics, and writes machine-readable reports.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from shodh.contracts import (
    ApprovalDocument,
    PythonSnippet,
    RequirementsDocument,
    SpecificationDocument,
    WorkflowGraph,
)
from shodh.model_client import FakeModelClient
from shodh.reviewer import WorkflowReviewer
from evaluation.oracle import IndependentOracle
from evaluation.metrics import MetricsCalculator

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_bundle(bundle_dir: Path) -> Dict[str, Any]:
    """Load JSON/Python files in a bundle directory into Pydantic models."""
    # Requirements
    with open(bundle_dir / "requirements.json", "r") as f:
        req_doc = RequirementsDocument.model_validate_json(f.read())

    # Specification (optional)
    spec_doc = None
    if (bundle_dir / "specification.json").exists():
        with open(bundle_dir / "specification.json", "r") as f:
            spec_doc = SpecificationDocument.model_validate_json(f.read())

    # Workflow graph (optional)
    graph = None
    if (bundle_dir / "workflow.json").exists():
        with open(bundle_dir / "workflow.json", "r") as f:
            graph = WorkflowGraph.model_validate_json(f.read())

    # Code snippet (optional)
    snippet = None
    if (bundle_dir / "code.py").exists():
        with open(bundle_dir / "code.py", "r") as f:
            code_text = f.read()
        snippet = PythonSnippet(
            snippet_id=f"SNIP-{bundle_dir.name}",
            file_path="workflow.py",
            line_start=1,
            line_end=len(code_text.splitlines()),
            code=code_text,
        )

    # Approvals
    approvals = []
    if (bundle_dir / "approvals.json").exists():
        with open(bundle_dir / "approvals.json", "r") as f:
            app_doc = ApprovalDocument(doc_id=f"APP-{bundle_dir.name}", records=json.load(f))
            approvals = app_doc.records

    return {
        "requirements": req_doc,
        "specification": spec_doc,
        "workflow": graph,
        "code": snippet,
        "approvals": approvals,
    }


def run_evaluation(held_out_only: bool = False) -> Dict[str, Any]:
    """Run evaluation across all frozen bundles."""
    with open(FIXTURES_DIR / "expected_labels.json", "r") as f:
        expected_meta = json.load(f)

    oracle = IndependentOracle()
    eval_results: List[Dict[str, Any]] = []

    print(f"\n{'='*75}")
    print(f"SHODH EVALUATION BENCHMARK RUNNER")
    print(f"{'='*75}\n")
    print(f"{'Bundle ID':<35} | {'Oracle Expected':<16} | {'Actual Status':<16} | {'Match'}")
    print(f"{'-'*75}")

    for bundle_id, meta in sorted(expected_meta.items()):
        if held_out_only and not meta.get("held_out"):
            continue

        bundle_dir = FIXTURES_DIR / bundle_id
        if not bundle_dir.exists():
            continue

        # Get independent oracle label
        oracle_label = oracle.evaluate_bundle(bundle_dir)

        # Run reviewer with FakeModelClient
        fake_client = FakeModelClient()
        reviewer = WorkflowReviewer(model_client=fake_client)
        bundle_data = load_bundle(bundle_dir)

        t0 = time.time()
        report = reviewer.review(
            requirements_doc=bundle_data["requirements"],
            spec_doc=bundle_data["specification"],
            workflow_graph=bundle_data["workflow"],
            code_snippet=bundle_data["code"],
            approvals=bundle_data["approvals"],
        )
        elapsed = time.time() - t0

        actual_status = report.status.value
        matched = (actual_status == oracle_label)

        has_ce = any(f.counterexample is not None for f in report.findings)

        eval_results.append({
            "bundle_id": bundle_id,
            "description": meta["description"],
            "held_out": meta.get("held_out", False),
            "expected": oracle_label,
            "actual": actual_status,
            "matched": matched,
            "findings_count": len(report.findings),
            "has_counterexample": has_ce,
            "runtime_seconds": round(elapsed, 4),
            "model_calls": fake_client.call_count,
        })

        match_str = "✓ PASS" if matched else "✗ FAIL"
        print(f"{bundle_id:<35} | {oracle_label:<16} | {actual_status:<16} | {match_str}")

    metrics = MetricsCalculator.calculate(eval_results)

    print(f"\n{'-'*75}")
    print(f"SUMMARY METRICS:")
    print(f"Total Cases:               {metrics['total_cases']}")
    print(f"Correct Decisions:         {metrics['correct_decisions']} / {metrics['total_cases']} ({metrics['accuracy']*100:.1f}%)")
    print(f"False Pass Rate:           {metrics['false_pass_rate']*100:.1f}% ({metrics['false_passes']} false passes)")
    print(f"False Block Rate:          {metrics['false_block_rate']*100:.1f}% ({metrics['false_blocks']} false blocks)")
    print(f"Counterexample Rate:       {metrics['defective_cases_with_counterexample_rate']*100:.1f}% on defective cases")
    print(f"Total Runtime:             {metrics['total_runtime_seconds']}s")
    print(f"{'='*75}\n")

    # Save machine-readable report
    output_path = REPORTS_DIR / "benchmark_report.json"
    with open(output_path, "w") as f:
        json.dump({"metrics": metrics, "results": eval_results}, f, indent=2)
    print(f"Saved benchmark report to {output_path}")

    return {"metrics": metrics, "results": eval_results}


if __name__ == "__main__":
    run_evaluation()
