"""Master Reviewer Orchestrator for SHODH.

Integrates input contract normalization, approval resolution, specification checks,
graph verification, Python AST analysis, counterexample generation, and guarded
model interpretation into an authoritative ReviewReport.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from shodh.contracts import (
    ApprovalRecord,
    Finding,
    PythonSnippet,
    RequirementsDocument,
    ReviewReport,
    ReviewStatus,
    Severity,
    SpecificationDocument,
    UnsupportedCondition,
    WorkflowGraph,
)
from shodh.approvals import ApprovalResolver
from shodh.rule_engine import SpecificationChecker
from shodh.graph_analyzer import GraphAnalyzer
from shodh.code_analyzer import CodeAnalyzer
from shodh.counterexamples import CounterexampleGenerator
from shodh.model_client import FakeModelClient, ModelClient, ModelOutputValidator


class WorkflowReviewer:
    """End-to-end specification and workflow reviewer."""

    def __init__(self, model_client: Optional[ModelClient] = None):
        self.model_client = model_client or FakeModelClient()

    def review(
        self,
        requirements_doc: RequirementsDocument,
        spec_doc: Optional[SpecificationDocument] = None,
        workflow_graph: Optional[WorkflowGraph] = None,
        code_snippet: Optional[PythonSnippet] = None,
        approvals: Optional[List[ApprovalRecord]] = None,
    ) -> ReviewReport:
        """Execute full multi-artifact verification pipeline."""
        start_time = time.time()
        findings: List[Finding] = []
        check_results: List[Dict[str, Any]] = []
        unreviewed_scope: List[str] = []

        approvals = approvals or []

        # ---------------------------------------------------------------------
        # 1. Approval & Revision Resolution
        # ---------------------------------------------------------------------
        resolver = ApprovalResolver()
        effective_requirements, approval_findings = resolver.resolve(requirements_doc, approvals)
        findings.extend(approval_findings)
        check_results.append({
            "stage": "approvals",
            "status": "FAILED" if any(f.severity == Severity.BLOCKER for f in approval_findings) else "PASSED",
            "findings_count": len(approval_findings),
        })

        # ---------------------------------------------------------------------
        # 2. Unsupported Condition Audit
        # ---------------------------------------------------------------------
        valid_rule_ids = {r.rule_id for r in effective_requirements}
        verified_rule_ids = set()

        for req in effective_requirements:
            if isinstance(req.condition, UnsupportedCondition):
                unreviewed_scope.append(f"Rule {req.rule_id}: {req.condition.reason}")
            else:
                verified_rule_ids.add(req.rule_id)

        ce_gen = CounterexampleGenerator(effective_requirements)

        # ---------------------------------------------------------------------
        # 3. Specification Verification
        # ---------------------------------------------------------------------
        if spec_doc:
            spec_checker = SpecificationChecker()
            spec_findings = spec_checker.check(effective_requirements, spec_doc)
            findings.extend(spec_findings)
            check_results.append({
                "stage": "specification",
                "status": "FAILED" if any(f.severity == Severity.BLOCKER for f in spec_findings) else "PASSED",
                "findings_count": len(spec_findings),
            })
        else:
            unreviewed_scope.append("Specification document was not provided.")

        # ---------------------------------------------------------------------
        # 4. Workflow Graph Verification & Simulation
        # ---------------------------------------------------------------------
        if workflow_graph:
            graph_analyzer = GraphAnalyzer(workflow_graph)
            graph_findings = graph_analyzer.check_against_requirements(effective_requirements)

            # Behavioral counterexample search via graph simulation
            ce = ce_gen.find_counterexample(lambda t: graph_analyzer.simulate(t)[0])
            if ce:
                graph_findings.append(
                    Finding(
                        finding_id=f"FIND-GRAPH-SIM-MISMATCH",
                        rule_id=None,
                        severity=Severity.BLOCKER,
                        issue="Workflow graph routing behavior disagrees with effective requirements",
                        expected=f"Routing to '{ce['expected_route']}' for ticket",
                        actual=f"Workflow graph routes to '{ce['actual_route']}'",
                        evidence=f"Workflow graph '{workflow_graph.workflow_id}'",
                        counterexample=ce,
                        correction="Inspect graph decision branches and path routing.",
                    )
                )

            findings.extend(graph_findings)
            check_results.append({
                "stage": "workflow_graph",
                "status": "FAILED" if any(f.severity == Severity.BLOCKER for f in graph_findings) else "PASSED",
                "findings_count": len(graph_findings),
            })
        else:
            unreviewed_scope.append("Workflow graph was not provided.")

        # ---------------------------------------------------------------------
        # 5. Python AST Code Verification & Simulation
        # ---------------------------------------------------------------------
        if code_snippet:
            code_analyzer = CodeAnalyzer(code_snippet)

            # Report any unsupported Python AST constructs
            for unsup in code_analyzer.unsupported_constructs:
                unreviewed_scope.append(f"Code construct: {unsup}")

            # Behavioral counterexample search via code simulation
            ce = ce_gen.find_counterexample(lambda t: code_analyzer.simulate(t)[0])
            if ce:
                # Find which rule or line caused this
                target_rule_id = None
                for req in effective_requirements:
                    if req.action == ce["expected_route"]:
                        target_rule_id = req.rule_id
                        break

                findings.append(
                    Finding(
                        finding_id=f"FIND-CODE-BEHAVIOR-MISMATCH",
                        rule_id=target_rule_id,
                        severity=Severity.BLOCKER,
                        issue="Python snippet routing behavior disagrees with effective requirements",
                        expected=f"Route to '{ce['expected_route']}'",
                        actual=f"Python code routes to '{ce['actual_route']}'",
                        evidence=f"{code_snippet.file_path}:{code_snippet.line_start}-{code_snippet.line_end}",
                        counterexample=ce,
                        correction=f"Correct condition boundary or precedence order in {code_snippet.file_path}.",
                    )
                )

            check_results.append({
                "stage": "python_code",
                "status": "FAILED" if ce else "PASSED",
                "findings_count": 1 if ce else 0,
            })
        else:
            unreviewed_scope.append("Python code snippet was not provided.")

        # ---------------------------------------------------------------------
        # 6. Guarded Model Interpretation
        # ---------------------------------------------------------------------
        model_summary = ""
        if self.model_client:
            payload = {
                "requirements": [r.model_dump() for r in effective_requirements],
                "deterministic_findings": [f.model_dump() for f in findings],
            }
            try:
                raw_response = self.model_client.review(payload)
                validator = ModelOutputValidator(valid_rule_ids)
                _, model_findings = validator.validate_and_filter(raw_response)
                findings.extend(model_findings)
                model_summary = raw_response.get("summary", "")
            except Exception as e:
                findings.append(
                    Finding(
                        finding_id="FIND-MODEL-EXEC-ERR",
                        rule_id=None,
                        severity=Severity.WARNING,
                        issue=f"Model review failure: {type(e).__name__}",
                        expected="Model response available",
                        actual=str(e),
                        evidence="Model client invocation",
                        correction="Inspect model configuration or credentials.",
                    )
                )

        # ---------------------------------------------------------------------
        # 7. Final Status Determination
        # ---------------------------------------------------------------------
        has_blocker = any(f.severity == Severity.BLOCKER for f in findings)

        if has_blocker:
            status = ReviewStatus.CHANGES_REQUIRED
            summary = f"Review completed with {len([f for f in findings if f.severity == Severity.BLOCKER])} blocker findings requiring remediation."
        elif unreviewed_scope:
            status = ReviewStatus.INCOMPLETE
            summary = f"Review incomplete: {len(unreviewed_scope)} scope item(s) could not be deterministically verified."
        else:
            status = ReviewStatus.PASS
            summary = "All effective requirements successfully verified across specification, graph, and code with zero blockers."

        if model_summary:
            summary = f"{summary} [AI Insights: {model_summary}]"

        coverage = {
            "total_rules": len(effective_requirements),
            "verified_rules": len(verified_rule_ids),
            "unreviewed_rules": len(unreviewed_scope),
            "runtime_seconds": round(time.time() - start_time, 4),
        }

        return ReviewReport(
            status=status,
            summary=summary,
            findings=findings,
            coverage=coverage,
            check_results=check_results,
            unreviewed_scope=unreviewed_scope,
        )
