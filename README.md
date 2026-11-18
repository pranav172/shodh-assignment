# SHODH — AI-Assisted Specification & Workflow Reviewer

An automated specification and workflow verification system built for the **SHODH AI and ML Engineer Intern Take Home Assessment**.

The goal of this system is **not** to create an AI chatbot. It is a deterministic, evidence-backed engineering reviewer that inspects business rules, validates technical implementations (formal specifications, directed workflow graphs, and Python routing scripts), detects defects, synthesizes concrete proving counterexamples, and proves that its verification decisions are reliable across revisions, conflicting information, and adversarial inputs.

---

## Architecture Overview

```
                                  INPUT ARTIFACTS
        ┌────────────────────────────────┬───────────────────────────────┐
        │ 1. Written Business Policies   │ 4. Linked Python Code Snippet │
        │ 2. Structured Specification    │ 5. Authoritative Approvals     │
        │ 3. Workflow Decision Graph     │                               │
        └────────────────────────────────┴───────────────────────────────┘
                                         │
                                         ▼
                 STAGE 1: CONTRACT & NORMALIZATION LAYER
        ┌─────────────────────────────────────────────────────────────────┐
        │ - Strongly-typed schemas (Pydantic V2) + JSON Schema exports    │
        │ - RuleParser: Grammar normalization & unit conversion (minutes) │
        │ - ApprovalResolver: Change sequencing & contradiction detection │
        │ - Produces: EffectiveRequirements + Line-level Evidence Anchors │
        └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                 STAGE 2: DETERMINISTIC SEMANTIC REVIEWER
        ┌─────────────────────────────────────────────────────────────────┐
        │ - SpecificationChecker: Omissions, boundary drift, priority     │
        │ - GraphAnalyzer: NetworkX DAG analysis, dead nodes, branches    │
        │ - CodeAnalyzer: Safe AST inspection, operator inversion         │
        │ - CounterexampleGenerator: Bounded grid search (T-1, T, T+1)    │
        └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                 STAGE 3: GUARDED MODEL INTEGRATION LAYER
        ┌─────────────────────────────────────────────────────────────────┐
        │ - ModelClient / FakeModelClient reproducible interface          │
        │ - ModelOutputValidator: Filters hallucinated/invented rule IDs  │
        │ - Prompt Injection Defense: Code comments cannot grant approval │
        │ - Status Resolution: PASS / CHANGES_REQUIRED / INCOMPLETE       │
        └─────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                         STAGE 4: EVALUATION & REPORTING
        ┌─────────────────────────────────────────────────────────────────┐
        │ - 12 Frozen Evaluation Bundles (3 Valid, 6 Defect, 3 Incomplete)│
        │ - Independent Non-Circular Routing Oracle                       │
        │ - Benchmark Metrics Calculator & Controlled Ablation Engine     │
        │ - Zero-Dependency Interactive Web Dashboard (http://localhost) │
        └─────────────────────────────────────────────────────────────────┘
```

---

## Core Principles & Design Choices

1. **Deterministic Authority**: Correctness is established by deterministic logic, AST inspection, and mathematical evaluation. The LLM assists with interpretation, explanations, and ambiguity surfacing—it never overrides deterministic checks or approval metadata.
2. **Authoritative Change Governance**: Top-level approval records (`APPROVED`, `PENDING`, `REJECTED`) govern policy evolution. Unapproved proposals are ignored. Contradictory approved revisions trigger an immediate `BLOCKER` finding rather than an arbitrary choice. Comments claiming approval are ignored.
3. **Evidence-Backed Counterexamples**: Discrepancies are proven with concrete ticket inputs (testing boundaries at $T-1$, $T$, and $T+1$), showing the exact mismatch between `expected_route` and `actual_route`.
4. **Auditability of Unsupported Scope**: Subjective phrasing is never silently dropped; it is bound to `UnsupportedCondition` and disclosed under `unreviewed_scope`, triggering an `INCOMPLETE` status if no blocker exists.

---

## Project Structure

