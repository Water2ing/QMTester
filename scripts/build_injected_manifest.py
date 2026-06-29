"""Build a frozen injected-mutant manifest and QPY circuit store."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _write_qpy(path: Path, circuit) -> None:
    import qiskit.qpy
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        qiskit.qpy.dump(circuit, f)


def build(root: Path, args) -> None:
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root / "faults"))

    from qmtester.bug_manifest import runnable_bugs4q_rows
    from qmtester.circuit_io import normalize
    from qmtester.relations import (
        EquivalenceRewriting,
        IdentityInsertion,
        PhaseRewriting,
        SwapRewriting,
        enumerate_admitted,
    )
    from qmtester.subject_adapter import probe_subject
    from mutator import generate_mutants
    import numpy as np

    bugs4q_root = root / "vendor" / "bugs4q"
    rows = runnable_bugs4q_rows(root, root / args.bugs4q_manifest)
    source_qcs = {}
    for row in rows:
        qc, reason = probe_subject(bugs4q_root / row["buggy_path"])
        if qc is not None:
            source_qcs[row["subject_id"]] = qc

    mutants = generate_mutants(
        source_qcs,
        n_total=args.mutants,
        seed=args.seed,
        max_per_source=args.max_per_source,
        min_tvd=args.min_tvd,
        effect_shots=args.effect_shots,
    )
    if len(mutants) < args.mutants:
        raise SystemExit(f"Generated only {len(mutants)}/{args.mutants} mutants")

    out = root / args.out
    qpy_dir = root / args.qpy_dir
    out.parent.mkdir(parents=True, exist_ok=True)
    families = [IdentityInsertion(), SwapRewriting(), PhaseRewriting(), EquivalenceRewriting()]
    rng = np.random.default_rng(args.seed)

    fieldnames = [
        "mutant_id", "source_id", "operator", "site", "seed", "effect_tvd",
        "qpy_path", "admitted_total", "admitted_identity", "admitted_swap",
        "admitted_phase", "admitted_equivalence",
    ]
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in mutants:
            rel_qpy = Path(args.qpy_dir) / f"{m.mutant_id}.qpy"
            _write_qpy(root / rel_qpy, m.circuit)
            try:
                admitted, _ = enumerate_admitted(normalize(m.circuit), families, rng)
            except Exception:
                admitted = []
            by_family = {name: 0 for name in ["identity", "swap", "phase", "equivalence"]}
            for cand in admitted:
                by_family[cand.family] = by_family.get(cand.family, 0) + 1
            writer.writerow({
                "mutant_id": m.mutant_id,
                "source_id": m.source_id,
                "operator": m.operator,
                "site": m.site,
                "seed": args.seed,
                "effect_tvd": "" if m.effect_tvd is None else f"{m.effect_tvd:.8f}",
                "qpy_path": str(rel_qpy),
                "admitted_total": len(admitted),
                "admitted_identity": by_family["identity"],
                "admitted_swap": by_family["swap"],
                "admitted_phase": by_family["phase"],
                "admitted_equivalence": by_family["equivalence"],
            })

    print(f"Wrote {len(mutants)} injected mutants -> {out}")
    print(f"Wrote QPY circuits -> {qpy_dir}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--bugs4q_manifest", default="data/manifests/bugs4q_manifest.csv")
    p.add_argument("--out", default="data/manifests/injected_mutants.csv")
    p.add_argument("--qpy_dir", default="data/manifests/injected_mutants_qpy")
    p.add_argument("--mutants", type=int, default=250)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--max_per_source", type=int, default=25)
    p.add_argument("--min_tvd", type=float, default=0.02)
    p.add_argument("--effect_shots", type=int, default=8192)
    args = p.parse_args()
    build(Path(args.root).resolve(), args)


if __name__ == "__main__":
    main()
