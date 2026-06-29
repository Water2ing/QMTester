"""Phase-preserving rewriting (Table II, row 3).

Added or rewritten phases that are global or cancel before measurement do not change
measurement probabilities (Born rule). Examples: adding a global phase, inserting
Z-axis rotations that cancel, inserting pairs of CZ gates on qubits that are in
a product state at that point.

Preconditions (admissibility):
  - No live relative phases that depend on execution branches (no conditional ops).
  - No mid-circuit measurements that would make the phase observable.
  - Phase rewrite does not introduce interference before a measurement boundary.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from qiskit import QuantumCircuit
from qiskit.circuit.library import GlobalPhaseGate

from ..circuit_io import NormalizedCircuit
from .base import Candidate, RelationFamily, register


@register
class PhaseRewriting(RelationFamily):
    name = "phase"

    def enumerate(self, norm: NormalizedCircuit, rng) -> List[Candidate]:
        cands: List[Candidate] = []
        qubits = norm.measured_qubits or list(range(norm.num_qubits))
        # Global phase addition: e^{i*theta} * I — never changes any measurement outcome.
        for theta_frac in [0.25, 0.5, 1.0]:
            theta = theta_frac * math.pi
            cands.append(Candidate(
                family=self.name,
                name=f"global_phase({theta:.3f})",
                params={"kind": "global_phase", "theta": theta},
                canon_map=None,
            ))
        # Rz(2pi) on single qubits = global phase on that qubit subspace, cancels.
        for q in qubits[:min(3, len(qubits))]:
            cands.append(Candidate(
                family=self.name,
                name=f"rz_2pi@q{q}",
                params={"kind": "rz_2pi", "qubit": q},
                canon_map=None,
            ))
        # Z gate pair: Z^2 = I (same as identity insertion, but framed as phase).
        for q in qubits[:min(2, len(qubits))]:
            cands.append(Candidate(
                family=self.name,
                name=f"z_pair@q{q}",
                params={"kind": "z_pair", "qubit": q},
                canon_map=None,
            ))
        return cands

    def admissible(self, norm: NormalizedCircuit, cand: Candidate) -> Tuple[bool, str]:
        # Phase rewrites are invalid when phases are observable (mid-circuit measurement,
        # conditional on classical register, or interference-sensitive decompositions).
        if norm.has_midcircuit_measure:
            return False, "PHASE:mid_circuit_measurement_makes_phase_observable"
        if norm.has_nonterminal_measure:
            return False, "PHASE:nonterminal_measurement_makes_phase_observable"
        if norm.has_conditional:
            return False, "PHASE:conditional_op_makes_relative_phase_live"
        if norm.has_reset:
            return False, "PHASE:reset_may_disturb_phase_cancellation"
        if norm.has_delay:
            return False, "PHASE:delay_may_disturb_phase_cancellation"
        return True, "OK"

    def apply(self, norm: NormalizedCircuit, cand: Candidate) -> QuantumCircuit:
        kind = cand.params["kind"]
        src = norm.qc
        out = QuantumCircuit(*src.qregs, *src.cregs)
        # Copy unitary prefix; measures stay at the end.
        measures = []
        for inst in src.data:
            if inst.operation.name == "measure":
                measures.append(inst)
            else:
                out.append(inst.operation, inst.qubits, inst.clbits)
        if kind == "global_phase":
            theta = cand.params["theta"]
            out.global_phase += theta
        elif kind == "rz_2pi":
            q = cand.params["qubit"]
            out.rz(2 * math.pi, q)
        elif kind == "z_pair":
            q = cand.params["qubit"]
            out.z(q)
            out.z(q)
        for m in measures:
            out.append(m.operation, m.qubits, m.clbits)
        return out
