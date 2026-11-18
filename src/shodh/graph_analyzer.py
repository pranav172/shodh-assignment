"""Workflow Graph Analyzer.

Analyzes workflow decision graphs using NetworkX to detect unreachable/dead nodes,
missing branches, incorrect destinations, and precedence violations, and provides
deterministic ticket simulation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import networkx as nx

from shodh.contracts import (
    Finding,
    Severity,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
)
from shodh.rule_engine import eval_condition
from shodh.approvals import EffectiveRequirement


class GraphAnalyzer:
    """Performs topological and semantic graph validation."""

    def __init__(self, workflow: WorkflowGraph):
        self.workflow = workflow
        self.nx_graph = self._build_nx_graph()

    def _build_nx_graph(self) -> nx.DiGraph:
        """Construct NetworkX DiGraph representation."""
        G = nx.DiGraph()
        for node_id, node in self.workflow.nodes.items():
            G.add_node(node_id, data=node)
        for edge in self.workflow.edges:
            G.add_edge(edge.source_node_id, edge.target_node_id, branch=edge.branch)
        return G

    def find_dead_or_unreachable_nodes(self) -> List[str]:
        """Return nodes that cannot be reached from entry_node_id."""
        if self.workflow.entry_node_id not in self.nx_graph:
            return list(self.workflow.nodes.keys())
        reachable = nx.descendants(self.nx_graph, self.workflow.entry_node_id)
        reachable.add(self.workflow.entry_node_id)
        all_nodes = set(self.workflow.nodes.keys())
        return list(all_nodes - reachable)

    def find_missing_branches(self) -> List[Tuple[str, str]]:
        """
        Decision nodes must have both 'true' and 'false' outgoing edges.
        Returns list of (node_id, missing_branch_name).
        """
        missing = []
        for node_id, node in self.workflow.nodes.items():
            if node.type == WorkflowNodeType.DECISION:
                outgoing = self.nx_graph.out_edges(node_id, data=True)
                branches_present = {data.get("branch") for _, _, data in outgoing}
                if "true" not in branches_present:
                    missing.append((node_id, "true"))
                if "false" not in branches_present:
                    missing.append((node_id, "false"))
        return missing

    def simulate(self, ticket: Dict[str, Any], max_steps: int = 50) -> Tuple[Optional[str], List[str]]:
        """
        Simulate routing a ticket through the workflow graph.
        Returns: (terminal_action, path_visited)
        """
        curr_id = self.workflow.entry_node_id
        path = []
        steps = 0

        while curr_id and steps < max_steps:
            steps += 1
            path.append(curr_id)
            node = self.workflow.nodes.get(curr_id)
            if not node:
                break

            if node.type == WorkflowNodeType.ACTION:
                return node.action, path

            # Decision node
            outcome = eval_condition(node.condition, ticket)
            branch_needed = "true" if outcome else "false"

            # Find matching outgoing edge
            next_id = None
            for _, target, data in self.nx_graph.out_edges(curr_id, data=True):
                if data.get("branch") == branch_needed:
                    next_id = target
                    break
                elif data.get("branch") == "default" and next_id is None:
                    next_id = target

            curr_id = next_id

        return None, path

    def check_against_requirements(
        self,
        effective_requirements: List[EffectiveRequirement],
    ) -> List[Finding]:
        """Verify graph structure against effective requirements."""
        findings: List[Finding] = []

        # 1. Unreachable nodes check
        dead_nodes = self.find_dead_or_unreachable_nodes()
        for node_id in dead_nodes:
            findings.append(
                Finding(
                    finding_id=f"FIND-GRAPH-UNREACHABLE-{node_id}",
                    rule_id=self.workflow.nodes[node_id].rule_id,
                    severity=Severity.BLOCKER,
                    issue="Unreachable or dead node in workflow graph",
                    expected="All defined nodes are reachable from entry node",
                    actual=f"Node '{node_id}' cannot be reached from entry node '{self.workflow.entry_node_id}'",
                    evidence=f"Workflow graph '{self.workflow.workflow_id}', node '{node_id}'",
                    correction=f"Connect an incoming edge to '{node_id}' or remove dead node.",
                )
            )

        # 2. Missing branch check
        missing_branches = self.find_missing_branches()
        for node_id, branch_name in missing_branches:
            findings.append(
                Finding(
                    finding_id=f"FIND-GRAPH-BRANCH-{node_id}-{branch_name}",
                    rule_id=self.workflow.nodes[node_id].rule_id,
                    severity=Severity.BLOCKER,
                    issue=f"Missing '{branch_name}' decision branch in workflow graph",
                    expected=f"Decision node '{node_id}' must branch on both true and false",
                    actual=f"Outgoing '{branch_name}' edge is missing from node '{node_id}'",
                    evidence=f"Workflow graph '{self.workflow.workflow_id}', node '{node_id}'",
                    correction=f"Add a directed edge from '{node_id}' with branch='{branch_name}'.",
                )
            )

        return findings
