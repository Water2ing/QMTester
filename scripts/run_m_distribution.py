"""Per-subject admitted-pair count m under the realistic readout/crosstalk noise model.

Computes the full distribution of m (the number of admitted test pairs per subject)
across the correct-program benchmark, and reports the m of the thin-margin subject
(the one with the smallest uncorrected p-value), so the realistic-noise specificity
result can be checked against the per-subject Bonferroni threshold alpha/m. m is
recovered as alpha / corrected_alpha (corrected_alpha = alpha/m, SubjectResult).

Usage:
  python scripts/run_m_distribution.py --out_dir data/results/runs/m_distribution_v1
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out_dir", default="data/results/runs/m_distribution_v1")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

    from qmtester.pipeline import run_subject
    from qmtester.relations import (
        IdentityInsertion, SwapRewriting, PhaseRewriting, EquivalenceRewriting,
    )
    import importlib.util
    spec = importlib.util.spec_from_file_location("rf", str(root / "scripts" / "run_falsepos.py"))
    rf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rf)
    spec_rn = importlib.util.spec_from_file_location("rn", str(root / "scripts" / "run_rich_noise_falsepos.py"))
    rn = importlib.util.module_from_spec(spec_rn)
    spec_rn.loader.exec_module(rn)

    families = [IdentityInsertion(), SwapRewriting(), PhaseRewriting(), EquivalenceRewriting()]
    noise = rn.build_rich_noise()
    programs = sorted((root / "benchmarks" / "correct").glob("*.py"))[:args.limit]

    rows = []
    for prog in programs:
        qc = rf._load_correct_program(prog)
        if qc is None:
            continue
        res = run_subject(
            subject_id=prog.stem, source_qc=qc, families=families,
            shots=args.shots, seed=args.seed, alpha=args.alpha,
            noise_model=noise, calibrate=False, run_id="m_dist",
        )
        m = round(args.alpha / res.corrected_alpha) if res.corrected_alpha else 0
        rows.append({
            "program_id": prog.stem,
            "m": m,
            "corrected_alpha": res.corrected_alpha,
            "min_p": res.min_p,
            "false_positive": int(bool(res.detected)),
            "survives_by_correction": int(res.min_p >= res.corrected_alpha),
        })
        print(f"{prog.stem:34} m={m:<4} alpha/m={res.corrected_alpha:.5f} "
              f"min_p={res.min_p:.4f} fp={int(bool(res.detected))}", flush=True)

    csv_path = out_dir / "m_distribution.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    ms = sorted(r["m"] for r in rows)
    n = len(ms)
    thin = min(rows, key=lambda r: r["min_p"])
    fp_total = sum(r["false_positive"] for r in rows)
    print("\n" + "=" * 72)
    print(f"n={n} correct programs (realistic readout+crosstalk noise)")
    print(f"m distribution: min={ms[0]} median={ms[n//2]} max={ms[-1]} "
          f"(quartiles {ms[n//4]}, {ms[n//2]}, {ms[(3*n)//4]})")
    print(f"thin-margin subject (smallest min_p): {thin['program_id']} "
          f"min_p={thin['min_p']:.4f}, m={thin['m']}, alpha/m={thin['corrected_alpha']:.5f}")
    print(f"  -> survives by correction (min_p >= alpha/m)? "
          f"{'YES' if thin['min_p'] >= thin['corrected_alpha'] else 'NO'}")
    print(f"false positives total: {fp_total}/{n}")
    print(f"all survive by correction: "
          f"{all(r['survives_by_correction'] for r in rows)}")
    summ = {"n": n, "m_min": ms[0], "m_median": ms[n//2], "m_max": ms[-1],
            "thin_subject": thin["program_id"], "thin_min_p": thin["min_p"],
            "thin_m": thin["m"], "thin_alpha_over_m": thin["corrected_alpha"],
            "false_positives": fp_total}
    (out_dir / "m_distribution_summary.json").write_text(json.dumps(summ, indent=2))
    print(f"\nwrote {csv_path}")


if __name__ == "__main__":
    main()
