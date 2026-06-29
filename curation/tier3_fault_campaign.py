"""Tier 3 - exhaustive, UNBIASED detection-vs-effect-size campaign on REAL programs (GPU).

Extends the reviewer-praised power curve from one synthetic family to a diverse corpus
of real parameterized Qiskit programs (MQT-Bench: VQE, QAOA, QPE, realamp/su2/twolocal,
QNN, ...). For each program with rotation gates we sweep a *drift* delta on the
period-shift follow-up and measure detection at the operating shot budget against the
true effect (TVD) at high shots -- over EVERY (program, delta), with NO detectability
filter. This is the un-circular, large-n statistical base R3/R4 asked for.

Soundness: the period-shift is gate-aware -- 2*pi for uncontrolled rotations (rx/ry/rz/
p/u1/cp/cu1 and the two-qubit Pauli rotations rxx/ryy/rzz) and 4*pi for controlled Pauli
rotations (crx/cry/crz) -- so delta=0 is an exact invariant (also a per-program type-I
check). Detection at delta>0 measures sensitivity vs effect size on real circuit structure.

GPU: runs on Aer's GPU device when available (H100), else CPU. Mass simulation is the
part the H100 accelerates.

Usage (after `source .venv_curation/bin/activate`):
  python curation/tier3_fault_campaign.py \
      --corpus_dir benchmarks/correct \
      --out_dir data/results/runs/tier3_campaign_v1 \
      --device GPU --shots 4096 --effect_shots 32768
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path


def load_circuit(path):
    from qiskit import QuantumCircuit
    ns = {"__name__": "__main__", "__file__": str(path), "__builtins__": __builtins__}
    try:
        exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102
    except Exception:
        return None
    cands = [v for v in ns.values() if isinstance(v, QuantumCircuit) and v.num_qubits > 0]
    return max(cands, key=lambda c: len(c.data)) if cands else None


# rotation gate -> period in units of pi for the MEASUREMENT distribution.
#   2pi: uncontrolled single-qubit rotations (rx/ry/rz/p/u1) and controlled-PHASE
#        (cp/cu1: the +2pi phase on |1..1> is a no-op).
#   2pi: uncontrolled two-qubit Pauli rotations (rxx/ryy/rzz): +2pi -> global -I,
#        which is unobservable in measurement (the delta=0 row self-checks this).
#   4pi: controlled-PAULI rotations (crx/cry/crz): rz(2pi)=-I is a controlled (hence
#        observable) relative phase, so the period is 4pi.
PERIOD_PI = {"rx": 2, "ry": 2, "rz": 2, "p": 2, "u1": 2, "cp": 2, "cu1": 2,
             "rxx": 2, "ryy": 2, "rzz": 2,
             "crx": 4, "cry": 4, "crz": 4}


def _gate(name, angle):
    from qiskit.circuit.library import (RXGate, RYGate, RZGate, PhaseGate,
                                        CPhaseGate, CRXGate, CRYGate, CRZGate,
                                        RXXGate, RYYGate, RZZGate)
    m = {"rx": RXGate, "ry": RYGate, "rz": RZGate, "p": PhaseGate, "u1": PhaseGate,
         "cp": CPhaseGate, "cu1": CPhaseGate, "crx": CRXGate, "cry": CRYGate, "crz": CRZGate,
         "rxx": RXXGate, "ryy": RYYGate, "rzz": RZZGate}
    return m[name](angle)


def shift_rotations(qc, delta):
    """Return (new_circuit, n_rotations): every rotation angle shifted by its period + delta."""
    out = qc.copy_empty_like()
    n = 0
    for ci in qc.data:
        op, qargs, cargs = ci.operation, ci.qubits, ci.clbits
        name = op.name.lower()
        if name in PERIOD_PI and len(op.params) == 1 and isinstance(op.params[0], (int, float)):
            shift = PERIOD_PI[name] * math.pi + delta
            out.append(_gate(name, float(op.params[0]) + shift), qargs, cargs)
            n += 1
        else:
            out.append(op, qargs, cargs)
    return out, n


def ensure_measured(qc):
    if qc.num_clbits == 0 or not any(ci.operation.name == "measure" for ci in qc.data):
        m = qc.copy()
        m.measure_all()
        return m
    return qc


def _top_rotation_count(qc):
    return sum(1 for ci in qc.data if ci.operation.name.lower() in PERIOD_PI)


def expose_rotations(qc, max_reps=4):
    """Surface rotation gates that MQT circuits bury inside custom gate blocks.

    shift_rotations only inspects TOP-LEVEL op names, but MQT ALG-level circuits keep
    high-level structure -- e.g. qft/qftentangled wrap all their `cp` gates inside a
    single top-level `qft` block, and grover's `gate_Q` hides rz/crz/p. Such a program
    counts as zero rotation sites and is silently skipped, even though it is rotation
    rich. Decompose just enough to bring rotation gates to the top level. No-op when the
    circuit already exposes rotations (so a healthy circuit is never altered), and falls
    back to the original if decomposition surfaces nothing (never make a circuit worse).
    """
    if _top_rotation_count(qc) > 0:
        return qc
    cur = qc
    for _ in range(max_reps):
        try:
            nxt = cur.decompose()
        except Exception:
            break
        if _top_rotation_count(nxt) > 0:
            return nxt
        if len(nxt.data) == len(cur.data):   # decomposition converged; nothing new
            break
        cur = nxt
    return qc


def build_sim(device, method="statevector"):
    from qiskit_aer import AerSimulator
    try:
        sim = AerSimulator(method=method, device=device)
        if device.upper() == "GPU" and "GPU" not in sim.available_devices():
            print("  [warn] GPU device not available in Aer; using CPU", flush=True)
            return AerSimulator(method=method)
        return sim
    except Exception as exc:
        print(f"  [warn] GPU backend init failed ({exc}); using CPU", flush=True)
        return AerSimulator(method=method)


_WARNED_ERRORS = set()


def run_counts(sim, qc, shots, seed):
    """Return a counts dict, or None on empty/failed simulation. Distinct simulation
    errors are warned once (so an Aer unsupported-gate/OOM failure is visible, not
    silently collapsed into the same None as an empty-counts result)."""
    from qiskit import transpile
    try:
        tqc = transpile(qc, sim, optimization_level=0)
        res = sim.run(tqc, shots=shots, seed_simulator=seed).result()
        c = res.get_counts()
        return dict(c) if c else None
    except Exception as exc:
        key = f"{type(exc).__name__}: {str(exc).splitlines()[0][:100]}"
        if key not in _WARNED_ERRORS:
            _WARNED_ERRORS.add(key)
            print(f"  [warn] sim error (first occurrence): {key}", flush=True)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--corpus_dir", default="benchmarks/correct")
    ap.add_argument("--out_dir", default="data/results/runs/tier3_campaign_v1")
    ap.add_argument("--device", default="GPU", choices=["GPU", "CPU"])
    ap.add_argument("--shots", type=int, default=4096)
    ap.add_argument("--effect_shots", type=int, default=32768)
    ap.add_argument("--seed", type=int, default=20240519)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--max_programs", type=int, default=10000)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    from qmtester.canonicalize import canonicalize
    from qmtester.oracle.chisq import two_sample_test
    import numpy as np

    def tvd(a, b):
        keys = set(a) | set(b)
        ta = sum(a.values()) or 1
        tb = sum(b.values()) or 1
        return 0.5 * sum(abs(a.get(k, 0) / ta - b.get(k, 0) / tb) for k in keys)

    deltas = [0.0, 0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20, 0.30, 0.50]
    sim = build_sim(args.device)
    sim_eff = sim
    rng = np.random.default_rng(args.seed + 1)

    progs = sorted(Path(args.corpus_dir).glob("*.py"))[:args.max_programs]
    points = []
    used_stems = set()                     # programs contributing >=1 usable point
    drops = defaultdict(int)               # reason -> count (honest, auditable denominator)
    for prog in progs:
        qc0 = load_circuit(prog)
        if qc0 is None:
            drops["load_failed"] += 1
            continue
        qc0 = ensure_measured(qc0)
        qc0 = expose_rotations(qc0)        # surface rotations buried in custom gate blocks
        _, n_rot = shift_rotations(qc0, 0.0)
        if n_rot == 0:
            drops["zero_rotation_sites"] += 1
            continue
        # The source runs are delta-INDEPENDENT (same circuit, same seed every iteration):
        # compute them ONCE per program. This avoids 11x wasted simulation and stops a
        # transient source failure from desynchronizing the delta=0 type-I row.
        src_e = run_counts(sim_eff, qc0, args.effect_shots, args.seed + 1000)
        src_o = run_counts(sim, qc0, args.shots, args.seed)
        if src_e is None or src_o is None:
            drops["source_sim_failed"] += 1
            continue
        prog_points = 0
        for delta in deltas:
            fu, _ = shift_rotations(qc0, delta)
            fu_e = run_counts(sim_eff, fu, args.effect_shots, args.seed + 1000)
            fu_o = run_counts(sim, fu, args.shots, args.seed)
            if fu_e is None or fu_o is None:
                drops["followup_sim_failed"] += 1
                continue
            ok_e, _, sce, fce = canonicalize(src_e, fu_e, None)
            ok_o, reason, sco, fco = canonicalize(src_o, fu_o, None)
            if not (ok_e and ok_o):
                drops[f"canon:{reason}"] += 1
                continue
            t = tvd(sce, fce)
            stat = two_sample_test(sco, fco, args.alpha, rng)
            detected = stat.p_value < args.alpha
            points.append({"program": prog.stem, "n_rotations": n_rot,
                           "delta": round(delta, 4), "tvd": round(t, 6),
                           "detected": int(detected)})
            prog_points += 1
        if prog_points:
            used_stems.add(prog.stem)
        print(f"  {prog.stem}: {n_rot} rotations, {prog_points}/{len(deltas)} points", flush=True)

    n_prog_used = len(used_stems)          # honest: programs that actually contributed

    csv_path = out_dir / "tier3_points.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["program", "n_rotations", "delta", "tvd", "detected"])
        w.writeheader()
        w.writerows(points)

    # Auditable denominator: how many candidate programs were dropped, and why.
    drops_path = out_dir / "tier3_drops.csv"
    with drops_path.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["reason", "count"])
        w.writerow(["files_scanned", len(progs)])
        w.writerow(["programs_used", n_prog_used])
        for reason, cnt in sorted(drops.items()):
            w.writerow([reason, cnt])

    # unbiased detection-vs-TVD aggregate (NO detectability filter)
    edges = [0.0, 0.005, 0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 1.01]

    def wilson(k, n, z=1.96):
        if n == 0:
            return (0.0, 0.0, 0.0)
        p = k / n; d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
        return (p, max(0.0, c - h), min(1.0, c + h))

    print("\n" + "=" * 60)
    print(f"TIER 3: {len(points)} (program,delta) points over {n_prog_used} real programs")
    print("DETECTION vs TVD (unbiased; delta=0 row is the type-I/soundness check)")
    print("=" * 60)
    summ_path = out_dir / "tier3_detection_vs_tvd.csv"
    with summ_path.open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["tvd_lo", "tvd_hi", "detected", "n", "rate", "ci_lo", "ci_hi"])
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            sub = [p for p in points if lo <= p["tvd"] < hi]
            if not sub:
                continue
            k = sum(p["detected"] for p in sub)
            rate, clo, chi = wilson(k, len(sub))
            w.writerow([lo, hi, k, len(sub), round(rate, 4), round(clo, 4), round(chi, 4)])
            print(f"  TVD [{lo:.3f},{hi:.3f})  {k:>4}/{len(sub):<4}  {rate:.2f}  [{clo:.2f},{chi:.2f}]")
    z0 = [p for p in points if p["delta"] == 0.0]
    fp0 = sum(p["detected"] for p in z0)
    print(f"\ndelta=0 (must be ~0 false positives): {fp0}/{len(z0)} programs with an invariant row")
    if drops:
        print("dropped (auditable denominator): "
              + ", ".join(f"{r}={c}" for r, c in sorted(drops.items())))
    print(f"wrote {csv_path}, {summ_path}, and {drops_path}")


if __name__ == "__main__":
    main()
