# SHODH Reviewer: Real Debugging Log

This log documents two genuine debugging cases encountered during evaluation on the frozen benchmark suite, adhering to the requirements of Stage 4.

---

## Debugging Case 1: Python AST False Blocker on Boolean Identity (`is True`)

### 1. Actual Failing Output
Running evaluation benchmark on `bundle_03_reordered_paraphrase_valid`:
```
bundle_03_reordered_paraphrase_valid | PASS | CHANGES_REQUIRED | ✗ FAIL
[BLOCKER] Python snippet routing behavior disagrees with effective requirements:
Python code routes to 'normal' (expected: 'priority')
```

### 2. Diagnosis & Root Cause
In `bundle_03`, the code author wrote:
```python
if ticket.get("urgent") is True:
    return "priority"
```
In `CodeAnalyzer._build_atomic()`, the operator dispatch map `op_map` contained entries for `ast.Eq`, `ast.NotEq`, `ast.Lt`, `ast.Gt`, etc., and only handled `ast.Is` when the compared value was `None` (`is None`).
When encountering `is True`, `op_map` lacked `ast.Is`, causing the analyzer to treat `ticket.get("urgent") is True` as an `UnsupportedCondition`. During AST simulation, unsupported conditions evaluated to `False`, incorrectly routing urgent tickets to the `"normal"` queue and generating a false blocker on a valid implementation.

### 3. Focused Fix
In `src/shodh/code_analyzer.py` inside `_build_atomic()`:
Added explicit handling for `ast.Is` and `ast.IsNot` mapping to `Operator.EQ` and `Operator.NE` when comparing boolean values (`True`/`False`):
```python
if isinstance(val_node, ast.Constant) and isinstance(val_node.value, bool):
    if isinstance(op, ast.Is):
        return AtomicCondition(field=field, operator=Operator.EQ, value=val_node.value)
    elif isinstance(op, ast.IsNot):
        return AtomicCondition(field=field, operator=Operator.NE, value=val_node.value)
```

### 4. Regression Test
Added regression test in `tests/test_code.py`:
`test_code_analyzer_handles_boolean_identity_is_true()` verifying that `ticket.get("urgent") is True` extracts to `AtomicCondition(field="urgent", operator=Operator.EQ, value=True)` and simulates correctly.

---

## Debugging Case 2: Ambiguous / Injected Requirements Converted into False Blockers Instead of INCOMPLETE

### 1. Actual Failing Output
Running evaluation benchmark on `bundle_10_unsupported_condition` and `bundle_12_prompt_injection`:
```
bundle_10_unsupported_condition | INCOMPLETE | CHANGES_REQUIRED | ✗ FAIL
bundle_12_prompt_injection      | INCOMPLETE | CHANGES_REQUIRED | ✗ FAIL
[BLOCKER] Specification condition semantic mismatch
[BLOCKER] Requirement omitted from specification: Rule 'R5'
```

### 2. Diagnosis & Root Cause
The SHODH specification defines:
- `INCOMPLETE`: *"Missing evidence, ambiguity or failure prevents full review and no blocker is established."*
- `CHANGES_REQUIRED`: *"An evidenced blocker exists."*

In `bundle_10`, rule R2 contained an unparseable subjective phrase (*"If customer sentiment appears visibly angry"*), which the parser correctly labeled as `UnsupportedCondition`.
However, `SpecificationChecker` subsequently treated the `UnsupportedCondition` as a normal requirement and attempted semantic comparison against the specification's structured rule. When the conditions didn't match, it threw a `BLOCKER` finding.
Similarly, in `bundle_12`, an injected prompt rule R5 had an `UnsupportedCondition`. The specification correctly omitted this garbage rule, but `SpecificationChecker` flagged R5 as *"Requirement omitted from specification"* with severity `BLOCKER`.
Consequently, every bundle with unreviewed or ambiguous scope was converted into a false blocker (`CHANGES_REQUIRED`), making it impossible to produce an `INCOMPLETE` review result as required by the specification.

### 3. Focused Fix
In `src/shodh/rule_engine.py` inside `SpecificationChecker.check()`:
1. If `isinstance(req.condition, UnsupportedCondition)`, skip semantic condition comparison and do not penalize the specification for omitting an unparseable or prompt-injected requirement; let it be disclosed under `unreviewed_scope`.
2. In `route_ticket_by_requirements()`: if a ticket's routing would depend on an `UnsupportedCondition`, mark the route as `None` (ambiguous), preventing the synthesis of invalid counterexamples against the implementation.

### 4. Regression Test
Added regression tests in `tests/test_rules.py` and `tests/test_reviewer.py`:
- `test_unsupported_condition_does_not_generate_false_spec_blocker()`
- Verified `bundle_10` and `bundle_12` evaluate cleanly to `INCOMPLETE`.
