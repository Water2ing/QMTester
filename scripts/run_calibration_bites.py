"""Test whether the noise calibration ever changes a detection decision.

On the benign depolarizing corpus the uncalibrated and calibrated branches both give
0/50, so calibration is an untriggered safeguard. To probe for a regime where it
*bites*, we crank the noise (depolarizing + 5% readout + 3% two-qubit crosstalk) on a
subset of small correct programs and compare, per program, the uncalibrated vs the
calibrated decision. A program where uncalibrated flags a false positive but the
K=20-seed calibrated threshold does not is a case where calibration changes the outcome.

Usage:
  python scripts/run_calibration_bites.py --out_dir data/results/runs/calib_bites_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_harsh_noise(p1=2e-3, p2=1.5e-2, p_readout=0.05, p_crosstalk=0.03):
    from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(p1, 1),
                                   ["h", "x", "y", "z", "s", "t", "sx", "rx", "ry", "rz"])
    nm.add_all_qubit_quantum_error(depolarizing_error(min(0.75, p2 + p_crosstalk), 2),
                                   ["cx", "cz", "swap"])
    nm.add_all_qubit_readout_error(
        ReadoutError([[1 - p_readout, p_readout], [p_readout, 1 - p_readout]]))
    return nm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out_dir", default="data/results/runs/calib_bites_v1")
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--max_qubits", type=int, default=5)
    ap.add_argument("--limit", type=int, default=16)
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

    families = [IdentityInsertion(), SwapRewriting(), PhaseRewriting(), EquivalenceRewriting()]
    noise = build_harsh_noise()
    progs = sorted((root / "benchmarks" / "correct").glob("*.py"))

    rows = []
    n_seen = 0
    for prog in progs:
        if n_seen >= args.limit:
            break
        try:
            qc = rf._load_correct_program(prog)
            if qc is None or qc.num_qubits > args.max_qubits:
                continue
            n_seen += 1
            out = {"program_id": prog.stem, "num_qubits": qc.num_qubits}
            for calibrate in (False, True):
                res = run_subject(
                    subject_id=prog.stem, source_qc=qc, families=families,
                    shots=args.shots, seed=args.seed, alpha=args.alpha,
                    noise_model=noise, calibrate=calibrate,
                    log_path=out_dir / "calib_bites.jsonl",
                    run_id="cal" if calibrate else "uncal",
                )
                key = "cal" if calibrate else "uncal"
                out[f"{key}_fp"] = bool(res.detected)
                out[f"{key}_min_p"] = res.min_p
            out["calibration_changed_decision"] = out["uncal_fp"] and not out["cal_fp"]
            rows.append(out)
            print(f"{prog.stem:>22} q={out['num_qubits']}  uncal_fp={out['uncal_fp']} "
                  f"(min_p={out['uncal_min_p']:.4f})  cal_fp={out['cal_fp']} "
                  f"(min_p={out['cal_min_p']:.4f})  changed={out['calibration_changed_decision']}",
                  flush=True)
        except Exception as exc:  # robust: one bad program must not kill the run
            print(f"{prog.stem}: SKIP ({type(exc).__name__}: {exc})", flush=True)
            continue

    with (out_dir / "calib_bites_summary.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n_uncal = sum(r["uncal_fp"] for r in rows)
    n_cal = sum(r["cal_fp"] for r in rows)
    n_changed = sum(r["calibration_changed_decision"] for r in rows)
    print(f"\n=== harsh-noise specificity on {len(rows)} small correct programs ===")
    print(f"uncalibrated false positives: {n_uncal}/{len(rows)}")
    print(f"calibrated   false positives: {n_cal}/{len(rows)}")
    print(f"programs where calibration changed the decision (uncal FP -> cal clean): {n_changed}")


if __name__ == "__main__":
    main()
