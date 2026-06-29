"""Builder-level program mutation cases and manifest serialization."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

from .bugs4q_program_subjects import Bugs4QMeasurementOrderSubject
from .program_subject import ProgramRelationCandidate


FAMILY_TARGET_COUNTS = {
    "program_input_permutation": 20,
    "program_classical_remap": 20,
    "program_qft_round_trip": 20,
    "program_parameter_periodicity": 20,
    "program_ancilla_uncompute": 20,
}


@dataclass
class ProgramMutationCase:
    mutant_id: str
    source_id: str
    operator: str
    relation_family: str
    fixed_subject: Any
    mutant_subject: Any
    fixed_subject_spec: Dict[str, Any]
    mutant_subject_spec: Dict[str, Any]
    site: str
    seed: int
    expected_detected: bool = True
    effect_tvd: Optional[float] = None
    source_path: str = ""
    fixed_path: str = ""

    def manifest_row(self) -> Dict[str, Any]:
        return {
            "mutant_id": self.mutant_id,
            "source_id": self.source_id,
            "relation_family": self.relation_family,
            "operator": self.operator,
            "site": self.site,
            "seed": self.seed,
            "fixed_subject": json.dumps(self.fixed_subject_spec, sort_keys=True),
            "mutant_subject": json.dumps(self.mutant_subject_spec, sort_keys=True),
            "effect_tvd": "" if self.effect_tvd is None else f"{self.effect_tvd:.8f}",
            "expected_detected": str(self.expected_detected).lower(),
            "source_path": self.source_path,
            "fixed_path": self.fixed_path,
        }


class ParamInputPermutationSubject:
    canonicalizer = None
    bug_category = "input_permutation"
    source_path = None
    fixed_path = None

    def __init__(self, case_id: str, bits: List[int], perm: List[int], buggy: bool = False):
        self.subject_id = f"pm_perm_{case_id}"
        self.relations = ["program_input_permutation"]
        self.bits = bits
        self.perm = perm
        self.buggy = buggy

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        bits = list(input_spec.get("bits", self.bits))
        order = list(input_spec.get("qubit_order", range(len(bits))))
        if self.buggy:
            order = list(range(len(bits)))
        qc = QuantumCircuit(len(bits), len(bits))
        for logical, bit in enumerate(bits):
            if bit:
                qc.x(order[logical])
        qc.measure(range(len(bits)), range(len(bits)))
        return qc

    def enumerate_input_permutation(self, rng) -> List[ProgramRelationCandidate]:
        canon_map = [0] * len(self.perm)
        for followup_physical, _ in enumerate(self.perm):
            logical = self.perm.index(followup_physical)
            canon_map[followup_physical] = logical
        return [ProgramRelationCandidate(
            family="program_input_permutation",
            name=f"{self.subject_id}_covariance",
            source_input={"bits": self.bits, "qubit_order": list(range(len(self.bits)))},
            followup_input={"bits": self.bits, "qubit_order": self.perm},
            canon_map=canon_map,
            metadata={"perm": self.perm},
        )]


class ParamClassicalRemapSubject:
    canonicalizer = None
    bug_category = "classical_remap"
    source_path = None
    fixed_path = None

    def __init__(self, case_id: str, bits: List[int], measure_qubits: List[int], buggy: bool = False):
        self.subject_id = f"pm_cremap_{case_id}"
        self.relations = ["program_classical_remap"]
        self.bits = bits
        self.measure_qubits = measure_qubits
        self.buggy = buggy

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        bits = list(input_spec.get("bits", self.bits))
        measure_qubits = list(input_spec.get("measure_qubits", range(len(bits))))
        requested_clbits = list(input_spec.get("measure_clbits", range(len(bits))))
        qc = QuantumCircuit(len(bits), len(bits))
        for qubit, bit in enumerate(bits):
            if bit:
                qc.x(qubit)
        measure_clbits = measure_qubits if self.buggy else requested_clbits
        qc.measure(measure_qubits, measure_clbits)
        return qc

    def enumerate_classical_remap(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_classical_remap",
            name=f"{self.subject_id}_measurement_remap",
            source_input={
                "bits": self.bits,
                "measure_qubits": list(range(len(self.bits))),
                "measure_clbits": list(range(len(self.bits))),
            },
            followup_input={
                "bits": self.bits,
                "measure_qubits": self.measure_qubits,
                "measure_clbits": list(range(len(self.bits))),
            },
            canon_map=self.measure_qubits,
            metadata={"measure_qubits": self.measure_qubits},
        )]


class ParamQFTRoundTripSubject:
    canonicalizer = None
    bug_category = "qft_round_trip"
    source_path = None
    fixed_path = None

    def __init__(self, case_id: str, bits: List[int], buggy: bool = False):
        self.subject_id = f"pm_qft_{case_id}"
        self.relations = ["program_qft_round_trip"]
        self.bits = bits
        self.buggy = buggy

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        bits = list(input_spec.get("bits", self.bits))
        round_trip = bool(input_spec.get("round_trip", False))
        qc = QuantumCircuit(len(bits), len(bits))
        for qubit, bit in enumerate(bits):
            if bit:
                qc.x(qubit)
        if round_trip:
            qft = QFT(len(bits), do_swaps=True).to_gate()
            qc.append(qft, range(len(bits)))
            if not self.buggy:
                qc.append(qft.inverse(), range(len(bits)))
        qc.measure(range(len(bits)), range(len(bits)))
        return qc

    def enumerate_qft_round_trip(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_qft_round_trip",
            name=f"{self.subject_id}_qft_iqft",
            source_input={"bits": self.bits, "round_trip": False},
            followup_input={"bits": self.bits, "round_trip": True},
            metadata={"bits": self.bits},
        )]


class ParamRotationPeriodicitySubject:
    canonicalizer = None
    bug_category = "parameter_periodicity"
    source_path = None
    fixed_path = None

    def __init__(self, case_id: str, theta: float, axis: str = "ry", buggy: bool = False):
        self.subject_id = f"pm_rot_{case_id}"
        self.relations = ["program_parameter_periodicity"]
        self.theta = theta
        self.axis = axis
        self.buggy = buggy

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        theta = float(input_spec.get("theta", self.theta))
        if self.buggy:
            theta /= 2.0
        qc = QuantumCircuit(1, 1)
        getattr(qc, self.axis)(theta, 0)
        qc.measure(0, 0)
        return qc

    def enumerate_parameter_periodicity(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_parameter_periodicity",
            name=f"{self.subject_id}_{self.axis}_plus_2pi",
            source_input={"theta": self.theta},
            followup_input={"theta": self.theta + 2 * math.pi},
            metadata={"axis": self.axis},
        )]


class ParamRotationDriftSubject:
    canonicalizer = None
    bug_category = "parameter_periodicity_hard"
    source_path = None
    fixed_path = None

    def __init__(self, case_id: str, theta: float, drift: float, axis: str = "ry", buggy: bool = False):
        self.subject_id = f"ph_rot_{case_id}"
        self.relations = ["program_parameter_periodicity"]
        self.theta = theta
        self.drift = drift
        self.axis = axis
        self.buggy = buggy

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        theta = float(input_spec.get("theta", self.theta))
        if self.buggy and theta > math.tau:
            # A subtle periodicity bug: the follow-up angle near theta+2pi
            # receives a small extra calibration drift while the source angle
            # does not.  This keeps the effect measurable but much smaller than
            # the main positive-control mutants.
            theta += self.drift
        qc = QuantumCircuit(1, 1)
        getattr(qc, self.axis)(theta, 0)
        qc.measure(0, 0)
        return qc

    def enumerate_parameter_periodicity(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_parameter_periodicity",
            name=f"{self.subject_id}_{self.axis}_plus_2pi_drift",
            source_input={"theta": self.theta},
            followup_input={"theta": self.theta + math.tau},
            metadata={"axis": self.axis, "drift": self.drift},
        )]


class ParamAncillaResetSubject:
    canonicalizer = None
    bug_category = "ancilla_uncompute"
    source_path = None
    fixed_path = None

    def __init__(self, case_id: str, controls: List[int], target: int, bits: List[int], buggy: bool = False):
        self.subject_id = f"pm_ancilla_{case_id}"
        self.relations = ["program_ancilla_uncompute"]
        self.controls = controls
        self.target = target
        self.bits = bits
        self.buggy = buggy

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        bits = list(input_spec.get("bits", self.bits))
        use_ancilla = bool(input_spec.get("use_ancilla", False))
        controls = list(input_spec.get("controls", self.controls))
        target = int(input_spec.get("target", self.target))
        ancilla = 3
        qc = QuantumCircuit(4, 3)
        for qubit, bit in enumerate(bits[:3]):
            if bit:
                qc.x(qubit)
        if not use_ancilla:
            qc.ccx(controls[0], controls[1], target)
        else:
            qc.ccx(controls[0], controls[1], ancilla)
            if self.buggy:
                qc.reset(ancilla)
            qc.cx(ancilla, target)
            qc.ccx(controls[0], controls[1], ancilla)
        qc.measure([0, 1, 2], [0, 1, 2])
        return qc

    def enumerate_ancilla_uncompute(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_ancilla_uncompute",
            name=f"{self.subject_id}_scratch_equivalence",
            source_input={
                "bits": self.bits,
                "controls": self.controls,
                "target": self.target,
                "use_ancilla": False,
            },
            followup_input={
                "bits": self.bits,
                "controls": self.controls,
                "target": self.target,
                "use_ancilla": True,
            },
            metadata={"controls": self.controls, "target": self.target},
        )]


SUBJECT_TYPES = {
    "input_permutation": ParamInputPermutationSubject,
    "classical_remap": ParamClassicalRemapSubject,
    "qft_round_trip": ParamQFTRoundTripSubject,
    "rotation_periodicity": ParamRotationPeriodicitySubject,
    "rotation_drift": ParamRotationDriftSubject,
    "ancilla_reset": ParamAncillaResetSubject,
    "bugs4q_measurement_order": Bugs4QMeasurementOrderSubject,
}


def subject_from_spec(root: Path, spec: Dict[str, Any]):
    kind = spec["kind"]
    kwargs = dict(spec.get("kwargs", {}))
    if kind == "bugs4q_measurement_order":
        kwargs["root"] = root
    return SUBJECT_TYPES[kind](**kwargs)


def _spec(kind: str, **kwargs: Any) -> Dict[str, Any]:
    return {"kind": kind, "kwargs": kwargs}


def _case(
    mutant_id: str,
    source_id: str,
    relation_family: str,
    operator: str,
    site: str,
    seed: int,
    fixed_spec: Dict[str, Any],
    mutant_spec: Dict[str, Any],
    root: Path,
    source_path: str = "",
    fixed_path: str = "",
) -> ProgramMutationCase:
    return ProgramMutationCase(
        mutant_id=mutant_id,
        source_id=source_id,
        relation_family=relation_family,
        operator=operator,
        site=site,
        seed=seed,
        fixed_subject=subject_from_spec(root, fixed_spec),
        mutant_subject=subject_from_spec(root, mutant_spec),
        fixed_subject_spec=fixed_spec,
        mutant_subject_spec=mutant_spec,
        source_path=source_path,
        fixed_path=fixed_path,
    )


def generate_program_mutation_cases(root: Path, seed: int = 20240519) -> List[ProgramMutationCase]:
    """Generate the balanced 100-case builder-level mutation suite."""
    root = Path(root)
    cases: List[ProgramMutationCase] = []

    perms = [
        [1, 3, 0, 2],
        [2, 0, 3, 1],
        [3, 2, 1, 0],
        [1, 0, 3, 2],
    ]
    for i in range(20):
        bits = [1, 0, 0, 0]
        perm = perms[i % len(perms)]
        case_id = f"{i:02d}"
        fixed = _spec("input_permutation", case_id=case_id, bits=bits, perm=perm, buggy=False)
        mutant = _spec("input_permutation", case_id=case_id, bits=bits, perm=perm, buggy=True)
        cases.append(_case(
            f"pm_perm_{case_id}", "program_perm_parity", "program_input_permutation",
            "builder_ignores_qubit_order", f"perm={perm}", seed + i, fixed, mutant, root,
        ))

    measure_orders = [
        [1, 0, 2],
        [2, 1, 0],
        [0, 2, 1],
        [1, 2, 0],
    ]
    cremap_bits_by_order = {
        (1, 0, 2): [1, 0, 1],
        (2, 1, 0): [1, 0, 0],
        (0, 2, 1): [1, 0, 1],
        (1, 2, 0): [1, 0, 0],
    }
    for i in range(20):
        measure_qubits = measure_orders[i % len(measure_orders)]
        bits = cremap_bits_by_order[tuple(measure_qubits)]
        case_id = f"{i:02d}"
        fixed = _spec("classical_remap", case_id=case_id, bits=bits,
                      measure_qubits=measure_qubits, buggy=False)
        mutant = _spec("classical_remap", case_id=case_id, bits=bits,
                       measure_qubits=measure_qubits, buggy=True)
        cases.append(_case(
            f"pm_cremap_{case_id}", "program_classical_remap", "program_classical_remap",
            "builder_wrong_measurement_map", f"measure_qubits={measure_qubits}",
            seed + 100 + i, fixed, mutant, root,
        ))

    qft_bits = [
        [1, 0],
        [0, 1],
        [1, 1],
        [1, 0, 1],
        [0, 1, 1],
        [1, 1, 0],
        [1, 0, 0],
        [0, 0, 1],
        [1, 1, 1],
        [1, 0, 1, 1],
    ]
    for i in range(20):
        bits = qft_bits[i % len(qft_bits)]
        case_id = f"{i:02d}"
        fixed = _spec("qft_round_trip", case_id=case_id, bits=bits, buggy=False)
        mutant = _spec("qft_round_trip", case_id=case_id, bits=bits, buggy=True)
        cases.append(_case(
            f"pm_qft_{case_id}", "program_qft_round_trip", "program_qft_round_trip",
            "builder_omits_inverse_qft", f"bits={bits}", seed + 200 + i, fixed, mutant, root,
        ))

    axes = ["ry", "rx"]
    for i in range(20):
        theta = 0.37 + 0.11 * i
        axis = axes[i % len(axes)]
        case_id = f"{i:02d}"
        fixed = _spec("rotation_periodicity", case_id=case_id, theta=theta, axis=axis, buggy=False)
        mutant = _spec("rotation_periodicity", case_id=case_id, theta=theta, axis=axis, buggy=True)
        cases.append(_case(
            f"pm_rot_{case_id}", "program_rotation_periodicity", "program_parameter_periodicity",
            "builder_scales_rotation_angle", f"{axis}@theta={theta:.3f}",
            seed + 300 + i, fixed, mutant, root,
        ))

    ancilla_specs = [
        ([0, 1], 2, [1, 1, 0]),
        ([0, 2], 1, [1, 0, 1]),
        ([1, 2], 0, [0, 1, 1]),
        ([0, 1], 2, [1, 1, 1]),
        ([0, 2], 1, [1, 1, 1]),
    ]
    for i in range(20):
        controls, target, bits = ancilla_specs[i % len(ancilla_specs)]
        case_id = f"{i:02d}"
        fixed = _spec("ancilla_reset", case_id=case_id, controls=controls,
                      target=target, bits=bits, buggy=False)
        mutant = _spec("ancilla_reset", case_id=case_id, controls=controls,
                       target=target, bits=bits, buggy=True)
        cases.append(_case(
            f"pm_ancilla_{case_id}", "program_ancilla_reset", "program_ancilla_uncompute",
            "builder_resets_scratch_before_use", f"controls={controls};target={target}",
            seed + 400 + i, fixed, mutant, root,
        ))

    return cases


def generate_hard_program_mutation_cases(root: Path, seed: int = 20240519) -> List[ProgramMutationCase]:
    """Generate a supplemental lower-effect program mutant suite.

    The main 100-case suite is a balanced positive-control benchmark.  This
    supplemental suite intentionally focuses on a subtler parameter-periodicity
    failure mode with target TVD in roughly the 0.02-0.20 range.
    """
    root = Path(root)
    cases: List[ProgramMutationCase] = []
    axes = ["ry", "rx"]
    for i in range(20):
        theta = 1.10 + 0.025 * (i % 8)
        drift = 0.055 + 0.005 * (i % 5)
        axis = axes[i % len(axes)]
        case_id = f"{i:02d}"
        fixed = _spec("rotation_drift", case_id=case_id, theta=theta,
                      drift=drift, axis=axis, buggy=False)
        mutant = _spec("rotation_drift", case_id=case_id, theta=theta,
                       drift=drift, axis=axis, buggy=True)
        cases.append(_case(
            f"ph_rot_{case_id}",
            "program_rotation_periodicity_hard",
            "program_parameter_periodicity",
            "builder_adds_small_followup_angle_drift",
            f"{axis}@theta={theta:.3f};drift={drift:.3f}",
            seed + 700 + i,
            fixed,
            mutant,
            root,
        ))
    return cases


def load_program_mutation_cases(root: Path, manifest_path: Optional[Path] = None) -> List[ProgramMutationCase]:
    root = Path(root)
    if manifest_path is None:
        manifest_path = root / "data" / "manifests" / "program_mutants_manifest.csv"
    if not manifest_path.exists():
        return generate_program_mutation_cases(root)

    cases = []
    with manifest_path.open(newline="") as f:
        for row in csv.DictReader(f):
            fixed_spec = json.loads(row["fixed_subject"])
            mutant_spec = json.loads(row["mutant_subject"])
            case = _case(
                row["mutant_id"],
                row["source_id"],
                row["relation_family"],
                row["operator"],
                row["site"],
                int(row["seed"]),
                fixed_spec,
                mutant_spec,
                root,
                source_path=row.get("source_path", ""),
                fixed_path=row.get("fixed_path", ""),
            )
            if row.get("effect_tvd"):
                case.effect_tvd = float(row["effect_tvd"])
            case.expected_detected = row.get("expected_detected", "true") == "true"
            cases.append(case)
    return cases
