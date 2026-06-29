"""Identity insertion (Table II, row 1).

Insert a unitary gate and its inverse at a position where no non-unitary boundary
(measurement, reset, classical control) is crossed. Output distribution is unchanged;
canonicalization map is the identity.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from qiskit import QuantumCircuit

from ..circuit_io import NormalizedCircuit
from .base import Candidate, RelationFamily, register


@register
class IdentityInsertion(RelationFamily):
    name = "identity"

    # (gate name, builder applied to (qc, qubit), inverse builder)
    _SINGLE = ["h", "x", "z", "y", "s", "t", "sx"]

    def enumerate(self, norm: NormalizedCircuit, rng) -> List[Candidate]:
        cands: List[Candidate] = []
        qubits = norm.measured_qubits or list(range(norm.num_qubits))
        # A handful of fixed-gate insertions plus a couple of seeded rotation insertions.
        chosen = list(self._SINGLE)
        for gate in chosen:
            for q in qubits:
                cands.append(Candidate(
                    family=self.name,
                    name=f"insert_{gate}_inv@q{q}",
                    params={"gate": gate, "qubit": q},
                    canon_map=None,
                ))
        # Seeded parametric rotation + inverse (Rz/Rx/Ry theta, -theta).
        for axis in ("rz", "rx", "ry"):
            for q in qubits[: min(3, len(qubits))]:
                theta = float(rng.uniform(0.1, math.pi - 0.1))
                cands.append(Candidate(
                    family=self.name,
                    name=f"insert_{axis}({theta:.3f})_inv@q{q}",
                    params={"gate": axis, "qubit": q, "theta": theta},
                    canon_map=None,
                ))
        return cands

    def admissible(self, norm: NormalizedCircuit, cand: Candidate) -> Tuple[bool, str]:
        q = cand.params["qubit"]
        # Precondition: gate+inverse supported on selected qubit; insertion site (just
        # before the terminal measurement) must not cross measurement/reset/conditional.
        if norm.has_midcircuit_measure:
            return False, "INV:mid_circuit_measurement_boundary"
        if norm.has_nonterminal_measure:
            return False, "INV:nonterminal_measurement_boundary"
        if norm.has_reset:
            return False, "INV:reset_boundary"
        if norm.has_delay:
            return False, "INV:delay_boundary"
        if norm.has_conditional:
            return False, "INV:classical_control_boundary"
        if q not in norm.meas_map:
            return False, "INV:qubit_not_measured_no_observable_effect"
        return True, "OK"

    def apply(self, norm: NormalizedCircuit, cand: Candidate) -> QuantumCircuit:
        gate = cand.params["gate"]
        q = cand.params["qubit"]
        theta = cand.params.get("theta")
        # Rebuild the circuit, inserting gate+inverse immediately before the terminal
        # measurement on qubit q (i.e. at the end of the unitary part).
        src = norm.qc
        out = QuantumCircuit(*src.qregs, *src.cregs)
        # Split source into unitary prefix and terminal measurement layer.
        measures = []
        for inst in src.data:
            if inst.operation.name == "measure":
                measures.append(inst)
            else:
                out.append(inst.operation, inst.qubits, inst.clbits)
        # Insert gate then inverse on qubit q.
        self._apply_gate(out, gate, q, theta, inverse=False)
        self._apply_gate(out, gate, q, theta, inverse=True)
        for m in measures:
            out.append(m.operation, m.qubits, m.clbits)
        return out

    @staticmethod
    def _apply_gate(qc: QuantumCircuit, gate: str, q: int, theta, inverse: bool):
        if gate in ("rz", "rx", "ry"):
            ang = -theta if inverse else theta
            getattr(qc, gate)(ang, q)
            return
        # Self-inverse gates (h,x,y,z) repeat; s/t/sx use the dagger on inverse.
        if gate in ("h", "x", "y", "z"):
            getattr(qc, gate)(q)
        elif gate == "s":
            (qc.sdg if inverse else qc.s)(q)
        elif gate == "t":
            (qc.tdg if inverse else qc.t)(q)
        elif gate == "sx":
            (qc.sxdg if inverse else qc.sx)(q)
        else:  # pragma: no cover - guarded by enumerate
            raise ValueError(f"unknown identity gate {gate}")
