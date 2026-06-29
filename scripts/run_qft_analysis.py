"""Characterize why program_qft_round_trip detection is probabilistic rather than 1.0.

Measures the canonicalized source-vs-follow-up effect size (TVD) for the real qft subject
at high shots, and the detection rate over many seeds at the 4096-shot operating budget. A
wrong-direction QFT does not scatter the output uniformly; for the subject's specific input
state the forward and inverse outputs partially overlap, so the effect is a moderate TVD (<1)
and detection at 4096 shots is probabilistic.

Usage:
  python scripts/run_qft_analysis.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _tvd(a, b):
    keys = set(a) | set(b)
    ta = sum(a.values()) or 1
    tb = sum(b.values()) or 1
    return 0.5 * sum(abs(a.get(k, 0) / ta - b.get(k, 0) / tb) for k in keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--effect_shots", type=int, default=200000)
    ap.add_argument("--seeds", type=int, default=60)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "artifact"))
    from qmtester.bugs4q_program_subjects import Bugs4QStackOverflowQFTSubject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from qmtester.program_pipeline import run_program_subject
    from qmtester.execute import execute_circuit
    from qmtester.canonicalize import canonicalize
    import numpy as np

    subj = Bugs4QStackOverflowQFTSubject(root=root, variant="buggy")
    cand = subj.enumerate_qft_round_trip(np.random.default_rng(args.seed))[0]

    # True effect size at high shots: canonicalized source vs follow-up distribution.
    src = execute_circuit(subj.build(cand.source_input), shots=args.effect_shots, seed=args.seed)
    fu = execute_circuit(subj.build(cand.followup_input), shots=args.effect_shots, seed=args.seed)
    ok, _, sc, fc = canonicalize(src, fu, cand.canon_map)
    tvd = _tvd(sc, fc) if ok else None

    # support overlap: how much probability mass sits on shared outcomes
    ta = sum(sc.values()); tb = sum(fc.values())
    shared = set(sc) & set(fc)
    overlap = sum(min(sc.get(k, 0) / ta, fc.get(k, 0) / tb) for k in shared)  # = 1 - TVD
    n_src, n_fu, n_shared = len(sc), len(fc), len(shared)

    # Detection rate over seeds at the operating budget.
    fam = PROGRAM_FAMILIES_DEFAULT
    det = 0
    for i in range(args.seeds):
        r = run_program_subject(subj, fam, shots=args.shots, seed=args.seed + 7919 * (i + 1), alpha=args.alpha)
        det += int(bool(r.detected))

    print("=" * 70)
    print("program_qft_round_trip  (qiskit_stackoverflow_7, wrong-direction QFT)")
    print("=" * 70)
    print(f"canonicalized effect size  TVD = {tvd:.4f}  (at {args.effect_shots} shots)")
    print(f"output supports: source={n_src} outcomes, follow-up={n_fu}, shared={n_shared}")
    print(f"shared probability mass (overlap) = {overlap:.4f}  (= 1 - TVD = {1-tvd:.4f})")
    print(f"detection rate @ {args.shots} shots over {args.seeds} seeds = {det}/{args.seeds} = {det/args.seeds:.3f}")
    print("\nInterpretation: the wrong-direction QFT partially overlaps the correct output on")
    print("this input state (overlap mass > 0), so the effect is a MODERATE TVD < 1; at the")
    print("operating 4096-shot budget detection is therefore probabilistic, not deterministic.")


if __name__ == "__main__":
    main()
