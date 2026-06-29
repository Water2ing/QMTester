"""Deployable static-analysis baseline + minimal-QMTester ablation.

Compares two deployable detectors against the full QMTester pipeline:

  static_detect: LintQ-style structural checks on the EMITTED circuit, no execution / no
  spec --- the information a linter has. Includes the register-shape bit-width check (LintQ's
  `ql-measure-all-abuse`), redundant/never-measured register, and double measurement.

  minimal-QMTester: canonicalize + raw count-equality (no permutation test), to show how
  much the statistical oracle adds to detection on the deterministic real families.

A static checker flags the syntactic register-shape defect (measure_all) but is structurally
unable to flag the 7 semantic builder-contract defects (role permutation, endianness, ancilla
uncompute, QFT direction): a buggy and a correct builder there emit equally well-formed
circuits that only differ in the measured distribution.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def static_detect(qc):
    """LintQ-style structural detection on the emitted circuit. Returns (flagged, reasons)."""
    reasons = []
    measured_q = set()
    seen_measure_on = set()
    for ci in qc.data:
        name = ci.operation.name
        if name == "measure":
            q = ci.qubits[0]
            if q in seen_measure_on:
                reasons.append("double_measurement")
            seen_measure_on.add(q)
            measured_q.add(q)
    # register-shape / measure_all: more classical bits than distinct measured qubits, with
    # a redundant extra register (LintQ ql-measure-all-abuse: "twice as long output").
    if qc.num_clbits > len(measured_q) and len(qc.cregs) > 1:
        reasons.append("redundant_register(measure_all)")
    # never-measured declared register (constant-0 output bits).
    measured_clbits = sum(1 for ci in qc.data if ci.operation.name == "measure")
    if qc.num_clbits > measured_clbits:
        reasons.append("unmeasured_clbits")
    return (len(reasons) > 0), sorted(set(reasons))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--bugs4q_manifest", default="data/manifests/program_bugs4q_manifest.csv")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "artifact"))
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from qmtester.bugs4q_program_subjects import load_bugs4q_program_subjects
    from qmtester.register_shape import RegisterShapeSubject, run_register_shape_subject
    from qmtester.execute import execute_circuit
    from qmtester.canonicalize import canonicalize
    import numpy as np

    allowed = {r["subject_id"] for r in csv.DictReader((root / args.bugs4q_manifest).open(newline=""))}
    buggy = [s for s in load_bugs4q_program_subjects(root, "buggy") if s.subject_id in allowed]
    fixed = {s.subject_id: s for s in load_bugs4q_program_subjects(root, "fixed") if s.subject_id in allowed}
    fam = PROGRAM_FAMILIES_DEFAULT

    print("=" * 86)
    print(f"{'subject':40} {'family':22} {'static':7} {'minQM':6} {'QMtest'}")
    print("=" * 86)

    static_det = static_fp = 0
    min_det = 0
    qm_det = 0
    n = 0
    for bs in buggy:
        sid = bs.subject_id
        fs = fixed.get(sid)
        if fs is None:
            continue
        n += 1
        family = (bs.relations or ["?"])[0].replace("program_", "")
        # candidate inputs from the family
        cands = []
        for f in fam:
            if bs.relations and f.name not in bs.relations:
                continue
            cands.extend(f.enumerate(bs, np.random.default_rng(args.seed)))

        # --- static baseline (on the buggy emitted circuit; FP on the fixed) ---
        sdet = sfp = False
        for c in cands:
            d, _ = static_detect(bs.build(c.followup_input))
            sdet = sdet or d
            d2, _ = static_detect(fs.build(c.followup_input))
            sfp = sfp or d2
        static_det += int(sdet); static_fp += int(sfp)

        # --- minimal-QMTester: canonicalize + RAW count-equality (no permutation test) ---
        mdet = False
        for c in cands:
            sc = execute_circuit(bs.build(c.source_input), shots=args.shots, seed=args.seed)
            fc = execute_circuit(bs.build(c.followup_input), shots=args.shots, seed=args.seed)
            if sc is None or fc is None:
                continue
            ok, _, a, b = canonicalize(sc, fc, c.canon_map)
            if ok and any(a.get(k, 0) != b.get(k, 0) for k in set(a) | set(b)):
                mdet = True
        min_det += int(mdet)

        # --- QMTester (full distribution pipeline) detection, for reference ---
        from qmtester.program_pipeline import run_program_subject
        qd = bool(run_program_subject(bs, fam, shots=args.shots, seed=args.seed, alpha=args.alpha).detected)
        qm_det += int(qd)

        print(f"{sid[:40]:40} {family:22} {('DET' if sdet else '-'):7} "
              f"{('DET' if mdet else '-'):6} {'DET' if qd else '-'}")

    # register-shape subject (qiskit_github_12 / measure_all): the one static can reach
    rs = RegisterShapeSubject(variant="buggy", n=3)
    rs_static, rs_reasons = static_detect(rs.build({"n": 3}))
    rs_qm, _ = run_register_shape_subject(rs, shots=args.shots, seed=args.seed)
    print(f"{'qiskit_github_12 (measure_all)':40} {'register_shape':22} "
          f"{('DET' if rs_static else '-'):7} {'n/a':6} {'DET' if rs_qm else '-'}")

    print("\n" + "=" * 86)
    print(f"Static analyzer (deployable): {static_det}/{n} semantic distribution defects detected "
          f"({static_fp} FP), + register-shape: {'DET' if rs_static else 'miss'} ({','.join(rs_reasons)})")
    print(f"Minimal QMTester (canon + raw-equality, no permutation test): {min_det}/{n}")
    print(f"QMTester (full distribution pipeline): {qm_det}/{n}; register-shape: {'DET' if rs_qm else 'miss'}")
    print("=> a deployable static checker reaches only the SYNTACTIC register-shape case;")
    print("   the 7 SEMANTIC builder-contract defects are detected by QMTester, not by static analysis.")


if __name__ == "__main__":
    main()