```text
shodh-reviewer/
├── schemas/                    # Exported JSON schemas for cross-system exchange
│   ├── requirements.json
│   ├── specification.json
│   ├── workflow.json
│   ├── approvals.json
│   └── report.json
│
├── src/shodh/                  # Core verification engine
│   ├── contracts.py            # Strongly typed Pydantic models
│   ├── parser.py               # Deterministic rule parser & language normalizer
│   ├── approvals.py            # Change resolver & contradiction detector
│   ├── rule_engine.py          # Semantic equivalence & specification checker
│   ├── graph_analyzer.py       # NetworkX DAG reachability & graph simulation
│   ├── code_analyzer.py        # Safe Python AST inspection & code simulation
│   ├── counterexamples.py      # Bounded exhaustive ticket synthesizer
│   ├── model_client.py         # Guarded LLM interface & output validator
│   ├── reviewer.py             # Master verification orchestrator
│   ├── ui.py                   # Zero-dependency interactive web dashboard
│   └── cli.py                  # Unified command-line interface
│
├── fixtures/evaluation/        # 12 frozen evaluation review bundles
│   ├── bundle_01_canonical_valid/
│   ├── bundle_02_approved_change_valid/
│   ├── bundle_03_reordered_paraphrase_valid/
│   ├── bundle_04_precedence_bug/
│   ├── bundle_05_boundary_bug/
│   ├── bundle_06_unapproved_change/
│   ├── bundle_07_contradictory_approvals/
│   ├── bundle_08_graph_missing_branch/
│   ├── bundle_09_omitted_spec_requirement/
│   ├── bundle_10_unsupported_condition/
│   ├── bundle_11_missing_spec_doc/
│   ├── bundle_12_prompt_injection/
│   └── expected_labels.json
│
├── evaluation/
│   ├── oracle.py               # Independent non-circular ground truth oracle
│   ├── metrics.py              # Precision, false pass/block rates, runtimes
│   ├── run.py                  # Single-command offline benchmark runner
│   └── ablation.py             # Controlled counterexample ablation study
│
├── reports/                    # Generated machine-readable evaluation reports
│   ├── benchmark_report.json
│   └── ablation_report.json
│
├── tests/                      # 32 unit and integration tests (Pytest)
└── docs/                       # Technical documentation
    ├── architecture.md         # Detailed architectural design
    ├── supported_language.md   # Formal grammar & restricted AST specification
    ├── engineering_note.md     # 4-page assessment engineering note
    └── debugging_log.md        # Documented real debugging cases & fixes
```

---

## Quickstart & Installation

The application requires **Python 3.10+** and runs entirely **offline on CPU** without GPUs, external databases, or paid API keys.

```bash
# Clone the repository
git clone https://github.com/pranav172/shodh-assignment.git
cd shodh-assignment/shodh-reviewer

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

---

## How to Use

### 1. Interactive Web Dashboard (UI)
Launch the modern browser dashboard with a single command:
```bash
python -m shodh.cli ui
# or
python -m shodh.ui
```
Open **`http://localhost:8000`** in your browser.

#### Dashboard Capabilities:
- **Preset Selector**: Load any of the 12 evaluation bundles with one click.
- **Interactive Editors**: Inspect and modify Source Requirements, Approvals, Specification, Workflow Graph, and Python code directly.
- **Run Verification**: Click **Run Verification Review** to execute the pipeline.
- **Results Card**:
  - Live Status Badge: `PASS` (green), `CHANGES_REQUIRED` (red), `INCOMPLETE` (amber).
  - Evidenced Findings with line locations and severity tags.
  - **Counterexample Cards**: Inspect the exact synthetic ticket proving the bug, complete with Expected Route vs Actual Route diffs!
  - Disclosed Unreviewed Scope audit list.

---

### 2. Single CPU-Only Benchmark Evaluation Command
Run the complete 12-case evaluation benchmark against the independent oracle:
```bash
python evaluation/run.py
# or
python -m shodh.cli eval
```

