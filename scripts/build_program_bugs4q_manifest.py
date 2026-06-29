"""Build frozen manifest for audited Bugs4Q program-level subjects."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--out", default="data/manifests/program_bugs4q_manifest.csv")
    p.add_argument("--excluded", default="data/manifests/program_excluded.csv")
    args = p.parse_args()

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "artifact"))

    from qmtester.bugs4q_program_subjects import (
        PROGRAM_BUGS4Q_EXCLUSIONS,
        load_bugs4q_program_subjects,
    )
    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT

    included = []
    excluded = list(PROGRAM_BUGS4Q_EXCLUSIONS)
    for buggy, fixed in zip(
        load_bugs4q_program_subjects(root, "buggy"),
        load_bugs4q_program_subjects(root, "fixed"),
    ):
        buggy_result = run_program_subject(
            buggy, PROGRAM_FAMILIES_DEFAULT, shots=args.shots, seed=args.seed, alpha=0.05
        )
        fixed_result = run_program_subject(
            fixed, PROGRAM_FAMILIES_DEFAULT, shots=args.shots, seed=args.seed, alpha=0.05
        )
        if fixed_result.detected:
            excluded.append({
                "subject_id": buggy.subject_id,
                "buggy_path": str(buggy.source_path.relative_to(root / "vendor" / "bugs4q")),
                "fixed_path": str(fixed.fixed_path.relative_to(root / "vendor" / "bugs4q")),
                "reason": "fixed_variant_detected",
            })
            continue
        if not buggy_result.detected:
            excluded.append({
                "subject_id": buggy.subject_id,
                "buggy_path": str(buggy.source_path.relative_to(root / "vendor" / "bugs4q")),
                "fixed_path": str(fixed.fixed_path.relative_to(root / "vendor" / "bugs4q")),
                "reason": "buggy_variant_not_detected",
            })
            continue
        included.append({
            "subject_id": buggy.subject_id,
            "bug_category": buggy.bug_category,
            "relations": ";".join(buggy.relations),
            "buggy_path": str(buggy.source_path.relative_to(root / "vendor" / "bugs4q")),
            "fixed_path": str(fixed.fixed_path.relative_to(root / "vendor" / "bugs4q")),
            "buggy_detected": "true",
            "fixed_detected": "false",
            "buggy_min_p": buggy_result.min_p,
            "fixed_min_p": fixed_result.min_p,
            "n_admitted": len(buggy_result.admitted_pairs),
        })

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "subject_id", "bug_category", "relations", "buggy_path", "fixed_path",
            "buggy_detected", "fixed_detected", "buggy_min_p", "fixed_min_p", "n_admitted",
        ])
        writer.writeheader()
        writer.writerows(included)

    excluded_path = root / args.excluded
    excluded_path.parent.mkdir(parents=True, exist_ok=True)
    with excluded_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["subject_id", "buggy_path", "fixed_path", "reason"])
        writer.writeheader()
        writer.writerows(excluded)

    print(f"Wrote {len(included)} audited Bugs4Q program subjects -> {out_path}")
    print(f"Wrote {len(excluded)} program exclusions -> {excluded_path}")


if __name__ == "__main__":
    main()
