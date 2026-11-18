"""Contract schemas and domain models for SHODH reviewer.

Defines strongly typed Pydantic models for requirements, specifications,
workflow graphs, code snippets, approval records, and review reports.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


class Operator(str, Enum):
    """Supported comparison operators."""
    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IN = "in"
    NOT_IN = "not_in"


class TimeUnit(str, Enum):
    """Supported time units, normalized to minutes."""
    SECONDS = "seconds"
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"

    @classmethod
    def to_minutes(cls, value: float, unit: Union[TimeUnit, str]) -> float:
        unit_str = unit.value if isinstance(unit, TimeUnit) else str(unit).lower()
        if unit_str in ("seconds", "s", "sec"):
            return value / 60.0
        elif unit_str in ("minutes", "m", "min"):
            return float(value)
        elif unit_str in ("hours", "h", "hr"):
            return value * 60.0
        elif unit_str in ("days", "d"):
            return value * 1440.0
        raise ValueError(f"Unsupported time unit: {unit}")


class AtomicCondition(BaseModel):
    """An individual comparison condition against a single ticket field."""
    type: Literal["atomic"] = "atomic"
    field: str = Field(..., description="Ticket attribute name (e.g., 'waiting_minutes', 'category', 'urgent')")
    operator: Operator = Field(..., description="Comparison operator")
    value: Any = Field(default=None, description="Target value for comparison (null for is_null/is_not_null)")
    unit: Optional[str] = Field(default=None, description="Optional unit (e.g., 'minutes', 'hours')")

    def normalized_numeric_value(self) -> Optional[float]:
        """Convert time-based numeric values into minutes for uniform evaluation."""
        if self.unit and self.value is not None:
            try:
                return TimeUnit.to_minutes(float(self.value), self.unit)
            except (ValueError, TypeError):
                pass
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            return float(self.value)
        return None


class CompoundCondition(BaseModel):
    """Logical combination of conditions (AND / OR / NOT)."""
    type: Literal["compound"] = "compound"
    combinator: Literal["and", "or", "not"] = Field(..., description="Logical combinator")
    conditions: List[Condition] = Field(..., description="Child conditions to combine")

    @model_validator(mode="after")
    def validate_conditions(self) -> CompoundCondition:
        if self.combinator == "not" and len(self.conditions) != 1:
            raise ValueError("NOT combinator must have exactly one child condition")
        if self.combinator in ("and", "or") and len(self.conditions) < 1:
            raise ValueError(f"{self.combinator.upper()} combinator must have at least one child condition")
        return self


class UnsupportedCondition(BaseModel):
    """Preserves raw condition text that cannot be safely parsed into the supported domain."""
    type: Literal["unsupported"] = "unsupported"
    raw_text: str = Field(..., description="Original unparsed text")
    reason: str = Field(..., description="Why the condition is unsupported or ambiguous")
    flag: Literal["UNSUPPORTED", "AMBIGUOUS"] = Field(default="UNSUPPORTED")


# Discriminated union of conditions
Condition = Annotated[
    Union[AtomicCondition, CompoundCondition, UnsupportedCondition],
    Field(discriminator="type")
]

# Update forward refs for recursive CompoundCondition
CompoundCondition.model_rebuild()


# ============================================================================
# 1. Source Requirements Artifact
# ============================================================================

class SourceRequirement(BaseModel):
    """A single business policy requirement, anchored to source text."""
    rule_id: str = Field(..., description="Unique rule identifier (e.g. 'R1', 'R2')")
    title: Optional[str] = Field(default=None, description="Short human-readable title")
    source: str = Field(..., description="Source file or document reference (e.g. 'support_policy.md')")
    line_start: Optional[int] = Field(default=None, description="Starting line in source document")
    line_end: Optional[int] = Field(default=None, description="Ending line in source document")
    version: int = Field(default=1, description="Version of the source requirement")
    priority: int = Field(..., description="Precedence rank: lower integer evaluated first (1, 2, 3...)")
    condition: Optional[Condition] = Field(default=None, description="Trigger condition (None for default/fallback)")
    action: str = Field(..., description="Resulting queue or action (e.g. 'manual_review', 'priority')")
    raw_text: Optional[str] = Field(default=None, description="Original prose text")
    is_fallback: bool = Field(default=False, description="True if this is an 'otherwise / remaining tickets' catch-all")

    @property
    def evidence_location(self) -> str:
        """Formatted evidence string."""
        if self.line_start is not None and self.line_end is not None:
            return f"{self.source}:{self.line_start}-{self.line_end}"
        elif self.line_start is not None:
            return f"{self.source}:{self.line_start}"
        return self.source


class RequirementsDocument(BaseModel):
    """A collection of business requirements representing an entire policy version."""
    doc_id: str = Field(..., description="Identifier for requirements document")
    version: int = Field(default=1, description="Version of the document")
    title: Optional[str] = Field(default=None)
    rules: List[SourceRequirement] = Field(default_factory=list)


# ============================================================================
# 2. Structured Specification Artifact
# ============================================================================

class SpecificationRule(BaseModel):
    """A developer or architect formalization of a business rule."""
    spec_rule_id: str = Field(..., description="Identifier within the specification")
    target_rule_id: Optional[str] = Field(default=None, description="Target business rule ID (e.g., 'R1')")
    priority: int = Field(..., description="Evaluation precedence rank")
    condition: Optional[Condition] = Field(default=None, description="Formal condition (None for default fallback)")
    action: str = Field(..., description="Target routing action")
    evidence: Optional[str] = Field(default=None, description="Source line or ticket reference")
    is_fallback: bool = Field(default=False)


class SpecificationDocument(BaseModel):
    """The structured specification artifact."""
    spec_id: str = Field(..., description="Identifier for this specification")
    version: int = Field(default=1)
    requirements_doc_id: Optional[str] = Field(default=None, description="Referenced requirements document ID")
    rules: List[SpecificationRule] = Field(default_factory=list)


# ============================================================================
# 3. Workflow Graph Artifact
# ============================================================================

class WorkflowNodeType(str, Enum):
    DECISION = "decision"
    ACTION = "action"


class WorkflowNode(BaseModel):
    """A node in the decision routing graph."""
    node_id: str = Field(..., description="Unique node identifier")
    type: WorkflowNodeType = Field(..., description="'decision' or 'action'")
    rule_id: Optional[str] = Field(default=None, description="Referenced rule ID if applicable")
    condition: Optional[Condition] = Field(default=None, description="Condition to evaluate for decision nodes")
    action: Optional[str] = Field(default=None, description="Terminal action name for action nodes")
    evidence: Optional[str] = Field(default=None, description="Evidence location in workflow definition")


class WorkflowEdge(BaseModel):
    """A directed edge in the workflow graph."""
    source_node_id: str = Field(..., description="Originating node ID")
    target_node_id: str = Field(..., description="Destination node ID")
    branch: Literal["true", "false", "default"] = Field(..., description="Branch label taken on condition outcome")


class WorkflowGraph(BaseModel):
    """A full workflow routing graph."""
    workflow_id: str = Field(..., description="Unique workflow identifier")
    version: int = Field(default=1)
    entry_node_id: str = Field(..., description="Entry decision node ID")
    nodes: Dict[str, WorkflowNode] = Field(..., description="Dictionary of node_id -> WorkflowNode")
    edges: List[WorkflowEdge] = Field(default_factory=list, description="List of directed branch edges")


# ============================================================================
# 4. Linked Python Code Snippet Artifact
# ============================================================================

class PythonSnippet(BaseModel):
    """Linked Python code snippet implementing routing logic."""
    snippet_id: str = Field(..., description="Snippet identifier")
    file_path: str = Field(..., description="File path (e.g. 'workflow.py')")
    line_start: int = Field(..., description="First line of snippet")
    line_end: int = Field(..., description="Last line of snippet")
    code: str = Field(..., description="Exact Python source code")
    target_rule_ids: List[str] = Field(default_factory=list, description="Associated rule IDs claimed in comments/metadata")


# ============================================================================
# 5. Approval Records Artifact
# ============================================================================

class ApprovalStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class ApprovalRecord(BaseModel):
    """A formal change control approval record."""
    change_id: str = Field(..., description="Unique change proposal ID (e.g. 'CHG-101')")
    target_rule_id: str = Field(..., description="Rule ID targeted for amendment (e.g. 'R3')")
    target_version: int = Field(default=1, description="Base rule version being modified")
    status: ApprovalStatus = Field(..., description="'APPROVED', 'REJECTED', or 'PENDING'")
    author: str = Field(..., description="Individual or role proposing/approving change")
    timestamp: str = Field(..., description="ISO 8601 timestamp or sequence ordering key")
    patch: Dict[str, Any] = Field(..., description="Dictionary of modified fields (e.g. {'condition': {'value': 25}})")
    notes: Optional[str] = Field(default=None, description="Context, justification, or review notes")


class ApprovalDocument(BaseModel):
    """Collection of approval records."""
    doc_id: str = Field(..., description="Approval log document identifier")
    records: List[ApprovalRecord] = Field(default_factory=list)


# ============================================================================
# 6. Review Findings and Report Artifacts
# ============================================================================

class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class Finding(BaseModel):
    """An evidenced defect, inconsistency, or violation discovered during review."""
    finding_id: str = Field(..., description="Unique finding identifier (e.g. 'FIND-001')")
    rule_id: Optional[str] = Field(default=None, description="Associated requirement rule ID")
    severity: Severity = Field(..., description="Severity level")
    issue: str = Field(..., description="Clear summary of the problem (e.g., 'Incorrect threshold boundary')")
    expected: str = Field(..., description="Expected behavior according to effective requirements")
    actual: str = Field(..., description="Actual behavior found in spec, graph, or code")
    evidence: str = Field(..., description="Exact location: file, line range, or node ID (e.g. 'workflow.py:3')")
    counterexample: Optional[Dict[str, Any]] = Field(default=None, description="Concrete ticket input proving the discrepancy")
    correction: Optional[str] = Field(default=None, description="Specific remediation advice")


class ReviewStatus(str, Enum):
    PASS = "PASS"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    INCOMPLETE = "INCOMPLETE"


class ReviewReport(BaseModel):
    """Final comprehensive review report."""
    status: ReviewStatus = Field(..., description="'PASS', 'CHANGES_REQUIRED', or 'INCOMPLETE'")
    summary: str = Field(..., description="Executive summary of the review results")
    findings: List[Finding] = Field(default_factory=list, description="List of findings found")
    coverage: Dict[str, Any] = Field(
        default_factory=dict,
        description="Coverage statistics: total_rules, verified_rules, unreviewed_rules"
    )
    check_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed record of all individual checks run across artifacts"
    )
    unreviewed_scope: List[str] = Field(
        default_factory=list,
        description="Explicit disclosure of any requirements, nodes, or code left unreviewed"
    )
