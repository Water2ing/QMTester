"""Assemble a complete artifact bundle (additive; non-destructive).

Copies the tool source, manifests, the authoritative program-level canonical CSV, and
the backing shards into a fresh output directory. It never modifies the source tree.
See ARTIFACT_BUNDLE_MANIFEST.md.

Usage:
    python scripts/assemble_artifact_bundle.py --out artifact_bundle
    python scripts/assemble_artifact_bundle.py --out artifact_bundle --include-raw-runs

By default the ~134 MB per-pair raw_runs.jsonl is skipped (pass --include-raw-runs to
add it). The summary shards (which derive_metrics.py actually consumes) are always
included.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

RUN = "data/results/runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z"
PAPER_READY = "data/results/paper_ready/program_v1"


def copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif src.exists():
        shutil.copy2(src, dst)
    else:
        print(f"  [skip missing] {src}")
        return
    print(f"  {src}  ->  {dst}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="artifact_bundle")
    ap.add_argument("--include-raw-runs", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing {out}; choose a fresh --out")
    print(f"Assembling bundle at {out}\n")

    # Tool source + drivers
    copy(root / "artifact/qmtester", out / "tool/qmtester")
    for s in ["derive_metrics.py", "run_bugs4q_program.py", "run_program_injected.py",
              "run_falsepos.py", "analyze_oracle_and_typeI.py"]:
        copy(root / "scripts" / s, out / "tool/scripts" / s)

    # Manifests + authoritative canonical + integrity
    for f in ["program_bugs4q_manifest.csv", "program_mutants_manifest.csv",
              "program_hard_mutants_manifest.csv", "program_excluded.csv"]:
        copy(root / PAPER_READY / f, out / "manifests" / f)
    copy(root / PAPER_READY / "canonical_results.csv", out / "results/canonical_results.csv")
    copy(root / PAPER_READY / "SHA256SUMS.txt", out / "results/SHA256SUMS.txt")

    # Raw shards (summary JSONL consumed by derive_metrics.py)
    copy(root / RUN / "shards", out / "raw/shards")
    if args.include_raw_runs:
        copy(root / RUN / "raw_runs.jsonl", out / "raw/raw_runs.jsonl")

    # Docs / audit trail
    for d in ["RESULTS.md", "PAPER_RESULTS_SUMMARY.md", "PAPER_REVISION_NOTES.md",
              "STATISTICAL_VALIDATION.md", "BUGS4Q_RELATION_AUDIT.md",
              "ARTIFACT_BUNDLE_MANIFEST.md"]:
        copy(root / d, out / "docs" / d)

    print("\nDone. Review ARTIFACT_BUNDLE_MANIFEST.md for the manifest.json edits "
          "(set full_reproduction_ready; make Table artifact-status truthful).")


if __name__ == "__main__":
    main()
