# SHODH System Architecture

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
        │ - Schema Validation & Serialization (Pydantic V2)               │
        │ - RuleParser: Supported Grammar & Unit Normalization (minutes)  │
        │ - ApprovalResolver: Change Sequencing & Contradiction Detection │
        │ - Produces: EffectiveRequirements + Line Evidence Anchors       │
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
        │ - ModelClient / FakeModelClient interface                       │
        │ - ModelOutputValidator: Strips hallucinated/invented rule IDs   │
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

## Directory Layout
- `src/shodh/contracts.py`: Strongly typed Pydantic models for requirements, specs, graphs, code snippets, approvals, findings, and reports.
- `src/shodh/parser.py`: Rule line parser and condition grammar normalizer.
- `src/shodh/approvals.py`: Change governance, chronological sequencing, and contradiction detection.
- `src/shodh/rule_engine.py`: Semantic equivalence, mathematical boundary evaluation, and specification checker.
- `src/shodh/graph_analyzer.py`: Directed graph topology, dead node detection, and graph execution simulation.
- `src/shodh/code_analyzer.py`: Python AST condition extraction, inverted operator normalization, and safe execution simulation.
- `src/shodh/counterexamples.py`: Boundary test synthesis producing concrete ticket inputs that prove discrepancies.
- `src/shodh/model_client.py`: Guarded LLM interface, prompt injection defense, and schema-enforcing output validator.
- `src/shodh/reviewer.py`: The master orchestrator assembling the complete review report.
- `src/shodh/ui.py`: Zero-dependency interactive web dashboard.
- `src/shodh/cli.py`: Unified CLI for reviewing, benchmarking, ablating, and launching the UI.
- `evaluation/oracle.py`: Ground-truth oracle written independently from reviewer logic.
- `evaluation/metrics.py`: Computes precision, false passes, false blocks, counterexample rates, and runtimes.
- `evaluation/run.py`: Single CPU-only command executing the frozen evaluation benchmark.
- `evaluation/ablation.py`: Controlled experiment verifying the necessity of counterexample generation.
