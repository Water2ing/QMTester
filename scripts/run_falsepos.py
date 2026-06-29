"""RQ4: false-positive rate on 50 correct programs (MQT Bench).

Runs QMTester under ideal + noisy simulator. Correct programs should NOT be
flagged as buggy; any detection is a false positive.

Usage:
    python scripts/run_falsepos.py \\
        --root . --shots 4096 --seed 20240519 \\
        --out_dir $JOBFS/falsepos \\
        --noisy         # run noisy simulator
        --calibrate     # run K=20 calibration before noisy pairs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--run_id", default=os.environ.get("QMT_RUN_ID", "manual"))
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--noisy", action="store_true")
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--enabled_families", nargs="+",
                   default=["identity", "swap", "phase", "equivalence"])
    args = p.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))

    from qmtester.pipeline import run_subject
    from qmtester.relations import (
        IdentityInsertion, SwapRewriting, PhaseRewriting, EquivalenceRewriting
    )

    families_map = {
        "identity": IdentityInsertion,
        "swap": SwapRewriting,
        "phase": PhaseRewriting,
        "equivalence": EquivalenceRewriting,
    }
    active_families = [families_map[f]() for f in args.enabled_families]

    # Load noise model for noisy simulation.
    noise_model = None
    if args.noisy:
        noise_model = _load_noise_model(root)

    correct_dir = root / "benchmarks" / "correct"
    programs = sorted(correct_dir.glob("*.py"))
    if not programs:
        print("No correct programs found in", correct_dir)
        sys.exit(1)

    label = "noisy_cal" if (args.noisy and args.calibrate) else ("noisy" if args.noisy else "ideal")
    log_path = out_dir / f"falsepos_{label}.jsonl"
    summary_path = out_dir / f"falsepos_summary_{label}.jsonl"

    n_fp = 0
    n_total = 0
    for prog in programs[:args.limit]:
        qc = _load_correct_program(prog)
        if qc is None:
            continue
        sid = prog.stem
        result = run_subject(
            subject_id=sid,
            source_qc=qc,
            families=active_families,
            shots=args.shots,
            seed=args.seed,
            alpha=args.alpha,
            noise_model=noise_model,
            calibrate=args.calibrate,
            log_path=log_path,
            run_id=args.run_id,
        )
        n_total += 1
        fp = result.detected
        if fp:
            n_fp += 1
        row = {"run_id": args.run_id, "program_id": sid, "false_positive": fp, "label": label,
               "n_admitted": len(result.admitted_pairs), "min_p": result.min_p}
        with summary_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"  {sid}: fp={fp} n_admitted={len(result.admitted_pairs)}")

    print(f"\nFalse positives: {n_fp}/{n_total}  ({label})")


def _load_noise_model(root: Path):
    """Load a simple depolarizing noise model from data/manifests/noise.json."""
    import json as _json
    noise_path = root / "data" / "manifests" / "noise.json"
    if not noise_path.exists():
        return _default_noise_model()
    with noise_path.open() as f:
        cfg = _json.load(f)
    return _build_noise_model(cfg)


def _default_noise_model():
    """Depolarizing noise matching the paper's noisy-simulator config (Sec. IV-B)."""
    from qiskit_aer.noise import NoiseModel, depolarizing_error, thermal_relaxation_error
    nm = NoiseModel()
    # p1=1e-3 single-qubit, p2=5e-3 two-qubit depolarizing; T1=T2=80 us, tg=50 ns.
    err1 = depolarizing_error(1e-3, 1)
    err2 = depolarizing_error(5e-3, 2)
    nm.add_all_qubit_quantum_error(err1, ["h", "x", "y", "z", "s", "t", "sx", "rx", "ry", "rz"])
    nm.add_all_qubit_quantum_error(err2, ["cx", "cz", "swap"])
    return nm


def _build_noise_model(cfg: dict):
    from qiskit_aer.noise import NoiseModel, depolarizing_error
    nm = NoiseModel()
    p1 = cfg.get("p1", 1e-3)
    p2 = cfg.get("p2", 5e-3)
    err1 = depolarizing_error(p1, 1)
    err2 = depolarizing_error(p2, 2)
    nm.add_all_qubit_quantum_error(err1, ["h", "x", "y", "z", "s", "t", "sx", "rx", "ry", "rz"])
    nm.add_all_qubit_quantum_error(err2, ["cx", "cz", "swap"])
    return nm


def _load_correct_program(prog: Path):
    """Load a correct program from benchmarks/correct/ as a QuantumCircuit."""
    import importlib.util
    import qiskit
    ns: dict = {"__name__": "__main__", "__file__": str(prog), "__builtins__": __builtins__}
    try:
        src = prog.read_text()
        exec(compile(src, str(prog), "exec"), ns)  # noqa: S102
    except Exception:
        return None
    from qiskit import QuantumCircuit
    for v in ns.values():
        if isinstance(v, QuantumCircuit) and v.num_qubits > 0:
            return v
    return None


if __name__ == "__main__":
    main()
