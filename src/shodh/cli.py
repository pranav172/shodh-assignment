"""SHODH Command Line Interface (CLI).

Commands:
- review: Run verification review on a specific bundle directory
- eval: Execute the 12-bundle offline evaluation benchmark
- ablation: Run the counterexample ablation study
- ui: Launch the interactive browser dashboard
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shodh.reviewer import WorkflowReviewer
from shodh.model_client import FakeModelClient
from evaluation.run import load_bundle, run_evaluation
from evaluation.ablation import run_ablation
from shodh.ui import run_server


def main():
    parser = argparse.ArgumentParser(
        prog="shodh",
        description="SHODH: AI-Assisted Specification and Workflow Reviewer",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: review
    review_parser = subparsers.add_parser("review", help="Review a specific bundle directory")
    review_parser.add_argument("bundle_path", type=str, help="Path to bundle folder")

    # Command: eval
    subparsers.add_parser("eval", help="Run 12-case benchmark evaluation")

    # Command: ablation
    subparsers.add_parser("ablation", help="Run counterexample ablation study")

    # Command: ui
    ui_parser = subparsers.add_parser("ui", help="Start interactive web dashboard")
    ui_parser.add_argument("--port", type=int, default=8000, help="Web server port (default 8000)")

    args = parser.parse_args()

    if args.command == "review":
        bundle_dir = Path(args.bundle_path)
        if not bundle_dir.exists():
            print(f"Error: Bundle directory not found at {bundle_dir}", file=sys.stderr)
            sys.exit(1)
        data = load_bundle(bundle_dir)
        reviewer = WorkflowReviewer(model_client=FakeModelClient())
        report = reviewer.review(
            requirements_doc=data["requirements"],
            spec_doc=data["specification"],
            workflow_graph=data["workflow"],
            code_snippet=data["code"],
            approvals=data["approvals"],
        )
        print(json.dumps(report.model_dump(), indent=2))

    elif args.command == "eval":
        run_evaluation()

    elif args.command == "ablation":
        run_ablation()

    elif args.command == "ui":
        run_server(args.port)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
