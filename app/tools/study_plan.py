"""Generate or persist study plans from coverage and readiness."""
from pathlib import Path
from typing import Any


def generate_plan(coverage: list[dict], readiness: dict[str, float]) -> dict[str, Any]:
    """Build a study plan (ordered topics, priorities). Stub."""
    return {"topics": [], "priorities": {}}


def save_plan(plan: dict[str, Any], out_path: Path) -> None:
    """Write plan to JSON or similar. Stub."""
    import json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2))
