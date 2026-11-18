# SHODH Reviewer — Engineering Note

## 1. Executive Summary & Supported Scope
The SHODH Reviewer is an automated specification and workflow verification engine. It evaluates whether decision implementations (formal specifications, directed workflow graphs, and Python routing scripts) faithfully implement business requirements and authorized revisions.

### Supported Language Scope
- **Numeric Boundaries**: Full support for comparison operators (`==`, `!=`, `<`, `<=`, `>`, `>=`) with explicit handling of inclusivity/exclusivity and normalization of declared time units (`minutes`, `hours`, `seconds`, `days` normalized to minutes).
- **Nullity & Missingness**: Explicit checks for missing values (`is None`, `is_null`, `is_not_null`, `is present`).
- **Boolean Flags & Combinators**: Support for truth values and logical combinators (`AND`, `OR`, `NOT`).
- **Catch-All Rules**: Explicit semantics for fallback/remaining routing.
- **Restricted Python AST Subset**: Safe inspection of `if`/`elif`/`else` control flow, dict subscript lookups (`ticket["key"]` and `ticket.get("key")`), and inverted comparisons (e.g. `30 <= ticket["waiting_minutes"]`).
- **Auditability of Unsupported Scope**: Qualitative or subjective phrasing (e.g., *"if customer tone is agitated"*) is never silently dropped; it is bound to `UnsupportedCondition` and disclosed as unreviewed scope, triggering `INCOMPLETE` status if no blocker exists.

---

## 2. Core Architecture & Design Choices

```
[ Written Requirements ] ────► [ RuleParser ] ──┐
                                                ▼
[ Approval Records ] ────────► [ ApprovalResolver ] ──► [ Effective Requirements ]
                                                              │
                     ┌────────────────────────────────────────┼─────────────────────────┐
                     ▼                                        ▼                         ▼
             [ SpecChecker ]                           [ GraphAnalyzer ]         [ CodeAnalyzer ]
            (Coverage & Drift)                        (Reachability & DAG)      (Safe AST Inspection)
                     │                                        │                         │
                     └────────────────────────────────────────┼─────────────────────────┘
                                                              ▼
                                                [ CounterexampleGenerator ]
                                                (Bounded Exhaustive Grid)
                                                              ▼
                                                    [ Guarded ModelClient ]
                                                              ▼
                                                    [ Final ReviewReport ]
```

### Key Design Principles:
1. **Deterministic Authority**: Correctness is established deterministically via AST inspection, graph traversal, and mathematical evaluation. The LLM assists with natural-language interpretation, explanation, and ambiguity surfacing—it never overrides deterministic checks or approval metadata.
2. **Authoritative Change Governance**: Top-level approval records (`APPROVED`, `PENDING`, `REJECTED`) govern policy evolution. Unapproved changes are ignored; contradictory approved records targeting the same rule scope trigger an immediate `BLOCKER` finding rather than an arbitrary choice. Unanchored prose claims (e.g. *"approved by lead"*) cannot override top-level metadata.
3. **Evidence-Backed Counterexamples**: Discrepancies are proven with concrete ticket inputs (e.g., evaluating boundary conditions at $T-1$, $T$, and $T+1$), showing the exact mismatch between `expected_route` and `actual_route`.

---

## 3. Evaluation & Benchmark Results

The system was evaluated against 12 frozen review bundles (including a 4-bundle held-out test set):

| Bundle ID | Case Category | Condition Tested | Expected Status | Reviewer Status | Result |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `bundle_01` | Valid | Canonical 4-rule policy | `PASS` | `PASS` | Match |
| `bundle_02` | Valid | Approved SLA reduction (30m -> 25m) | `PASS` | `PASS` | Match |
| `bundle_03` | Valid (Unusual) | Paraphrased syntax (`30 <= waiting`) | `PASS` | `PASS` | Match |
| `bundle_04` | Defective | Precedence bug (urgent before missing category)| `CHANGES_REQUIRED` | `CHANGES_REQUIRED` | Match (Counterexample) |
| `bundle_05` | Defective | Boundary bug (`> 30` instead of `>= 30`) | `CHANGES_REQUIRED` | `CHANGES_REQUIRED` | Match (Counterexample) |
| `bundle_06` | Defective | Unapproved change implemented (25m) | `CHANGES_REQUIRED` | `CHANGES_REQUIRED` | Match |
| `bundle_07` | Defective | Contradictory approvals conflict | `CHANGES_REQUIRED` | `CHANGES_REQUIRED` | Match |
| `bundle_08` | Defective | Graph missing false branch | `CHANGES_REQUIRED` | `CHANGES_REQUIRED` | Match |
| `bundle_09` | Defective (Held-out) | Specification omits R1 | `CHANGES_REQUIRED` | `CHANGES_REQUIRED` | Match |
| `bundle_10` | Incomplete (Held-out)| Subjective natural language condition | `INCOMPLETE` | `INCOMPLETE` | Match |
| `bundle_11` | Incomplete (Held-out)| Missing specification document | `INCOMPLETE` | `INCOMPLETE` | Match |
| `bundle_12` | Incomplete (Held-out)| Malicious prompt injection attempt | `INCOMPLETE` | `INCOMPLETE` | Match |

### Benchmark Metrics:
- **Decision Accuracy**: 12 / 12 (100.0%)
- **False Pass Rate**: 0.0% (0 false passes across all defective cases)
- **False Block Rate**: 0.0% (0 false blocks across all valid cases)
- **Counterexample Synthesis**: 100% of behavioral routing discrepancies synthesized with concrete tickets
- **Total Execution Runtime**: < 0.02s for all 12 cases on CPU.

---

## 4. Controlled Ablation Study

To evaluate the contribution of behavioral counterexample generation, an ablation was conducted where simulation-backed counterexamples were disabled:
- **Full Reviewer**: 100.0% accuracy, 0.0% false pass rate.
- **Ablated Reviewer (No Counterexamples)**: Accuracy dropped to **75.0%**, with a **50.0% False Pass Rate** on defective implementations (silently passing `bundle_04_precedence_bug`, `bundle_05_boundary_bug`, and `bundle_06_unapproved_change`).
- **Conclusion**: Static schema checking alone is inadequate; dynamic AST simulation and boundary exploration are essential for finding real-world implementation bugs.

---

## 5. Material AI Assistance Disclosure & Verification
- AI tooling was utilized for schema structuring, rapid test scaffolding, and initial documentation drafting.
- All code, AST traversal logic, graph algorithms, and evaluation assertions were independently verified through automated test suites (32 unit/integration tests) and an independent ground-truth oracle.
