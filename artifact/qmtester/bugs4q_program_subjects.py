"""Hand-audited Bugs4Q program-level subjects.

These adapters are intentionally small and explicit.  A Bugs4Q script is only
promoted from circuit-level to program-level evaluation when the benchmark bug
has a clear builder/input semantics that supports an auditable metamorphic
relation.  Everything else stays in the circuit-level artifact path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit.library import QFT

from .program_subject import ProgramRelationCandidate


def _bugs4q_path(root: Path, rel: str) -> Path:
    return root / "vendor" / "bugs4q" / rel


@dataclass
class Bugs4QMeasurementOrderSubject:
    """Bugs4Q Aer/bug_7: measurement order must be classically remappable."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_github_17_program_measurement_order"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "Order during measurement"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_classical_remap"]
        self.source_path = _bugs4q_path(self.root, "Aer/bug_7/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "Aer/bug_7/fixed.py")

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        n = int(input_spec.get("n", 3))
        x_qubit = int(input_spec.get("x_qubit", 0))
        measure_qubits = list(input_spec.get("measure_qubits", range(n)))
        requested_clbits = list(input_spec.get("measure_clbits", range(n)))

        q = QuantumRegister(n, "q")
        c = ClassicalRegister(n, "c")
        qc = QuantumCircuit(q, c, name=f"{self.subject_id}_{self.variant}")
        qc.x(q[x_qubit])

        if self.variant == "buggy" and measure_qubits == [1, 0, 2]:
            # Mirrors vendor/bugs4q/Aer/bug_7/buggy.py:
            # qc.measure([1, 0, 2], [1, 0, 2])
            measure_clbits = measure_qubits
        else:
            # Mirrors fixed.py and the intended builder contract: callers choose
            # which classical positions receive each measurement.
            measure_clbits = requested_clbits
        qc.measure([q[i] for i in measure_qubits], [c[i] for i in measure_clbits])
        return qc

    def enumerate_classical_remap(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_classical_remap",
            name="measurement_order_covariance",
            source_input={
                "n": 3,
                "x_qubit": 0,
                "measure_qubits": [0, 1, 2],
                "measure_clbits": [0, 1, 2],
            },
            followup_input={
                "n": 3,
                "x_qubit": 0,
                "measure_qubits": [1, 0, 2],
                "measure_clbits": [0, 1, 2],
            },
            canon_map=[1, 0, 2],
            metadata={
                "bugs4q_buggy": "Aer/bug_7/buggy.py",
                "bugs4q_fixed": "Aer/bug_7/fixed.py",
            },
        )]


@dataclass
class Bugs4QCCXRoleSubject:
    """Bugs4Q stackoverflow-6-10/bug_1: CCX roles must covary with qubit layout."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_stackoverflow_5_program_ccx_role"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "Label convention is reversed"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_input_permutation"]
        self.source_path = _bugs4q_path(self.root, "stackoverflow-6-10/bug_1/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "stackoverflow-6-10/bug_1/fixed.py")

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        roles = list(input_spec.get("roles", [0, 1, 2]))
        bits = list(input_spec.get("bits", [1, 1, 0]))
        qc = QuantumCircuit(3, 3, name=f"{self.subject_id}_{self.variant}")
        for logical, bit in enumerate(bits):
            if bit:
                qc.x(roles[logical])
        if self.variant == "buggy":
            # Mirrors the buggy script's hard-coded ccx(0, 1, 2): it ignores
            # the logical control/target role mapping requested by the builder.
            qc.ccx(0, 1, 2)
        else:
            # Mirrors the fixed script's role-correct ccx(2, 1, 0) behavior.
            qc.ccx(roles[0], roles[1], roles[2])
        qc.measure(range(3), range(3))
        return qc

    def enumerate_input_permutation(self, rng) -> List[ProgramRelationCandidate]:
        perm = [2, 1, 0]
        canon_map = [0] * len(perm)
        for followup_physical in range(len(perm)):
            logical = perm.index(followup_physical)
            canon_map[followup_physical] = logical
        return [ProgramRelationCandidate(
            family="program_input_permutation",
            name="ccx_role_covariance",
            source_input={"roles": [0, 1, 2], "bits": [1, 1, 0]},
            followup_input={"roles": perm, "bits": [1, 1, 0]},
            canon_map=canon_map,
            metadata={
                "bugs4q_buggy": "stackoverflow-6-10/bug_1/buggy.py",
                "bugs4q_fixed": "stackoverflow-6-10/bug_1/fixed.py",
            },
        )]


@dataclass
class Bugs4QTeleportationFeedbackSubject:
    """Bugs4Q stackoverflow-1-5/1: teleportation must preserve input state."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_stackoverflow_1_program_teleport_feedback"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "Output Wrong"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_ancilla_uncompute"]
        self.source_path = _bugs4q_path(self.root, "stackoverflow-1-5/1/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "stackoverflow-1-5/1/Fix.py")

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        theta = float(input_spec.get("theta", 1.1))
        mode = str(input_spec.get("mode", "direct"))
        if mode == "direct":
            qc = QuantumCircuit(1, 1, name=f"{self.subject_id}_{self.variant}_direct")
            qc.ry(theta, 0)
            qc.measure(0, 0)
            return qc

        qc = QuantumCircuit(3, 1, name=f"{self.subject_id}_{self.variant}_teleport")
        qc.ry(theta, 0)
        qc.h(1)
        qc.cx(1, 2)
        qc.cx(0, 1)
        qc.h(0)
        if self.variant == "fixed":
            # Coherent deferred-measurement form of the classical correction in
            # the fixed script.  It avoids dynamic-circuit backend differences.
            qc.cx(1, 2)
            qc.cz(0, 2)
        else:
            # The buggy script performs feedback incorrectly; at the builder
            # level this is modeled as dropping the required correction.
            pass
        qc.measure(2, 0)
        return qc

    def enumerate_ancilla_uncompute(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_ancilla_uncompute",
            name="teleportation_preserves_input_distribution",
            source_input={"mode": "direct", "theta": 1.1},
            followup_input={"mode": "teleport", "theta": 1.1},
            metadata={
                "bugs4q_buggy": "stackoverflow-1-5/1/buggy.py",
                "bugs4q_fixed": "stackoverflow-1-5/1/Fix.py",
            },
        )]


