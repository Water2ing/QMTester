"""Stage 1: normalize source circuit metadata.

We make quantum/classical registers, measurement operations, and output-bit order
explicit so that downstream relation admission and canonicalization can reason about
non-unitary boundaries (measurement, reset, classical control) precisely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from qiskit import QuantumCircuit


@dataclass
class NormalizedCircuit:
    """Canonical view of a source circuit plus the metadata QMTester needs."""

    qc: QuantumCircuit                       # circuit WITH terminal measurements
    num_qubits: int
    num_clbits: int
    # measured_qubit -> clbit it is written to (terminal measurement layer only)
    meas_map: Dict[int, int] = field(default_factory=dict)
    measured_qubits: List[int] = field(default_factory=list)
    has_midcircuit_measure: bool = False
    has_nonterminal_measure: bool = False
    has_reset: bool = False
    has_delay: bool = False
    has_conditional: bool = False            # classical-controlled ops (c_if etc.)
    has_custom_opaque: bool = False
    depth: int = 0

    @property
    def is_pure_unitary_then_measure(self) -> bool:
        """True iff the only non-unitary ops are a terminal measurement layer."""
        return not (
            self.has_midcircuit_measure
            or self.has_nonterminal_measure
            or self.has_reset
            or self.has_delay
            or self.has_conditional
        )


def _instruction_qubit_indices(qc: QuantumCircuit, qargs) -> List[int]:
    return [qc.find_bit(q).index for q in qargs]


def _instruction_clbit_indices(qc: QuantumCircuit, cargs) -> List[int]:
    return [qc.find_bit(c).index for c in cargs]


def normalize(qc: QuantumCircuit) -> NormalizedCircuit:
    """Normalize a Qiskit circuit into a :class:`NormalizedCircuit`.

    If the circuit has no measurements at all, a terminal computational-basis
    ``measure_all`` is appended (algorithm-level programs are sampled in the Z basis).
    """
    qc = qc.copy()

    has_any_measure = any(inst.operation.name == "measure" for inst in qc.data)
    if not has_any_measure:
        # Append a fresh classical register and measure every qubit in order.
        qc.measure_all(inplace=True)

    num_qubits = qc.num_qubits
    num_clbits = qc.num_clbits

    # Identify the terminal measurement layer: measurements that are not followed by
    # any further operation on their qubits. We approximate by scanning forward and
    # flagging a measurement as mid-circuit if a later instruction touches its qubit.
    data = list(qc.data)
    meas_map: Dict[int, int] = {}
    measured_qubits: List[int] = []
    has_midcircuit_measure = False
    has_nonterminal_measure = False
    has_reset = False
    has_delay = False
    has_conditional = False
    has_custom_opaque = False

    # Map: for each instruction index, the qubit indices it touches.
    touched_after: Dict[int, set] = {}
    seen_qubits: set = set()
    for i in range(len(data) - 1, -1, -1):
        inst = data[i]
        qidx = set(_instruction_qubit_indices(qc, inst.qubits))
        touched_after[i] = set(seen_qubits)
        seen_qubits |= qidx

    standard_unitary = {
        "h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "sxdg",
        "rx", "ry", "rz", "p", "u", "u1", "u2", "u3", "id",
        "cx", "cy", "cz", "ch", "crx", "cry", "crz", "cp", "cu",
        "swap", "iswap", "ccx", "cswap", "rzz", "rxx", "ryy", "rzx",
        "barrier", "measure", "reset", "delay", "global_phase",
    }

    for i, inst in enumerate(data):
        op = inst.operation
        name = op.name
        if getattr(inst.operation, "condition", None) is not None or getattr(inst, "condition", None) is not None:
            has_conditional = True
        if name == "reset":
            has_reset = True
        elif name == "delay":
            has_delay = True
        elif name == "measure":
            qidx = _instruction_qubit_indices(qc, inst.qubits)
            cidx = _instruction_clbit_indices(qc, inst.clbits)
            if any(later.operation.name not in {"measure", "barrier"} for later in data[i + 1:]):
                has_nonterminal_measure = True
            for q, c in zip(qidx, cidx):
                # mid-circuit if any later instruction touches this qubit
                if q in touched_after[i]:
                    has_midcircuit_measure = True
                else:
                    meas_map[q] = c
                    if q not in measured_qubits:
                        measured_qubits.append(q)
        elif name not in standard_unitary:
            has_custom_opaque = True

    measured_qubits.sort()

    return NormalizedCircuit(
        qc=qc,
        num_qubits=num_qubits,
        num_clbits=num_clbits,
        meas_map=meas_map,
        measured_qubits=measured_qubits,
        has_midcircuit_measure=has_midcircuit_measure,
        has_nonterminal_measure=has_nonterminal_measure,
        has_reset=has_reset,
        has_delay=has_delay,
        has_conditional=has_conditional,
        has_custom_opaque=has_custom_opaque,
        depth=qc.depth(),
    )
