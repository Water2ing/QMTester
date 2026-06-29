"""Small program-level subjects for smoke tests and positive controls."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional

from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

from .program_subject import ProgramRelationCandidate


@dataclass
class PermutationParitySubject:
    subject_id: str = "program_perm_parity"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "input_permutation"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None
    buggy_ignore_order: bool = False

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_input_permutation"]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        bits = list(input_spec.get("bits", [1, 0, 1, 0]))
        order = list(input_spec.get("qubit_order", range(len(bits))))
        if self.buggy_ignore_order:
            order = list(range(len(bits)))
        qc = QuantumCircuit(len(bits), len(bits))
        for logical, bit in enumerate(bits):
            if bit:
                qc.x(order[logical])
        for physical in range(len(bits)):
            qc.measure(physical, physical)
        return qc

    def enumerate_input_permutation(self, rng) -> List[ProgramRelationCandidate]:
        bits = [1, 0, 1, 1]
        perm = [1, 3, 0, 2]
        inv = [0] * len(perm)
        for logical, physical in enumerate(perm):
            inv[physical] = logical
        return [ProgramRelationCandidate(
            family="program_input_permutation",
            name="qubit_order_covariance",
            source_input={"bits": bits, "qubit_order": list(range(len(bits)))},
            followup_input={"bits": bits, "qubit_order": perm},
            canon_map=inv,
            metadata={"perm": perm},
        )]


@dataclass
class RotationPeriodicitySubject:
    subject_id: str = "program_rotation_periodicity"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "parameter_periodicity"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None
    buggy_halve_angle: bool = False

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_parameter_periodicity"]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        theta = float(input_spec.get("theta", 0.7))
        if self.buggy_halve_angle:
            theta /= 2.0
        qc = QuantumCircuit(1, 1)
        qc.ry(theta, 0)
        qc.measure(0, 0)
        return qc

    def enumerate_parameter_periodicity(self, rng) -> List[ProgramRelationCandidate]:
        theta = 0.73
        return [ProgramRelationCandidate(
            family="program_parameter_periodicity",
            name="ry_theta_plus_2pi",
            source_input={"theta": theta},
            followup_input={"theta": theta + 2 * math.pi},
        )]


@dataclass
class QFTRoundTripSubject:
    subject_id: str = "program_qft_round_trip"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "qft_round_trip"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None
    buggy_omit_inverse: bool = False

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_qft_round_trip"]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        bits = list(input_spec.get("bits", [1, 0, 1]))
        use_round_trip = bool(input_spec.get("round_trip", False))
        qc = QuantumCircuit(len(bits), len(bits))
        for q, bit in enumerate(bits):
            if bit:
                qc.x(q)
        if use_round_trip:
            qft = QFT(len(bits), do_swaps=True).to_gate()
            qc.append(qft, range(len(bits)))
            if not self.buggy_omit_inverse:
                qc.append(qft.inverse(), range(len(bits)))
        qc.measure(range(len(bits)), range(len(bits)))
        return qc

    def enumerate_qft_round_trip(self, rng) -> List[ProgramRelationCandidate]:
        bits = [1, 0, 1]
        return [ProgramRelationCandidate(
            family="program_qft_round_trip",
            name="qft_iqft_identity",
            source_input={"bits": bits, "round_trip": False},
            followup_input={"bits": bits, "round_trip": True},
        )]
