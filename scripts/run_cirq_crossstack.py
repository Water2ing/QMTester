"""Cross-stack replication of QMTester's relation logic on Cirq.

QMTester's relation logic---rebuild from a follow-up input, canonicalize the count
vectors through the documented bijection, two-sample test---is stack-agnostic: only
circuit construction and execution are Qiskit-specific. This script re-implements two
real subjects' builders in Cirq, executes on Cirq's simulator, and feeds the counts to
the same canonicalization (canonicalize) and oracle (two_sample_test) used for Qiskit,
checking that the buggy variant is detected and the fixed variant stays clean on Cirq.

Subjects: ccx_role (program_input_permutation, structurally builder-only) and
measurement-order/endianness (program_classical_remap).

Usage:  .venv_cirq/Scripts/python scripts/run_cirq_crossstack.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import cirq

ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT / "artifact"))
from qmtester.canonicalize import canonicalize          # qiskit-free
from qmtester.oracle.chisq import two_sample_test        # qiskit-free


def counts_from_cirq(circuit, shots, seed):
    """Run a Cirq circuit (one measurement key 'm' over all qubits) -> {bitstring: count}."""
    res = cirq.Simulator(seed=seed).run(circuit, repetitions=shots)
    arr = res.measurements["m"]  # (shots, n), qubit order = measure order
    out = {}
    for row in arr:
        key = "".join(str(int(b)) for b in row)
        out[key] = out.get(key, 0) + 1
    return out


# ---- ccx_role (program_input_permutation): buggy hard-codes ccx(0,1,2) ----
def build_ccx_role(roles, bits, variant):
    q = cirq.LineQubit.range(3)
    ops = []
    for logical, bit in enumerate(bits):
        if bit:
            ops.append(cirq.X(q[roles[logical]]))
    if variant == "buggy":
        ops.append(cirq.CCX(q[0], q[1], q[2]))        # hard-coded, ignores roles
    else:
        ops.append(cirq.CCX(q[roles[0]], q[roles[1]], q[roles[2]]))  # role-covariant
    ops.append(cirq.measure(*q, key="m"))
    return cirq.Circuit(ops)


def ccx_role_candidate():
    perm = [2, 1, 0]
    canon_map = [perm.index(i) for i in range(3)]  # follow-up clbit i -> source clbit
    return dict(name="ccx_role_covariance",
                source=dict(roles=[0, 1, 2], bits=[1, 1, 0]),
                followup=dict(roles=perm, bits=[1, 1, 0]),
                canon_map=canon_map, build=build_ccx_role)


# ---- measurement-order / endianness (program_classical_remap) ----
def build_remap(order, variant):
    # prepare an asymmetric basis state |1 0 0> (not reversal-palindromic), read out under `order`.
    q = cirq.LineQubit.range(3)
    ops = [cirq.X(q[0])]
    if variant == "buggy":
        read = [0, 1, 2]                       # buggy: ignores the requested order
    else:
        read = order                           # fixed: honours the readout order
    ops.append(cirq.measure(*[q[i] for i in read], key="m"))
    return cirq.Circuit(ops)


def remap_candidate():
    order = [2, 1, 0]                           # reversed endianness
    canon_map = [order.index(i) for i in range(3)]
    return dict(name="endianness_remap",
                source=dict(order=[0, 1, 2]),
                followup=dict(order=order),
                canon_map=canon_map, build=build_remap)


def run(label, cand, shots=4096, seed=20240519, alpha=0.05):
    rng = np.random.default_rng(seed + 1)
    print(f"\n=== {label} (Cirq) ===")
    for variant in ("buggy", "fixed"):
        src = counts_from_cirq(cand["build"](variant=variant, **cand["source"]), shots, seed)
        fu = counts_from_cirq(cand["build"](variant=variant, **cand["followup"]), shots, seed)
        ok, reason, sc, fc = canonicalize(src, fu, cand["canon_map"])
        if not ok:
            print(f"  {variant}: canonicalization rejected ({reason})"); continue
        stat = two_sample_test(sc, fc, alpha, rng)
        detected = stat.p_value < alpha
        tag = "DET" if detected else "clean"
        print(f"  {variant:5}: p={stat.p_value:.4g}  -> {tag}"
              + ("   <-- FALSE POSITIVE" if (variant == "fixed" and detected) else ""))


def main():
    print("Cirq", cirq.__version__, "| reusing Qiskit-side canonicalize + two_sample_test")
    run("ccx_role / input_permutation", ccx_role_candidate())
    run("endianness / classical_remap", remap_candidate())
    print("\nIf buggy=DET and fixed=clean on Cirq, the relations transfer beyond Qiskit.")


if __name__ == "__main__":
    main()