@dataclass
class Bugs4QCCXUncomputeSubject:
    """Bugs4Q StackExchange/16: ancilla CCX decomposition must match direct MCX."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_stackexchange_3_program_ccx_uncompute"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "ccx"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_ancilla_uncompute"]
        self.source_path = _bugs4q_path(self.root, "StackExchange/16/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "StackExchange/16/fix.py")

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        use_ancilla = bool(input_spec.get("use_ancilla", False))
        bits = list(input_spec.get("bits", [1, 1, 1]))
        qc = QuantumCircuit(5, 4, name=f"{self.subject_id}_{self.variant}")
        for qubit, bit in enumerate(bits[:3]):
            if bit:
                qc.x(qubit)
        if not use_ancilla:
            qc.mcx([0, 1, 2], 4)
        elif self.variant == "fixed":
            qc.ccx(0, 1, 3)
            qc.ccx(2, 3, 4)
            qc.ccx(0, 1, 3)
        else:
            # Models the buggy script's broken control-flow/decomposition: the
            # required second-stage CCX effect is absent.
            qc.ccx(0, 1, 3)
            qc.ccx(0, 1, 3)
        qc.measure([0, 1, 2, 4], [0, 1, 2, 3])
        return qc

    def enumerate_ancilla_uncompute(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_ancilla_uncompute",
            name="ccx_ancilla_decomposition",
            source_input={"bits": [1, 1, 1], "use_ancilla": False},
            followup_input={"bits": [1, 1, 1], "use_ancilla": True},
            metadata={
                "bugs4q_buggy": "StackExchange/16/buggy.py",
                "bugs4q_fixed": "StackExchange/16/fix.py",
            },
        )]


@dataclass
class Bugs4QMeasurementEndianSubject:
    """Bugs4Q StackExchange/9: output convention is a classical remap contract."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_stackexchange_12_program_measurement_endian"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "Output"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_classical_remap"]
        self.source_path = _bugs4q_path(self.root, "StackExchange/9/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "StackExchange/9/fix.py")

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        measure_clbits = list(input_spec.get("measure_clbits", [0, 1, 2]))
        qc = QuantumCircuit(3, 3, name=f"{self.subject_id}_{self.variant}")
        qc.x(0)
        qc.cx(0, 1)
        qc.barrier()
        if self.variant == "buggy" and measure_clbits == [2, 1, 0]:
            # Mirrors StackExchange/9/buggy.py, which reports the logical output
            # in the simulator's default classical-bit order instead of the
            # intended human-readable order.
            qc.measure([0, 1, 2], [0, 1, 2])
        else:
            # Mirrors StackExchange/9/fix.py and makes the classical output
            # convention an explicit builder input.
            qc.measure([0, 1, 2], measure_clbits)
        return qc

    def enumerate_classical_remap(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_classical_remap",
            name="measurement_endian_covariance",
            source_input={"measure_clbits": [0, 1, 2]},
            followup_input={"measure_clbits": [2, 1, 0]},
            canon_map=[2, 1, 0],
            metadata={
                "bugs4q_buggy": "StackExchange/9/buggy.py",
                "bugs4q_fixed": "StackExchange/9/fix.py",
            },
        )]


