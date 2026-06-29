"""Frozen Bugs4Q manifest loading utilities."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List


REQUIRED_COLUMNS = {
    "subject_id", "buggy_path", "fixed_path", "category", "runnable",
    "adapter", "exclusion_reason",
}


def load_bugs4q_manifest(root: Path, manifest_path: Path | None = None) -> List[Dict[str, str]]:
    """Load and validate the frozen Bugs4Q manifest."""
    path = manifest_path or (root / "data" / "manifests" / "bugs4q_manifest.csv")
    if not path.exists():
        raise FileNotFoundError(
            f"missing Bugs4Q manifest: {path}. "
            "Run scripts/build_bugs4q_manifest.py on the login node first."
        )
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - cols)
        if missing:
            raise ValueError(f"Bugs4Q manifest {path} missing columns: {missing}")
        rows = list(reader)
    return rows


def runnable_bugs4q_rows(root: Path, manifest_path: Path | None = None) -> List[Dict[str, str]]:
    rows = load_bugs4q_manifest(root, manifest_path)
    runnable = [r for r in rows if r.get("runnable", "").lower() == "true"]
    if not runnable:
        raise ValueError("Bugs4Q manifest has zero runnable subjects")
    return runnable
