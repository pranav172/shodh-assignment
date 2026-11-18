"""Export JSON schemas from Pydantic models for cross-tool interoperability."""

import json
from pathlib import Path
from shodh.contracts import (
    RequirementsDocument,
    SpecificationDocument,
    WorkflowGraph,
    ApprovalDocument,
    ReviewReport,
)

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"


def export_all_schemas(target_dir: Path = SCHEMA_DIR) -> None:
    """Generate standardized JSON schema files for all 5 core artifacts."""
    target_dir.mkdir(parents=True, exist_ok=True)

    mappings = {
        "requirements.json": RequirementsDocument,
        "specification.json": SpecificationDocument,
        "workflow.json": WorkflowGraph,
        "approvals.json": ApprovalDocument,
        "report.json": ReviewReport,
    }

    for filename, model in mappings.items():
        out_path = target_dir / filename
        schema_dict = model.model_json_schema()
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(schema_dict, f, indent=2)
        print(f"Exported {filename} -> {out_path}")


if __name__ == "__main__":
    export_all_schemas()
