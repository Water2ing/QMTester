"""RQ1/RQ2 driver: QMTester on Bugs4Q (and matched MorphQ rerun).

Writes per-pair JSONL shards to $JOBFS (SLURM local NVMe) for later reduction.

Usage (inside Apptainer via SLURM array):
    python scripts/run_bugs4q.py \\
        --root /fred/oz402/nhunguyen/ICSE_QMTester \\
        --shard 0 --nshards 6 \\
        --shots 4096 --seed 20240519 \\
        --out_dir $JOBFS/shards \\
        --with_morphq
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--nshards", type=int, default=1)
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--run_id", default=os.environ.get("QMT_RUN_ID", "manual"))
    p.add_argument("--manifest", default="data/manifests/bugs4q_manifest.csv")
    p.add_argument("--with_morphq", action="store_true")
    p.add_argument("--enabled_families", nargs="+",
                   default=["identity", "swap", "phase", "equivalence"])
    args = p.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Add artifact and project root to Python path.
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

    from qmtester.bug_manifest import runnable_bugs4q_rows
    from qmtester.subject_adapter import probe_subject
    from qmtester.pipeline import run_subject
    from qmtester.relations import (
        IdentityInsertion, SwapRewriting, PhaseRewriting, EquivalenceRewriting
    )
    from baselines.morphq_runner import run_morphq

    families_map = {
        "identity": IdentityInsertion,
        "swap": SwapRewriting,
        "phase": PhaseRewriting,
        "equivalence": EquivalenceRewriting,
    }
    active_families = [families_map[f]() for f in args.enabled_families]

    bugs4q_root = root / "vendor" / "bugs4q"
    manifest_path = root / args.manifest
    print(f"[shard {args.shard}/{args.nshards}] loading manifest {manifest_path}...")
    manifest_rows = runnable_bugs4q_rows(root, manifest_path)

    # Assign this shard's subjects.
    manifest_rows = sorted(manifest_rows, key=lambda r: r["subject_id"])
    my_rows = [r for i, r in enumerate(manifest_rows) if i % args.nshards == args.shard]
    print(f"  {len(my_rows)} subjects in this shard")

    log_path = out_dir / f"raw_runs_shard{args.shard:04d}.jsonl"
    summary_path = out_dir / f"summary_shard{args.shard:04d}.jsonl"

    for row in my_rows:
        sid = row["subject_id"]
        qc, reason = probe_subject(bugs4q_root / row["buggy_path"])
        if qc is None:
            print(f"  SKIP {sid}: {reason}")
            continue

        print(f"  RUN  {sid} ({qc.num_qubits}q)")
        result = run_subject(
            subject_id=sid,
            source_qc=qc,
            families=active_families,
            shots=args.shots,
            seed=args.seed,
            alpha=args.alpha,
            log_path=log_path,
            enabled_families=args.enabled_families,
            run_id=args.run_id,
        )

        summary = {
            "run_id": args.run_id,
            "subject_id": sid,
            "buggy_path": row["buggy_path"],
            "fixed_path": row["fixed_path"],
            "category": row["category"],
            "method": "qmtester",
            "detected": result.detected,
            "n_admitted": len(result.admitted_pairs),
            "n_rejected": result.rejected_count,
            "min_p": result.min_p,
            "corrected_alpha": result.corrected_alpha,
            "timeout": result.timeout,
            "unsupported": result.unsupported,
        }
        with summary_path.open("a") as f:
            f.write(json.dumps(summary) + "\n")

        if args.with_morphq and qc is not None:
            morphq_log = out_dir / f"morphq_shard{args.shard:04d}.jsonl"
            m_result = run_morphq(
                subject_id=sid,
                source_qc=qc,
                shots=args.shots,
                seed=args.seed,
                log_path=morphq_log,
                run_id=args.run_id,
            )
            msum = {
                "run_id": args.run_id,
                "subject_id": sid,
                "buggy_path": row["buggy_path"],
                "fixed_path": row["fixed_path"],
                "category": row["category"],
                "method": "morphq",
                "detected": m_result.detected,
                "n_admitted": len(m_result.admitted_pairs),
                "min_p": m_result.min_p,
            }
            morphq_summary = out_dir / f"morphq_summary_shard{args.shard:04d}.jsonl"
            with morphq_summary.open("a") as f:
                f.write(json.dumps(msum) + "\n")

    print(f"[shard {args.shard}] done -> {log_path}")


if __name__ == "__main__":
    main()
