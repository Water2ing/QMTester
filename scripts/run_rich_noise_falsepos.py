"""RQ4 extension: specificity under a richer noise model.

Runs the 50-correct-program false-positive check under a richer noise model that
adds readout and correlated/crosstalk errors on top of depolarizing noise:
  depolarizing (p1=1e-3, p2=5e-3) + symmetric readout error (p=2%) + a two-qubit
  crosstalk term (extra depolarizing p=1% on entangling gates),
both uncalibrated and with the K=20-seed calibrated threshold.

Usage:
  python scripts/run_rich_noise_falsepos.py --out_dir data/results/runs/rich_noise_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_rich_noise(p1=1e-3, p2=5e-3, p_readout=0.02, p_crosstalk=0.01):
    from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error
    nm = NoiseModel()
    e1 = depolarizing_error(p1, 1)
    nm.add_all_qubit_quantum_error(e1, ["h", "x", "y", "z", "s", "t", "sx", "rx", "ry", "rz"])
    # two-qubit depolarizing + a crosstalk proxy composed on entangling gates
    e2 = depolarizing_error(min(0.75, p2 + p_crosstalk), 2)
    nm.add_all_qubit_quantum_error(e2, ["cx", "cz", "swap"])
    # symmetric readout (measurement) error -- the key omitted term
    ro = ReadoutError([[1 - p_readout, p_readout], [p_readout, 1 - p_readout]])
    nm.add_all_qubit_readout_error(ro)
    return nm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out_dir", default="data/results/runs/rich_noise_v1")
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
    # reuse the program loader from the falsepos runner
    import importlib.util
    spec = importlib.util.spec_from_file_location("rf", str(root / "scripts" / "run_falsepos.py"))
    rf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rf)

    families = [IdentityInsertion(), SwapRewriting(), PhaseRewriting(), EquivalenceRewriting()]
    noise = build_rich_noise()
    programs = sorted((root / "benchmarks" / "correct").glob("*.py"))[:args.limit]

    for calibrate in (False, True):
        label = "rich_noisy_cal" if calibrate else "rich_noisy"
        summ = out_dir / f"falsepos_summary_{label}.jsonl"
        n_fp = n_total = 0
        min_ps = []
        for prog in programs:
            qc = rf._load_correct_program(prog)
            if qc is None:
                continue
            res = run_subject(
                subject_id=prog.stem, source_qc=qc, families=families,
                shots=args.shots, seed=args.seed, alpha=args.alpha,
                noise_model=noise, calibrate=calibrate,
                log_path=out_dir / f"falsepos_{label}.jsonl", run_id=label,
            )
            n_total += 1
            n_fp += int(bool(res.detected))
            min_ps.append(res.min_p)
            with summ.open("a") as f:
                f.write(json.dumps({"program_id": prog.stem, "false_positive": bool(res.detected),
                                    "label": label, "min_p": res.min_p}) + "\n")
        mn = min(min_ps) if min_ps else None
        print(f"[{label}] false positives: {n_fp}/{n_total}   min_p={mn}", flush=True)


if __name__ == "__main__":
    main()
