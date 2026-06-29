"""Detection and specificity of the real Bugs4Q subjects under a realistic
readout/crosstalk noise model.

Re-runs all seven audited Bugs4Q subjects (buggy and fixed) under a richer noise
model (depolarizing + 2% symmetric readout error + 1% two-qubit crosstalk, shared
with run_rich_noise_falsepos) and reports detection on the buggy variants and false
positives on the fixed variants.

Usage:
  python scripts/run_realistic_noise_detection.py --out_dir data/results/runs/realistic_det_v1
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
    ap.add_argument("--out_dir", default="data/results/runs/realistic_det_v1")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--bugs4q_manifest", default="data/manifests/program_bugs4q_manifest.csv")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from qmtester.bugs4q_program_subjects import load_bugs4q_program_subjects
    from qmtester.program_pipeline import run_program_subject
    import importlib.util
    spec_rn = importlib.util.spec_from_file_location("rn", str(root / "scripts" / "run_rich_noise_falsepos.py"))
    rn = importlib.util.module_from_spec(spec_rn)
    spec_rn.loader.exec_module(rn)

    allowed = {r["subject_id"] for r in csv.DictReader((root / args.bugs4q_manifest).open(newline=""))}
    buggy = [s for s in load_bugs4q_program_subjects(root, "buggy") if s.subject_id in allowed]
    fixed = {s.subject_id: s for s in load_bugs4q_program_subjects(root, "fixed") if s.subject_id in allowed}
    fam = PROGRAM_FAMILIES_DEFAULT
    noise = rn.build_rich_noise()

    rows = []
    det = fp = n = 0
    print("=" * 78)
    print(f"{'subject':40} {'family':20} {'detect':7} {'FP'}")
    print("=" * 78)
    for bs in buggy:
        sid = bs.subject_id
        fs = fixed.get(sid)
        if fs is None:
            continue
        n += 1
        family = (bs.relations or ["?"])[0].replace("program_", "")
        rb = run_program_subject(bs, fam, shots=args.shots, seed=args.seed, alpha=args.alpha, noise_model=noise)
        rf = run_program_subject(fs, fam, shots=args.shots, seed=args.seed, alpha=args.alpha, noise_model=noise)
        d = bool(rb.detected); f = bool(rf.detected)
        det += int(d); fp += int(f)
        rows.append({"subject_id": sid, "family": family, "detected": int(d),
                     "false_positive": int(f), "min_p_buggy": rb.min_p, "min_p_fixed": rf.min_p})
        print(f"{sid[:40]:40} {family:20} {('DET' if d else 'miss'):7} {'FP' if f else '-'}")

    csv_path = out_dir / "realistic_detection.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print("\n" + "=" * 78)
    print(f"Under realistic readout(2%)+crosstalk(1%) noise: detection {det}/{n}, false positives {fp}/{n}")
    det_by_fam = {}
    for r in rows:
        det_by_fam.setdefault(r["family"], [0, 0])
        det_by_fam[r["family"]][0] += r["detected"]; det_by_fam[r["family"]][1] += 1
    for famname, (k, tot) in sorted(det_by_fam.items()):
        print(f"  {famname}: {k}/{tot}")
    (out_dir / "summary.json").write_text(json.dumps(
        {"detection": f"{det}/{n}", "false_positives": f"{fp}/{n}", "by_family": det_by_fam}, indent=2))
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