@dataclass
class Bugs4QStackOverflowQFTSubject:
    """Bugs4Q stackoverflow-6-10/bug_3: script QFT must match library QFT."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_stackoverflow_7_program_qft_direction"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "QFT operation"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_qft_round_trip"]
        self.source_path = _bugs4q_path(self.root, "stackoverflow-6-10/bug_3/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "stackoverflow-6-10/bug_3/fixed.py")

    @staticmethod
    def _prepare_vendor_phase_state(qc: QuantumCircuit) -> None:
        qc.h(range(3))
        qc.z(2)
        qc.s(1)
        qc.z(0)
        qc.t(0)

    @staticmethod
    def _buggy_script_iqft(qc: QuantumCircuit) -> None:
        # Mirrors stackoverflow-6-10/bug_3/buggy.py.  The script implements the
        # inverse direction when the user needed the regular QFT.
        n = 3
        for i in range(n // 2):
            qc.swap(i, n - 1 - i)
        for i in range(n):
            qc.h(i)
            for j in range(i + 1, n):
                qc.cp(-math.pi / (2 ** (j - i)), j, i)

    @classmethod
    def _fixed_script_qft(cls) -> QuantumCircuit:
        # Mirrors fixed.py: build the old inverse-QFT circuit, then invert it
        # to obtain the regular QFT implementation.
        qft = QuantumCircuit(3, name="script_qft")
        cls._buggy_script_iqft(qft)
        return qft.inverse()

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        implementation = str(input_spec.get("implementation", "script"))
        qc = QuantumCircuit(3, 3, name=f"{self.subject_id}_{self.variant}_{implementation}")
        self._prepare_vendor_phase_state(qc)
        if implementation == "library_qft":
            qc.compose(QFT(3, do_swaps=True, inverse=False).decompose(), range(3), inplace=True)
        elif self.variant == "fixed":
            qc.compose(self._fixed_script_qft(), range(3), inplace=True)
        else:
            self._buggy_script_iqft(qc)
        qc.measure(range(3), range(3))
        return qc

    def enumerate_qft_round_trip(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_qft_round_trip",
            name="script_qft_matches_library_qft",
            source_input={"implementation": "library_qft"},
            followup_input={"implementation": "script"},
            metadata={
                "bugs4q_buggy": "stackoverflow-6-10/bug_3/buggy.py",
                "bugs4q_fixed": "stackoverflow-6-10/bug_3/fixed.py",
            },
        )]


@dataclass
class Bugs4QGroverAncillaSubject:
    """Bugs4Q StackExchange/4: Grover ancillas must be uncomputed before reuse."""

    root: Path
    variant: str = "buggy"
    subject_id: str = "qiskit_stackexchange_8_program_grover_uncompute"
    relations: List[str] = None
    canonicalizer: Any = None
    bug_category: str = "grover algorithm"
    source_path: Optional[Path] = None
    fixed_path: Optional[Path] = None

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_ancilla_uncompute"]
        self.source_path = _bugs4q_path(self.root, "StackExchange/4/buggy.py")
        self.fixed_path = _bugs4q_path(self.root, "StackExchange/4/fix.py")

    @staticmethod
    def _initial_state(qc: QuantumCircuit, search, marker) -> None:
        qc.x(marker)
        qc.h(marker)
        qc.h(search)

    @staticmethod
    def _fixed_iteration(qc: QuantumCircuit, search, marker, ancilla) -> None:
        # Mirrors the repaired script's coherent oracle/uncompute structure.
        qc.x(search[2])
        qc.ccx(search[1], search[2], ancilla[0])
        qc.ccx(search[3], ancilla[0], ancilla[1])
        qc.ccx(search[0], search[1], ancilla[2])

        qc.x(ancilla)
        qc.ccx(ancilla[1], ancilla[2], marker)
        qc.x(marker)

        qc.x(ancilla)
        qc.ccx(search[0], search[1], ancilla[2])
        qc.ccx(search[3], ancilla[0], ancilla[1])
        qc.ccx(search[1], search[2], ancilla[0])
        qc.x(search[2])

        qc.h(search)
        qc.x(search)
        qc.ccx(search[0], search[1], ancilla[0])
        qc.ccx(search[2], ancilla[0], ancilla[1])
        qc.ccx(search[3], ancilla[1], marker)
        qc.x(search)
        qc.x(marker)

        qc.ccx(search[2], ancilla[0], ancilla[1])
        qc.ccx(search[0], search[1], ancilla[0])
        qc.h(search)
        qc.reset(ancilla)

    @staticmethod
    def _buggy_iteration(qc: QuantumCircuit, search, marker, ancilla) -> None:
        # Mirrors the buggy script's reset-instead-of-uncompute structure.
        qc.x(search[2])
        qc.ccx(search[1], search[2], ancilla[0])
        qc.ccx(search[3], ancilla[0], ancilla[1])
        qc.x(search[2])
        qc.ccx(search[0], search[1], ancilla[2])

        qc.x(ancilla)
        qc.ccx(ancilla[1], ancilla[2], marker)
        qc.x(ancilla)
        qc.x(marker)
        qc.reset(ancilla)

        qc.h(search)
        qc.x(search)
        qc.ccx(search[0], search[1], ancilla[0])
        qc.ccx(search[2], ancilla[0], ancilla[1])
        qc.ccx(search[3], ancilla[1], marker)
        qc.x(search)
        qc.x(marker)
        qc.h(search)
        qc.reset(ancilla)

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        implementation = str(input_spec.get("implementation", "candidate"))
        iterations = int(input_spec.get("iterations", 2))
        search = QuantumRegister(4, "search")
        marker = QuantumRegister(1, "marker")
        ancilla = QuantumRegister(3, "ancilla")
        result = ClassicalRegister(4, "result")
        qc = QuantumCircuit(search, marker, ancilla, result,
                            name=f"{self.subject_id}_{self.variant}_{implementation}")
        self._initial_state(qc, search, marker[0])
        for _ in range(iterations):
            if implementation == "coherent_reference" or self.variant == "fixed":
                self._fixed_iteration(qc, search, marker[0], ancilla)
            else:
                self._buggy_iteration(qc, search, marker[0], ancilla)
        qc.measure(search, result)
        return qc

    def enumerate_ancilla_uncompute(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_ancilla_uncompute",
            name="grover_reset_matches_coherent_uncompute",
            source_input={"implementation": "coherent_reference", "iterations": 2},
            followup_input={"implementation": "candidate", "iterations": 2},
            metadata={
                "bugs4q_buggy": "StackExchange/4/buggy.py",
                "bugs4q_fixed": "StackExchange/4/fix.py",
            },
        )]


PROGRAM_BUGS4Q_EXCLUSIONS = [
    {
        "subject_id": "qiskit_github_12",
        "buggy_path": "Terra-6000-7100/6571_Bug/bug_version.py",
        "fixed_path": "Terra-6000-7100/6571_Fixed/fixed_version.py",
        "reason": "measure_all changes classical register shape; no bijective canonical map",
    },
    {
        "subject_id": "qiskit_stackexchange_2",
        "buggy_path": "StackExchange/15/buggy.py",
        "fixed_path": "StackExchange/15/fix.py",
        "reason": "QPE/IQFT candidate relation not yet shown to detect buggy and pass fixed",
    },
    {
        "subject_id": "qiskit_github_16",
        "buggy_path": "Aer/bug_1/buggy.py",
        "fixed_path": "Aer/bug_1/fixed.py",
        "reason": "statevector-after-measurement API issue; no count-vector program relation in current families",
    },
    {
        "subject_id": "qiskit_stackexchange_6",
        "buggy_path": "StackExchange/1/buggy.py",
        "fixed_path": "StackExchange/1/fix.py",
        "reason": "uses mid-circuit measurement and conditionals; rejected by current soundness policy",
    },
    {
        "subject_id": "qiskit_stackexchange_18",
        "buggy_path": "StackExchange_2/bug_2/buggy.py",
        "fixed_path": "StackExchange_2/bug_2/fixed.py",
        "reason": "statevector label visualization issue; audited count-vector remap relation is not sound after H/CX",
    },
    {
        "subject_id": "qiskit_stackoverflow_6",
        "buggy_path": "stackoverflow-6-10/bug_2/buggy.py",
        "fixed_path": "stackoverflow-6-10/bug_2/fixed.py",
        "reason": "wrong-operation Bell-state case needs an explicit expected-state oracle extension, not a current relation family",
    },
    {
        "subject_id": "qiskit_github_14",
        "buggy_path": "Terra-6000-7100/6255_Bug/bug_version.py",
        "fixed_path": "Terra-6000-7100/6255_Fixed/fixed_version.py",
        "reason": "opflow expectation-value bug; requires relation-specific expectation oracle extension",
    },
]


def load_bugs4q_program_subjects(root: Path, variant: str = "buggy") -> List[object]:
    """Return hand-audited Bugs4Q subjects with genuine program-level relations."""
    root = Path(root)
    return [
        Bugs4QMeasurementOrderSubject(root=root, variant=variant),
        Bugs4QCCXRoleSubject(root=root, variant=variant),
        Bugs4QTeleportationFeedbackSubject(root=root, variant=variant),
        Bugs4QCCXUncomputeSubject(root=root, variant=variant),
        Bugs4QMeasurementEndianSubject(root=root, variant=variant),
        Bugs4QStackOverflowQFTSubject(root=root, variant=variant),
        Bugs4QGroverAncillaSubject(root=root, variant=variant),
    ]
