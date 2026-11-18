"""Interactive Web Dashboard for SHODH Workflow Reviewer.

Provides a modern, zero-dependency browser-based interface to inspect bundles,
visualize workflow graphs, run reviews, and examine counterexample tickets.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict

from shodh.contracts import (
    ApprovalDocument,
    PythonSnippet,
    RequirementsDocument,
    SpecificationDocument,
    WorkflowGraph,
)
from shodh.reviewer import WorkflowReviewer
from shodh.model_client import FakeModelClient

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "evaluation"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SHODH — AI-Assisted Specification & Workflow Reviewer</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.5;
      padding: 24px;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .header h1 { font-size: 24px; font-weight: 700; color: #60a5fa; }
    .header p { color: var(--text-muted); font-size: 14px; }
    .badge {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-PASS { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }
    .badge-CHANGES_REQUIRED { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }
    .badge-INCOMPLETE { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #d97706; }
    .badge-BLOCKER { background: #dc2626; color: #fff; }
    .badge-WARNING { background: #d97706; color: #fff; }

    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    label { font-size: 12px; color: var(--text-muted); display: block; margin-bottom: 4px; font-weight: 600; }
    select, textarea, button {
      width: 100%;
      background: #0d1321;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px;
      border-radius: 6px;
      font-family: var(--font-mono);
      font-size: 13px;
      margin-bottom: 16px;
    }
    textarea { height: 130px; resize: vertical; }
    button.btn-primary {
      background: var(--primary);
      border: none;
      cursor: pointer;
      font-weight: 600;
      padding: 12px;
      font-family: inherit;
      color: #fff;
      transition: background 0.15s ease;
    }
    button.btn-primary:hover { background: var(--primary-hover); }

    .result-box {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      background: #090e1a;
    }
    .finding-card {
      background: #172033;
      border-left: 4px solid var(--danger);
      padding: 14px;
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .finding-card.warning { border-left-color: var(--warning); }
    .finding-title { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
    .finding-meta { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
    .counterexample-card {
      background: #0f172a;
      border: 1px dashed #3b82f6;
      border-radius: 6px;
      padding: 10px;
      margin: 8px 0;
      font-size: 12px;
    }
    .route-diff {
      display: flex;
      gap: 16px;
      margin-top: 6px;
      font-weight: 600;
    }
    .route-diff span.exp { color: #34d399; }
    .route-diff span.act { color: #f87171; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>SHODH — Specification & Workflow Reviewer</h1>
      <p>Deterministic Multi-Artifact Verification Engine with AST Analysis & Counterexample Synthesis</p>
    </div>
    <div id="statusBadgeContainer">
      <span class="badge badge-PASS">READY</span>
    </div>
  </div>

  <div class="grid">
    <!-- Left Column: Inputs & Preset Loader -->
    <div>
      <div class="card">
        <div class="card-title">
          <span>Review Bundle Inputs</span>
          <select id="presetSelect" style="width: auto; margin-bottom: 0;" onchange="loadPreset()">
            <option value="">-- Load Evaluation Bundle Preset --</option>
            <option value="bundle_01_canonical_valid">Bundle 01: Canonical Valid Workflow</option>
            <option value="bundle_02_approved_change_valid">Bundle 02: Approved 25m SLA Valid</option>
            <option value="bundle_03_reordered_paraphrase_valid">Bundle 03: Reordered Paraphrase Valid</option>
            <option value="bundle_04_precedence_bug">Bundle 04: Precedence Defect (Urgent before Category)</option>
            <option value="bundle_05_boundary_bug">Bundle 05: Boundary Defect (> 30 instead of >= 30)</option>
            <option value="bundle_06_unapproved_change">Bundle 06: Unapproved 25m Change</option>
            <option value="bundle_07_contradictory_approvals">Bundle 07: Contradictory Approvals Conflict</option>
            <option value="bundle_08_graph_missing_branch">Bundle 08: Graph Missing Branch Edge</option>
            <option value="bundle_09_omitted_spec_requirement">Bundle 09: Omitted Specification Rule</option>
            <option value="bundle_10_unsupported_condition">Bundle 10: Unsupported Natural Language</option>
            <option value="bundle_11_missing_spec_doc">Bundle 11: Missing Specification Doc</option>
            <option value="bundle_12_prompt_injection">Bundle 12: Malicious Prompt Injection</option>
          </select>
        </div>

        <label>1. Source Requirements JSON</label>
        <textarea id="requirementsInput"></textarea>

        <label>2. Approvals JSON</label>
        <textarea id="approvalsInput"></textarea>

        <label>3. Specification JSON</label>
        <textarea id="specificationInput"></textarea>

        <label>4. Workflow Graph JSON</label>
        <textarea id="workflowInput"></textarea>

        <label>5. Python Routing Code (workflow.py)</label>
        <textarea id="codeInput" style="height: 160px;"></textarea>

        <button class="btn-primary" onclick="submitReview()">Run Verification Review</button>
      </div>
    </div>

    <!-- Right Column: Results & Findings -->
    <div>
      <div class="card">
        <div class="card-title">Verification Report & Evidence Audit</div>
        <div id="resultsContainer">
          <p style="color: var(--text-muted); font-size: 14px;">Select an evaluation bundle or edit the inputs on the left, then click <strong>Run Verification Review</strong>.</p>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function loadPreset() {
      const select = document.getElementById("presetSelect");
      const bundleId = select.value;
      if (!bundleId) return;

      const resp = await fetch("/api/preset?bundle=" + bundleId);
      const data = await resp.json();
      document.getElementById("requirementsInput").value = JSON.stringify(data.requirements, null, 2);
      document.getElementById("approvalsInput").value = JSON.stringify(data.approvals, null, 2);
      document.getElementById("specificationInput").value = data.specification ? JSON.stringify(data.specification, null, 2) : "";
      document.getElementById("workflowInput").value = data.workflow ? JSON.stringify(data.workflow, null, 2) : "";
      document.getElementById("codeInput").value = data.code || "";
    }

    async function submitReview() {
      const container = document.getElementById("resultsContainer");
      container.innerHTML = "<p style='color: #60a5fa;'>Running multi-artifact verification pipeline...</p>";

      const payload = {
        requirements: document.getElementById("requirementsInput").value,
        approvals: document.getElementById("approvalsInput").value,
        specification: document.getElementById("specificationInput").value,
        workflow: document.getElementById("workflowInput").value,
        code: document.getElementById("codeInput").value,
      };

      const resp = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const report = await resp.json();
      renderReport(report);
    }

    function renderReport(report) {
      const badgeContainer = document.getElementById("statusBadgeContainer");
      badgeContainer.innerHTML = `<span class="badge badge-${report.status}">${report.status}</span>`;

      let findingsHtml = "";
      if (report.findings && report.findings.length > 0) {
        findingsHtml = report.findings.map(f => {
          let ceHtml = "";
          if (f.counterexample) {
            ceHtml = `
              <div class="counterexample-card">
                <strong>Concrete Proving Counterexample:</strong>
                <pre style="margin: 4px 0;">${JSON.stringify(f.counterexample.ticket, null, 2)}</pre>
                <div class="route-diff">
                  <span class="exp">Expected: ${f.counterexample.expected_route}</span>
                  <span class="act">Actual: ${f.counterexample.actual_route}</span>
                </div>
              </div>
            `;
          }
          return `
            <div class="finding-card ${f.severity === 'WARNING' ? 'warning' : ''}">
              <div class="finding-title">
                <span class="badge badge-${f.severity}">${f.severity}</span>
                <span style="margin-left: 8px;">${f.issue}</span>
              </div>
              <div class="finding-meta">
                ${f.rule_id ? `Rule: <code>${f.rule_id}</code> | ` : ''}
                Evidence: <code>${f.evidence}</code>
              </div>
              <div style="font-size: 13px; margin-bottom: 6px;">
                <strong>Expected:</strong> ${f.expected}<br>
                <strong>Actual:</strong> ${f.actual}
              </div>
              ${ceHtml}
              ${f.correction ? `<div style="font-size: 12px; color: #93c5fd;"><strong>Correction:</strong> ${f.correction}</div>` : ''}
            </div>
          `;
        }).join("");
      } else {
        findingsHtml = "<div style='color: #34d399; font-weight: 600;'>✓ All verification checks passed cleanly with 0 defects detected.</div>";
      }

      let unreviewedHtml = "";
      if (report.unreviewed_scope && report.unreviewed_scope.length > 0) {
        unreviewedHtml = `
          <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid #d97706; padding: 10px; border-radius: 6px; margin-top: 16px;">
            <strong style="color: #fbbf24;">Disclosed Unreviewed Scope:</strong>
            <ul style="margin-left: 20px; font-size: 13px; color: #fde68a;">
              ${report.unreviewed_scope.map(s => `<li>${s}</li>`).join("")}
            </ul>
          </div>
        `;
      }

      document.getElementById("resultsContainer").innerHTML = `
        <div class="result-box">
          <div style="font-weight: 700; font-size: 16px; margin-bottom: 6px;">Status: <span class="badge badge-${report.status}">${report.status}</span></div>
          <p style="font-size: 14px; margin-bottom: 8px;">${report.summary}</p>
          <div style="font-size: 12px; color: var(--text-muted);">
            Rules: ${report.coverage.verified_rules} / ${report.coverage.total_rules} verified |
            Runtime: ${report.coverage.runtime_seconds}s
          </div>
        </div>
        <h3 style="font-size: 14px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted);">Evidenced Findings (${report.findings.length})</h3>
        ${findingsHtml}
        ${unreviewedHtml}
      `;
    }

    // Auto-load bundle 01 on start
    window.onload = () => {
      document.getElementById("presetSelect").value = "bundle_01_canonical_valid";
      loadPreset();
    };
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving the dashboard and review APIs."""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if parsed.path == "/api/preset":
            params = urllib.parse.parse_qs(parsed.query)
            bundle_name = params.get("bundle", ["bundle_01_canonical_valid"])[0]
            bundle_dir = FIXTURES_DIR / bundle_name
            if not bundle_dir.exists():
                self.send_error(404, "Bundle not found")
                return

            req_data = json.loads((bundle_dir / "requirements.json").read_text())
            app_data = json.loads((bundle_dir / "approvals.json").read_text()) if (bundle_dir / "approvals.json").exists() else []
            spec_data = json.loads((bundle_dir / "specification.json").read_text()) if (bundle_dir / "specification.json").exists() else None
            wf_data = json.loads((bundle_dir / "workflow.json").read_text()) if (bundle_dir / "workflow.json").exists() else None
            code_text = (bundle_dir / "code.py").read_text() if (bundle_dir / "code.py").exists() else ""

            resp = {
                "requirements": req_data,
                "approvals": app_data,
                "specification": spec_data,
                "workflow": wf_data,
                "code": code_text,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/review":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len)
            payload = json.loads(post_body.decode("utf-8"))

            req_doc = RequirementsDocument.model_validate_json(payload["requirements"])
            app_records = []
            if payload.get("approvals"):
                raw_apps = json.loads(payload["approvals"])
                app_doc = ApprovalDocument(doc_id="APP-WEB", records=raw_apps)
                app_records = app_doc.records

            spec_doc = SpecificationDocument.model_validate_json(payload["specification"]) if payload.get("specification", "").strip() else None
            wf_graph = WorkflowGraph.model_validate_json(payload["workflow"]) if payload.get("workflow", "").strip() else None

            code_snippet = None
            if payload.get("code", "").strip():
                code_text = payload["code"]
                code_snippet = PythonSnippet(
                    snippet_id="SNIP-WEB",
                    file_path="workflow.py",
                    line_start=1,
                    line_end=len(code_text.splitlines()),
                    code=code_text,
                )

            reviewer = WorkflowReviewer(model_client=FakeModelClient())
            report = reviewer.review(
                requirements_doc=req_doc,
                spec_doc=spec_doc,
                workflow_graph=wf_graph,
                code_snippet=code_snippet,
                approvals=app_records,
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(report.model_dump_json().encode("utf-8"))
            return

        self.send_error(404, "Not Found")


def run_server(port: int = 8000):
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"SHODH Dashboard running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
