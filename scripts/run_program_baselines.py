"""Oracle-light / builder-layer baseline ablation.

Runs QMTester (full) and three oracle-light baselines over the audited 7 Bugs4Q
program subjects and the 100-case injected benchmark, on BOTH the buggy/mutant and
fixed variants, so we can report detection (on buggy) AND false positives (on fixed)
for each. This isolates what canonicalization + admission add over "rebuild and
compare".

Modes:
  full          - the real QMTester pipeline (canonicalize + chi-squared + admission)
  same_input    - rebuild from the SAME input twice + chi-squared (no transform)
  no_canon_chi2 - metamorphic follow-up + chi-squared WITHOUT canonicalization
  raw_equality  - metamorphic follow-up + exact raw count-equality

Usage:
  python scripts/run_program_baselines.py --out_dir data/results/runs/baselines_g1_v1
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

MODES = ["full", "same_input", "no_canon_chi2", "raw_equality"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out_dir", default="data/results/runs/baselines_g1_v1")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--run_id", default="baselines_g1_v1")
    ap.add_argument("--bugs4q_manifest", default="data/manifests/program_bugs4q_manifest.csv")
    ap.add_argument("--injected_manifest", default="data/manifests/program_mutants_manifest.csv")
    ap.add_argument("--skip_injected", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_baselines import run_program_subject_baseline
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from qmtester.bugs4q_program_subjects import load_bugs4q_program_subjects
    from qmtester.program_mutants import load_program_mutation_cases

    fam = PROGRAM_FAMILIES_DEFAULT
    raw_path = out_dir / "baselines_raw.jsonl"
    # cohort -> mode -> {"buggy_detected","buggy_n","fixed_fp","fixed_n"}
    agg = defaultdict(lambda: defaultdict(lambda: {"bd": 0, "bn": 0, "ff": 0, "fn": 0}))

    def run_one(mode, subject):
        if mode == "full":
            r = run_program_subject(subject, fam, shots=args.shots, seed=args.seed, alpha=args.alpha)
            return bool(r.detected)
        r = run_program_subject_baseline(subject, fam, mode, shots=args.shots, seed=args.seed, alpha=args.alpha)
        return bool(r.detected)

    def record(cohort, mode, subject_id, variant, detected, is_positive):
        with raw_path.open("a") as f:
            f.write(json.dumps({
                "run_id": args.run_id, "cohort": cohort, "mode": mode,
                "subject_id": subject_id, "variant": variant, "detected": detected,
            }) + "\n")
        a = agg[cohort][mode]
        if is_positive:
            a["bn"] += 1
            a["bd"] += int(detected)
        else:
            a["fn"] += 1
            a["ff"] += int(detected)

    # ---------- Bugs4Q (7 audited) ----------
    allowed = {r["subject_id"] for r in csv.DictReader((root / args.bugs4q_manifest).open(newline=""))}
    for variant, is_pos in [("buggy", True), ("fixed", False)]:
        for s in load_bugs4q_program_subjects(root, variant=variant):
            if s.subject_id not in allowed:
                continue
            sid = s.subject_id
            dets = {}
            for mode in MODES:
                # fresh subject per mode to avoid any in-place mutation surprises
                subj = next(x for x in load_bugs4q_program_subjects(root, variant=variant) if x.subject_id == sid)
                det = run_one(mode, subj)
                dets[mode] = det
                record("Bugs4Q", mode, sid, variant, det, is_pos)
            print(f"[Bugs4Q/{variant}] {sid[:46]:46} " +
                  " ".join(f"{m}={int(dets[m])}" for m in MODES), flush=True)

    # ---------- Injected (100) ----------
    if not args.skip_injected:
        for case in load_program_mutation_cases(root, root / args.injected_manifest):
            for variant, subject, is_pos in [("fixed", case.fixed_subject, False), ("mutant", case.mutant_subject, True)]:
                sid = f"{case.mutant_id}_{variant}"
                for mode in MODES:
                    det = run_one(mode, subject)
                    record("Injected", mode, sid, variant, det, is_pos)
            print(f"[Injected] {case.mutant_id} ({case.relation_family})", flush=True)

    # ---------- Aggregate CSV + console table ----------
    rows = []
    for cohort in agg:
        for mode in MODES:
            a = agg[cohort][mode]
            dp, dlo, dhi = wilson(a["bd"], a["bn"])
            fp, flo, fhi = wilson(a["ff"], a["fn"])
            rows.append({
                "cohort": cohort, "mode": mode,
                "detected": a["bd"], "n_buggy": a["bn"], "detection_rate": round(dp, 4),
                "det_ci_low": round(dlo, 4), "det_ci_high": round(dhi, 4),
                "false_pos": a["ff"], "n_fixed": a["fn"], "fp_rate": round(fp, 4),
                "fp_ci_low": round(flo, 4), "fp_ci_high": round(fhi, 4),
            })
    csv_path = out_dir / "baselines_results.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n" + "=" * 78)
    print(f"{'cohort':9} {'mode':14} {'detect(buggy)':16} {'false-pos(fixed)':16}")
    print("=" * 78)
    for r in rows:
        print(f"{r['cohort']:9} {r['mode']:14} "
              f"{r['detected']:>3}/{r['n_buggy']:<3} ({r['detection_rate']:.2f})   "
              f"{r['false_pos']:>3}/{r['n_fixed']:<3} ({r['fp_rate']:.2f})")
    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()