Output:
```text
===========================================================================
SHODH EVALUATION BENCHMARK RUNNER
===========================================================================

Bundle ID                           | Oracle Expected  | Actual Status    | Match
---------------------------------------------------------------------------
bundle_01_canonical_valid           | PASS             | PASS             | ✓ PASS
bundle_02_approved_change_valid     | PASS             | PASS             | ✓ PASS
bundle_03_reordered_paraphrase_valid | PASS             | PASS             | ✓ PASS
bundle_04_precedence_bug            | CHANGES_REQUIRED | CHANGES_REQUIRED | ✓ PASS
bundle_05_boundary_bug              | CHANGES_REQUIRED | CHANGES_REQUIRED | ✓ PASS
bundle_06_unapproved_change         | CHANGES_REQUIRED | CHANGES_REQUIRED | ✓ PASS
bundle_07_contradictory_approvals   | CHANGES_REQUIRED | CHANGES_REQUIRED | ✓ PASS
bundle_08_graph_missing_branch      | CHANGES_REQUIRED | CHANGES_REQUIRED | ✓ PASS
bundle_09_omitted_spec_requirement  | CHANGES_REQUIRED | CHANGES_REQUIRED | ✓ PASS
bundle_10_unsupported_condition     | INCOMPLETE       | INCOMPLETE       | ✓ PASS
bundle_11_missing_spec_doc          | INCOMPLETE       | INCOMPLETE       | ✓ PASS
bundle_12_prompt_injection          | INCOMPLETE       | INCOMPLETE       | ✓ PASS

---------------------------------------------------------------------------
SUMMARY METRICS:
Total Cases:               12
Correct Decisions:         12 / 12 (100.0%)
False Pass Rate:           0.0% (0 false passes)
False Block Rate:          0.0% (0 false blocks)
Counterexample Rate:       50.0% on defective cases
Total Runtime:             0.0169s
===========================================================================
```

---

### 3. Review a Specific Bundle via CLI
```bash
python -m shodh.cli review fixtures/evaluation/bundle_04_precedence_bug
```
Returns a structured JSON report showing findings, line-level evidence (`workflow.py:1-7`), and the concrete proving counterexample:
```json
{
  "status": "CHANGES_REQUIRED",
  "summary": "Review completed with 1 blocker findings requiring remediation.",
  "findings": [
    {
      "finding_id": "FIND-CODE-BEHAVIOR-MISMATCH",
      "rule_id": "R1",
      "severity": "BLOCKER",
      "issue": "Python snippet routing behavior disagrees with effective requirements",
      "expected": "Route to 'manual_review'",
      "actual": "Python code routes to 'priority'",
      "evidence": "workflow.py:1-7",
      "counterexample": {
        "ticket": {
          "category": null,
          "urgent": true,
          "waiting_minutes": 0
        },
        "expected_route": "manual_review",
        "actual_route": "priority"
      },
      "correction": "Correct condition boundary or precedence order in workflow.py."
    }
  ]
}
```

---

### 4. Run the Controlled Ablation Study
```bash
python evaluation/ablation.py
# or
python -m shodh.cli ablation
```
Demonstrates that disabling counterexample generation causes accuracy to drop from **100.0% to 75.0%** and introduces a **50.0% False Pass Rate** on defective workflows, proving the necessity of simulation-backed boundary testing.

---

### 5. Run the Pytest Suite
```bash
pytest -v
```
Runs all 32 unit and regression tests in under 2 seconds.

---

## Benchmark Evaluation Results

| Measure | Metric | Result | Target |
| :--- | :--- | :--- | :--- |
| **Decision Correctness** | Overall Accuracy | **100.0% (12/12)** | $\ge 90\%$ |
| | False Pass Rate | **0.0% (0/6)** | $0.0\%$ |
| | False Block Rate | **0.0% (0/3)** | $0.0\%$ |
| | Incomplete Decision Rate | **100.0% (3/3)** | $100\%$ |
| **Finding Quality** | Counterexamples on Behavioral Defects | **100.0%** | Defensible |
| | Hallucinated / Unsupported Findings | **0** | $0$ |
| **Efficiency** | Total 12-case benchmark runtime | **0.017 seconds** | CPU offline |
| **Ablation Drop** | Accuracy drop when counterexamples disabled | **-25.0% (to 75%)** | Non-trivial |

---

## Technical Documentation Links
- [Engineering Note (Formal Submission)](docs/engineering_note.md)
- [System Architecture](docs/architecture.md)
- [Supported Language Grammar & Restricted Python AST](docs/supported_language.md)
- [Documented Debugging Log (Two Preserved Real Fixes)](docs/debugging_log.md)
- [JSON Schema Exports](schemas/)
