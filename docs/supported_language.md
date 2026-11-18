# SHODH Supported Language & Grammar Specification

This document formally specifies the supported source condition language and the restricted Python subset handled deterministically by the SHODH Reviewer.

---

## 1. Supported Source Language Patterns

The source requirement parser parses business rules structured around the pattern:
```
[RuleID] [Prefix] <Condition> -> <Action>
```
or for catch-all fallback rules:
```
[All] remaining tickets -> <Action>
```

### 1.1 Atomic Condition Patterns

| Category | Natural Language Patterns | Parsed Operator | Target Normalized Field |
| :--- | :--- | :--- | :--- |
| **Missingness / Nullity** | `Missing <field>`, `<field> is missing`, `<field> is null`, `<field> is None` | `is_null` | `<field>` |
| **Existence** | `<field> exists`, `<field> is not null`, `<field> is present` | `is_not_null` | `<field>` |
| **Boolean Flags** | `<field> ticket`, `<field> is true`, `<field>` | `== True` | `<field>` |
| **Negated Boolean** | `not <field>`, `<field> is false` | `== False` | `<field>` |
| **Greater Than or Equal** | `waiting >= <N>`, `waiting at least <N>`, `<N> minutes or more` | `>=` | `<field>` (numeric) |
| **Greater Than** | `waiting > <N>`, `more than <N>`, `exceeds <N>`, `longer than <N>` | `>` | `<field>` (numeric) |
| **Less Than or Equal** | `waiting <= <N>`, `at most <N>`, `up to <N>` | `<=` | `<field>` (numeric) |
| **Less Than** | `waiting < <N>`, `less than <N>`, `under <N>` | `<` | `<field>` (numeric) |
| **Exact Equality** | `<field> is <value>`, `<field> == <value>`, `<field> equals <value>` | `==` | `<field>` |

### 1.2 Declared Time Units
All time durations are normalized into minutes internally:
- `minutes`, `minute`, `min`, `m` -> multiplier: `1.0`
- `hours`, `hour`, `hr`, `h` -> multiplier: `60.0`
- `seconds`, `second`, `sec`, `s` -> multiplier: `1/60.0`
- `days`, `day`, `d` -> multiplier: `1440.0`

### 1.3 Compound Logical Expressions
- **Conjunction**: Conditions joined by `AND` or `,` (e.g., `urgent ticket AND category exists`).
- **Disjunction**: Conditions joined by `OR`.
- **Precedence**: `AND` takes precedence over `OR`, or grouped with parentheses.

### 1.4 Fallback / Catch-All Rules
- Examples: `All remaining tickets -> normal queue.`, `Otherwise -> normal_queue.`
- Identifies the rule as `is_fallback = True`, with `condition = None`.

### 1.5 Unsupported or Ambiguous Content
Any phrase that cannot be deterministically mapped to the above patterns (such as subjective qualitative phrasing, e.g. *"if customer is visibly angry"*) is **never silently dropped**.
Instead, it is wrapped in an `UnsupportedCondition`:
```json
{
  "type": "unsupported",
  "raw_text": "customer is visibly angry",
  "reason": "Subjective sentiment expression not in supported deterministic grammar",
  "flag": "UNSUPPORTED"
}
```
Rules with `UnsupportedCondition` are marked in coverage as `unreviewed` with reasons, contributing to an `INCOMPLETE` report status if no blocker exists.

---

## 2. Restricted Python Subset

The code inspection engine safely analyzes Python AST without executing untrusted code.

### Supported Python Constructs
- Conditional statements: `if`, `elif`, `else`
- Ticket dictionary access: `ticket["<field>"]` or `ticket.get("<field>")`
- Comparison operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `is None`, `is not None`
- Boolean identity: `ticket["urgent"]`, `not ticket["urgent"]`
- Inverted comparisons: `30 <= ticket["waiting_minutes"]` is normalized to `ticket["waiting_minutes"] >= 30`
- Return statements: `return "<action>"` or assignment to return variables

### Unsupported Python Constructs
- Arbitrary function calls / external API calls
- Dynamic evaluation (`eval`, `exec`)
- Unbounded loops (`while True`)
- Nested function definitions
When encountered, the AST analyzer flags them as `UNSUPPORTED_CODE_CONSTRUCT` and reports them in the audit trail.
