"""Localize the power-curve floor below TVD=0.02.

The coarse sweep (run_power_curve.py) has its smallest drift at 0.01, so all
sub-0.02 mutants fall in one [0,0.02) bin and the 50%/80% crossings are only
*bounded* above by 0.02, not localized. This sweep adds fine drifts in (0.001, 0.02)
and fine bins below 0.02, so the crossings can be measured rather than bounded.

Usage:
  python scripts/run_power_curve_fine.py --out_dir data/results/runs/power_curve_fine_v1
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _tvd(a, b):
    keys = set(a) | set(b)
    ta = sum(a.values()) or 1
    tb = sum(b.values()) or 1
    return 0.5 * sum(abs(a.get(k, 0) / ta - b.get(k, 0) / tb) for k in keys)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out_dir", default="data/results/runs/power_curve_fine_v1")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--effect_shots", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))

    from qmtester.canonicalize import canonicalize
    from qmtester.execute import execute_circuit
    from qmtester.program_mutants import ParamRotationDriftSubject
    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT

    thetas = [0.35, 0.70, 1.05, 1.40, 1.75, 2.10]
    # fine drifts concentrated below the coarse 0.01 floor, to populate TVD in (0,0.02)
    drifts = [0.001, 0.003, 0.005, 0.007, 0.009, 0.012, 0.016, 0.020, 0.025,
              0.030, 0.035, 0.040, 0.045, 0.050, 0.060, 0.070, 0.085]
    axes = ["ry", "rx"]

    points = []
    cid = 0
    for axis in axes:
        for theta in thetas:
            for drift in drifts:
                cid += 1
                seed = args.seed + cid
                mut = ParamRotationDriftSubject(f"pcf{cid}", theta=theta, drift=drift, axis=axis, buggy=True)
                cand = mut.enumerate_parameter_periodicity(None)[0]
                src = execute_circuit(mut.build(cand.source_input), shots=args.effect_shots, seed=seed + 1000)
                fu = execute_circuit(mut.build(cand.followup_input), shots=args.effect_shots, seed=seed + 1000)
                if src is None or fu is None:
                    continue
                ok, _, sc, fc = canonicalize(src, fu, cand.canon_map)
                if not ok:
                    continue
                tvd = _tvd(sc, fc)
                res = run_program_subject(mut, PROGRAM_FAMILIES_DEFAULT, shots=args.shots, seed=seed, alpha=args.alpha)
                points.append({"axis": axis, "theta": round(theta, 4), "drift": round(drift, 4),
                               "tvd": round(tvd, 6), "detected": int(bool(res.detected))})
        print(f"[{axis}] done ({len(points)} points)", flush=True)

    csv_path = out_dir / "power_curve_fine_points.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["axis", "theta", "drift", "tvd", "detected"])
        w.writeheader(); w.writerows(points)

    # fine bins below 0.02
    edges = [0.000, 0.005, 0.010, 0.013, 0.016, 0.018, 0.020, 0.022, 0.025, 0.030, 0.040, 0.080]
    print("\n" + "=" * 64)
    print("FINE DETECTION RATE vs TVD (sub-0.02 localization)")
    print("=" * 64)
    print(f"{'TVD bin':>16}  {'det/n':>9}  {'rate':>6}  {'95% CI':>16}")
    bin_summ = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        sub = [p for p in points if lo <= p["tvd"] < hi]
        if not sub:
            continue
        k = sum(p["detected"] for p in sub)
        rate, clo, chi = wilson(k, len(sub))
        bin_summ.append((lo, hi, k, len(sub), rate, clo, chi))
        print(f"  [{lo:.4f},{hi:.4f})  {k:>4}/{len(sub):<4}  {rate:>5.2f}  [{clo:.2f},{chi:.2f}]")

    def crossover(thresh):
        for lo, hi, k, n, rate, clo, chi in bin_summ:
            if rate >= thresh:
                return (lo + hi) / 2
        return None
    print(f"\nMeasured TVD at >=50% detection: {crossover(0.5)}")
    print(f"Measured TVD at >=80% detection: {crossover(0.8)}")
    print(f"Total points: {len(points)}; wrote {csv_path}")


if __name__ == "__main__":
    main()
