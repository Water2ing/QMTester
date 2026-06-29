"""RQ2 (injected faults) + RQ3a (relation-family ablation) driver.

Reads a frozen injected-mutant manifest, then runs QMTester and optional MorphQ
under identical settings. Supports ablation via --enabled_families flag.

Usage:
    python scripts/run_injected.py \\
        --root . --shard 0 --nshards 10 \\
        --shots 4096 --seed 20240519 \\
        --out_dir $JOBFS/injected \\
        --enabled_families identity swap phase equivalence
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace


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
    p.add_argument("--mutant_manifest", default="data/manifests/injected_mutants.csv")
    p.add_argument("--enabled_families", nargs="+",
                   default=["identity", "swap", "phase", "equivalence"])
    p.add_argument("--with_morphq", action="store_true", default=False)
    p.add_argument("--tag", default="", help="Suffix appended to output filenames to avoid collisions (e.g. 'shots_8192')")
    p.add_argument("--mutants", type=int, default=250)
    p.add_argument("--max_per_source", type=int, default=25)
    p.add_argument("--min_tvd", type=float, default=0.02)
    p.add_argument("--effect_shots", type=int, default=8192)
    args = p.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

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

    mutants = _load_mutant_manifest(root, root / args.mutant_manifest)
    if len(mutants) < args.mutants:
        raise SystemExit(f"Mutant manifest has only {len(mutants)}/{args.mutants} mutants")
    mutants = mutants[:args.mutants]

    my_mutants = [m for i, m in enumerate(mutants) if i % args.nshards == args.shard]
    print(f"[shard {args.shard}] {len(my_mutants)} mutants")

    fam_label = "_".join(args.enabled_families)
    tag_suffix = f"_{args.tag}" if args.tag else ""
    log_path = out_dir / f"injected_{fam_label}_shard{args.shard:04d}{tag_suffix}.jsonl"
    summary_path = out_dir / f"injected_summary_{fam_label}_shard{args.shard:04d}{tag_suffix}.jsonl"

    for m in my_mutants:
        print(f"  MUTANT {m.mutant_id} op={m.operator}")
        result = run_subject(
            subject_id=m.mutant_id,
            source_qc=m.circuit,
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
            "mutant_id": m.mutant_id,
            "source_id": m.source_id,
            "operator": m.operator,
            "method": "qmtester",
            "families": args.enabled_families,
            "site": m.site,
            "effect_tvd": m.effect_tvd,
            "detected": result.detected,
            "n_admitted": len(result.admitted_pairs),
            "min_p": result.min_p,
        }
        with summary_path.open("a") as f:
            f.write(json.dumps(summary) + "\n")

        if args.with_morphq:
            mr = run_morphq(m.mutant_id, m.circuit, shots=args.shots, seed=args.seed, run_id=args.run_id)
            with summary_path.open("a") as f:
                f.write(json.dumps({
                    "run_id": args.run_id,
                    "mutant_id": m.mutant_id,
                    "source_id": m.source_id,
                    "operator": m.operator,
                    "site": m.site,
                    "effect_tvd": m.effect_tvd,
                    "method": "morphq",
                    "detected": mr.detected, "n_admitted": len(mr.admitted_pairs),
                }) + "\n")

    print(f"[shard {args.shard}] done -> {log_path}")


def _load_mutant_manifest(root: Path, manifest_path: Path):
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"missing injected mutant manifest: {manifest_path}. "
            "Run scripts/build_injected_manifest.py on the login node first."
        )
    import qiskit.qpy

    mutants = []
    with manifest_path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"mutant_id", "source_id", "operator", "site", "qpy_path"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Injected manifest {manifest_path} missing columns: {sorted(missing)}")
        for row in reader:
            qpy_path = root / row["qpy_path"]
            with qpy_path.open("rb") as qf:
                circuits = qiskit.qpy.load(qf)
            effect_tvd = row.get("effect_tvd") or None
            mutants.append(SimpleNamespace(
                mutant_id=row["mutant_id"],
                source_id=row["source_id"],
                operator=row["operator"],
                site=row["site"],
                effect_tvd=float(effect_tvd) if effect_tvd is not None else None,
                circuit=circuits[0],
            ))
    return mutants


if __name__ == "__main__":
    main()
