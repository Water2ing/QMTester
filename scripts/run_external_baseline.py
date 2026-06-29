"""External reference-oracle baseline for builder-layer defect detection.

This baseline detects builder-layer defects via an oracle differential / statistical
assertion that compares each program against its known-correct FIXED version. It is the
detection ceiling, since it has ground truth, against which QMTester is compared (QMTester
matches it without any oracle, by transforming the program input and rebuilding instead).

  detection  : buggy-program counts vs fixed-reference counts on a bug-exposing input
               -> a true positive when the two-sample test rejects.
  specificity: fixed-program vs the fixed reference at INDEPENDENT seeds (a correct
               program against its own reference) -> a false positive if the test rejects.

Run in the QMTester env (qiskit-terra 0.45 / aer 0.13):
  python scripts/run_external_baseline.py --out_dir data/results/runs/external_baseline_v1
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out_dir", default="data/results/runs/external_baseline_v1")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--bugs4q_manifest", default="data/manifests/program_bugs4q_manifest.csv")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))

    import numpy as np
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from qmtester.bugs4q_program_subjects import load_bugs4q_program_subjects
    from qmtester.execute import execute_circuit
    from qmtester.oracle.chisq import two_sample_test
    from qmtester.oracle.correction import bonferroni_threshold, apply_bonferroni
    from qmtester.canonicalize import _align_support, _flatten_counts

    fam = PROGRAM_FAMILIES_DEFAULT
    allowed = {r["subject_id"] for r in csv.DictReader((root / args.bugs4q_manifest).open(newline=""))}
    buggy = {s.subject_id: s for s in load_bugs4q_program_subjects(root, "buggy") if s.subject_id in allowed}
    fixed = {s.subject_id: s for s in load_bugs4q_program_subjects(root, "fixed") if s.subject_id in allowed}

    rng = np.random.default_rng(args.seed + 1)
    rows = []
    det_n = fp_n = n = 0

    for sid in sorted(buggy):
        bsubj, fsubj = buggy[sid], fixed.get(sid)
        if fsubj is None:
            continue
        cands = []
        for f in fam:
            if bsubj.relations and f.name not in bsubj.relations:
                continue
            cands.extend(f.enumerate(bsubj, np.random.default_rng(args.seed)))
        if not cands:
            continue
        n += 1
        # Test on every input the relation touches (source and follow-up): a developer
        # with the correct reference would diff the program against it on these inputs.
        inputs = []
        for c in cands:
            inputs.append(c.source_input)
            inputs.append(c.followup_input)
        thr = bonferroni_threshold(args.alpha, len(inputs))

        det_ps, fp_ps = [], []
        for inp in inputs:
            bc = execute_circuit(bsubj.build(inp), shots=args.shots, seed=args.seed)
            fc = execute_circuit(fsubj.build(inp), shots=args.shots, seed=args.seed)
            if bc is None or fc is None:
                continue
            bcv, fcv = _align_support(_flatten_counts(bc), _flatten_counts(fc))
            det_ps.append(two_sample_test(bcv, fcv, thr, rng).p_value)
            # specificity: the SAME correct program vs its reference at an independent seed
            fc2 = execute_circuit(fsubj.build(inp), shots=args.shots, seed=args.seed + 7919)
            if fc2 is not None:
                f1, f2 = _align_support(_flatten_counts(fc), _flatten_counts(fc2))
                fp_ps.append(two_sample_test(f1, f2, thr, rng).p_value)

        detected = apply_bonferroni(args.alpha, det_ps)
        false_pos = apply_bonferroni(args.alpha, fp_ps)
        det_n += int(detected)
        fp_n += int(false_pos)
        rows.append({"subject_id": sid, "detected": int(detected), "false_pos": int(false_pos),
                     "n_inputs": len(inputs), "min_p_detect": round(min(det_ps, default=1.0), 6)})
        print(f"  {sid[:50]:50} detect={int(detected)} fp={int(false_pos)} "
              f"(min_p={min(det_ps, default=1.0):.3g})", flush=True)

    csv_path = out_dir / "external_baseline_results.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["subject_id", "detected", "false_pos", "n_inputs", "min_p_detect"])
        w.writeheader(); w.writerows(rows)

    print("\n" + "=" * 64)
    print(f"REFERENCE-ORACLE (external) baseline over {n} in-scope Bugs4Q subjects")
    print(f"  detection (buggy vs known-correct fixed): {det_n}/{n}")
    print(f"  false positives (correct vs reference)  : {fp_n}/{n}")
    print("  (this baseline HAS the oracle; QMTester matches its detection oracle-free)")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
