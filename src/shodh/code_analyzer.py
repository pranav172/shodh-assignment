"""Python AST Code Analyzer.

Inspects linked Python snippets safely using Python's `ast` module without executing
arbitrary untrusted code. Extracts conditions, actions, and evaluation order,
normalizes inverted operators, and simulates ticket routing.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple
from shodh.contracts import (
    AtomicCondition,
    CompoundCondition,
    Condition,
    Finding,
    Operator,
    PythonSnippet,
    Severity,
    UnsupportedCondition,
)
from shodh.rule_engine import eval_condition
from shodh.approvals import EffectiveRequirement


class ExtractedCodeRule:
    """Represents an extracted if/elif/else branch from Python AST."""

    def __init__(
        self,
        condition: Optional[Condition],
        action: str,
        line_no: int,
        is_fallback: bool = False,
    ):
        self.condition = condition
        self.action = action
        self.line_no = line_no
        self.is_fallback = is_fallback

    def __repr__(self) -> str:
        return f"<ExtractedCodeRule line={self.line_no} action='{self.action}' cond={self.condition}>"


class CodeAnalyzer:
    """Extracts and verifies routing logic from Python AST."""

    def __init__(self, snippet: PythonSnippet):
        self.snippet = snippet
        self.extracted_rules: List[ExtractedCodeRule] = []
        self.unsupported_constructs: List[str] = []
        self._parse()

    def _parse(self) -> None:
        """Parse snippet code into AST and extract rules."""
        try:
            tree = ast.parse(self.snippet.code)
        except SyntaxError as e:
            self.unsupported_constructs.append(f"Syntax error in Python snippet: {e}")
            return

        # Walk through top-level statements
        for stmt in tree.body:
            self._process_statement(stmt)

    def _process_statement(self, stmt: ast.stmt) -> None:
        """Process if-statements and return statements."""
        if isinstance(stmt, ast.If):
            cond = self._parse_test(stmt.test, stmt.lineno)
            action = self._extract_action_from_body(stmt.body)
            if action:
                self.extracted_rules.append(
                    ExtractedCodeRule(condition=cond, action=action, line_no=stmt.lineno)
                )

            # Process elif / else in orelse
            curr_orelse = stmt.orelse
            while curr_orelse:
                if len(curr_orelse) == 1 and isinstance(curr_orelse[0], ast.If):
                    elif_stmt = curr_orelse[0]
                    cond = self._parse_test(elif_stmt.test, elif_stmt.lineno)
                    action = self._extract_action_from_body(elif_stmt.body)
                    if action:
                        self.extracted_rules.append(
                            ExtractedCodeRule(condition=cond, action=action, line_no=elif_stmt.lineno)
                        )
                    curr_orelse = elif_stmt.orelse
                else:
                    # Trailing else
                    action = self._extract_action_from_body(curr_orelse)
                    if action:
                        line_no = curr_orelse[0].lineno if curr_orelse else stmt.lineno
                        self.extracted_rules.append(
                            ExtractedCodeRule(condition=None, action=action, line_no=line_no, is_fallback=True)
                        )
                    break

        elif isinstance(stmt, ast.Return):
            action = self._extract_return_value(stmt)
            if action:
                self.extracted_rules.append(
                    ExtractedCodeRule(condition=None, action=action, line_no=stmt.lineno, is_fallback=True)
                )

    def _extract_action_from_body(self, body: List[ast.stmt]) -> Optional[str]:
        """Look for a Return statement inside a block."""
        for stmt in body:
            if isinstance(stmt, ast.Return):
                return self._extract_return_value(stmt)
        return None

    def _extract_return_value(self, ret: ast.Return) -> Optional[str]:
        """Extract string literal from return value."""
        if isinstance(ret.value, ast.Constant) and isinstance(ret.value.value, str):
            return ret.value.value.lower().replace(" ", "_")
        return None

    def _parse_test(self, test: ast.expr, line_no: int) -> Condition:
        """Parse condition expression from AST test node."""
        # 1. Unary NOT: not ticket["urgent"]
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            inner = self._parse_test(test.operand, line_no)
            if isinstance(inner, AtomicCondition) and inner.value is True:
                return AtomicCondition(field=inner.field, operator=Operator.EQ, value=False)
            return CompoundCondition(combinator="not", conditions=[inner])

        # 2. Boolean AND / OR: test1 and test2
        if isinstance(test, ast.BoolOp):
            combinator = "and" if isinstance(test.op, ast.And) else "or"
            sub_conds = [self._parse_test(val, line_no) for val in test.values]
            return CompoundCondition(combinator=combinator, conditions=sub_conds)

        # 3. Direct boolean subscript: ticket["urgent"]
        if isinstance(test, ast.Subscript):
            field = self._extract_subscript_field(test)
            if field:
                return AtomicCondition(field=field, operator=Operator.EQ, value=True)

        # 4. Comparisons: ==, !=, <, <=, >, >=, is, is not
        if isinstance(test, ast.Compare):
            left = test.left
            if len(test.ops) == 1 and len(test.comparators) == 1:
                op = test.ops[0]
                right = test.comparators[0]
                return self._parse_comparison(left, op, right, line_no)

        return UnsupportedCondition(
            raw_text=ast.unparse(test) if hasattr(ast, "unparse") else f"line {line_no}",
            reason="Python AST expression not in supported deterministic subset",
            flag="UNSUPPORTED",
        )

    def _parse_comparison(
        self,
        left: ast.expr,
        op: ast.cmpop,
        right: ast.expr,
        line_no: int,
    ) -> Condition:
        """Parse binary comparison with support for inverted ordering."""
        # Check if left is ticket['field']
        left_field = self._extract_subscript_field(left)
        right_field = self._extract_subscript_field(right)

        # Normal form: ticket['field'] <op> <value>
        if left_field and not right_field:
            return self._build_atomic(left_field, op, right, inverted=False, line_no=line_no)

        # Inverted form: <value> <op> ticket['field'] (e.g. 30 <= ticket['waiting_minutes'])
        if right_field and not left_field:
            return self._build_atomic(right_field, op, left, inverted=True, line_no=line_no)

        return UnsupportedCondition(
            raw_text=f"line {line_no}",
            reason="Unsupported comparison structure in Python snippet",
            flag="UNSUPPORTED",
        )

    def _extract_subscript_field(self, node: ast.expr) -> Optional[str]:
        """Extract field string from ticket['category'] or ticket.get('category')."""
        if isinstance(node, ast.Subscript):
            # ticket["category"]
            slice_node = node.slice
            if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
                return slice_node.value
        elif isinstance(node, ast.Call):
            # ticket.get("category")
            if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    return node.args[0].value
        return None

    def _build_atomic(
        self,
        field: str,
        op: ast.cmpop,
        val_node: ast.expr,
        inverted: bool,
        line_no: int,
    ) -> Condition:
        """Convert AST comparison operator and value into AtomicCondition."""
        # Null check
        if isinstance(val_node, ast.Constant) and val_node.value is None:
            if isinstance(op, (ast.Is, ast.Eq)):
                return AtomicCondition(field=field, operator=Operator.IS_NULL)
            elif isinstance(op, (ast.IsNot, ast.NotEq)):
                return AtomicCondition(field=field, operator=Operator.IS_NOT_NULL)

        # Boolean identity check (e.g. ticket.get("urgent") is True)
        if isinstance(val_node, ast.Constant) and isinstance(val_node.value, bool):
            if isinstance(op, (ast.Is, ast.Eq)):
                return AtomicCondition(field=field, operator=Operator.EQ, value=val_node.value)
            elif isinstance(op, (ast.IsNot, ast.NotEq)):
                return AtomicCondition(field=field, operator=Operator.NE, value=val_node.value)

        # Constant value
        val: Any = None
        if isinstance(val_node, ast.Constant):
            val = val_node.value

        op_map = {
            ast.Eq: Operator.EQ,
            ast.NotEq: Operator.NE,
            ast.Lt: Operator.GT if inverted else Operator.LT,
            ast.LtE: Operator.GE if inverted else Operator.LE,
            ast.Gt: Operator.LT if inverted else Operator.GT,
            ast.GtE: Operator.LE if inverted else Operator.GE,
        }

        matched_op = op_map.get(type(op))
        if matched_op:
            return AtomicCondition(
                field=field,
                operator=matched_op,
                value=val,
                unit="minutes" if "waiting" in field else None,
            )

        return UnsupportedCondition(
            raw_text=f"line {line_no}",
            reason=f"Unsupported comparison operator {type(op).__name__}",
            flag="UNSUPPORTED",
        )

    def simulate(self, ticket: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
        """
        Simulate routing through the extracted code rules safely without exec/eval.
        Returns: (returned_action, executed_line_no)
        """
        for rule in self.extracted_rules:
            if rule.is_fallback or eval_condition(rule.condition, ticket):
                return rule.action, rule.line_no
        return None, None
