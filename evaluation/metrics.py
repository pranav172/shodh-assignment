"""Evaluation Metrics Calculator.

Computes precision, recall, false pass rate, false block rate, finding quality,
counterexample usefulness, and execution benchmarks.
"""

from __future__ import annotations

from typing import Any, Dict, List


class MetricsCalculator:
    """Calculates standardized SHODH evaluation metrics."""

    @staticmethod
    def calculate(eval_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_cases = len(eval_results)
        valid_cases = [r for r in eval_results if r["expected"] == "PASS"]
        defective_cases = [r for r in eval_results if r["expected"] == "CHANGES_REQUIRED"]
        incomplete_cases = [r for r in eval_results if r["expected"] == "INCOMPLETE"]

        # Decision correctness
        false_passes = sum(1 for r in defective_cases if r["actual"] == "PASS")
        false_blocks = sum(1 for r in valid_cases if r["actual"] == "CHANGES_REQUIRED")
        correct_incompletes = sum(1 for r in incomplete_cases if r["actual"] == "INCOMPLETE")

        # Counts
        correct_decisions = sum(1 for r in eval_results if r["actual"] == r["expected"])

        # Finding quality & counterexamples
        counterexamples_produced = sum(1 for r in eval_results if r.get("has_counterexample"))
        defective_with_ce = sum(1 for r in defective_cases if r.get("has_counterexample"))

        # Resource use
        total_runtime = sum(r.get("runtime_seconds", 0.0) for r in eval_results)
        total_model_calls = sum(r.get("model_calls", 0) for r in eval_results)

        return {
            "total_cases": total_cases,
            "correct_decisions": correct_decisions,
            "accuracy": round(correct_decisions / total_cases if total_cases else 0.0, 4),
            "false_passes": false_passes,
            "false_pass_rate": round(false_passes / len(defective_cases) if defective_cases else 0.0, 4),
            "false_blocks": false_blocks,
            "false_block_rate": round(false_blocks / len(valid_cases) if valid_cases else 0.0, 4),
            "correct_incompletes": correct_incompletes,
            "total_incompletes_expected": len(incomplete_cases),
            "counterexamples_produced": counterexamples_produced,
            "defective_cases_with_counterexample_rate": round(defective_with_ce / len(defective_cases) if defective_cases else 0.0, 4),
            "total_runtime_seconds": round(total_runtime, 4),
            "avg_runtime_per_case_seconds": round(total_runtime / total_cases if total_cases else 0.0, 4),
            "total_model_calls": total_model_calls,
        }
