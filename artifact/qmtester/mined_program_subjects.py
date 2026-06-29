"""Program subjects reconstructed from mined Quantum Computing StackExchange defects
(real builder-contract bugs, 2022-2024). Each is verified by run_program_subject:
a subject is admitted only if the buggy variant is DETECTED and the fixed variant
raises NO false positive --- the same admission bar as the audited Bugs4Q subjects.

Provenance (links in metadata):
  qcse_40171 : QPE controlled-power role mapping reversed (eig[3]->U^1 ... eig[0]->U^8
               instead of eig[i]->U^(2^i)).  Family: program_input_permutation.
  qcse_23954 : Shor inverse-QFT readout built with do_swaps=False, omitting the
               bit-reversal swaps the readout contract requires.  qft_round_trip.
  qcse_28272 : Draper QFT adder builds QFT with do_swaps=False on qubit order [2,1,0],
               breaking the round-trip/endianness convention.  qft_round_trip.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Mapping, Optional

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.circuit.library import QFT

from .program_relations import ProgramRelationCandidate


# ---------------------------------------------------------------------------
# qft_round_trip family: the program's QFT/iQFT stage must match the library
# reference on a prepared state. A wrong-swaps stage diverges; the fix matches.
# Relation: source uses the library QFT, follow-up uses the program's script QFT;
# canon_map = identity (both act on the same qubits in the same order).
# ---------------------------------------------------------------------------
@dataclass
class MinedShorIQFTSubject:
    """qcse_23954: Shor counting-register inverse-QFT built with do_swaps=False."""

    variant: str = "buggy"
    subject_id: str = "qcse_23954_program_shor_iqft_swaps"
    n: int = 4
    relations: Optional[List[str]] = None
    bug_category: str = "inverse QFT readout omits bit-reversal swaps"
    link: str = "https://quantumcomputing.stackexchange.com/questions/23954"

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_qft_round_trip"]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        n = self.n
        impl = str(input_spec.get("implementation", "script"))
        phi = int(input_spec.get("phi", 5))  # a value whose bit-reversal differs
        qc = QuantumCircuit(n, n, name=f"{self.subject_id}_{self.variant}_{impl}")
        # prepare a Fourier-basis state |phi~> = QFT|phi>, so the iQFT readout must
        # return |phi>; with wrong swaps it returns the bit-reversed value.
        for i in range(n):
            if (phi >> i) & 1:
                qc.x(i)
        qc.compose(QFT(n, do_swaps=True).decompose(), range(n), inplace=True)
        # readout iQFT: library reference (source) vs script (follow-up).
        if impl == "library_qft":
            qc.compose(QFT(n, do_swaps=True, inverse=True).decompose(), range(n), inplace=True)
        else:
            do_swaps = (self.variant == "fixed")  # buggy omits swaps
            qc.compose(QFT(n, do_swaps=do_swaps, inverse=True).decompose(), range(n), inplace=True)
        qc.measure(range(n), range(n))
        return qc

    def enumerate_qft_round_trip(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_qft_round_trip",
            name="shor_iqft_matches_library",
            source_input={"implementation": "library_qft", "phi": 5},
            followup_input={"implementation": "script", "phi": 5},
            canon_map=None,
            metadata={"se_link": self.link},
        )]


@dataclass
class MinedDraperQFTSubject:
    """qcse_28272: Draper adder QFT built do_swaps=False on qubit order [2,1,0]."""

    variant: str = "buggy"
    subject_id: str = "qcse_28272_program_draper_qft_order"
    n: int = 3
    relations: Optional[List[str]] = None
    bug_category: str = "QFT stage wrong swaps + reversed qubit order"
    link: str = "https://quantumcomputing.stackexchange.com/questions/28272"

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_qft_round_trip"]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        n = self.n
        impl = str(input_spec.get("implementation", "script"))
        phi = int(input_spec.get("phi", 3))
        qc = QuantumCircuit(n, n, name=f"{self.subject_id}_{self.variant}_{impl}")
        for i in range(n):
            if (phi >> i) & 1:
                qc.x(i)
        qc.compose(QFT(n, do_swaps=True).decompose(), range(n), inplace=True)
        if impl == "library_qft":
            qc.compose(QFT(n, do_swaps=True, inverse=True).decompose(), range(n), inplace=True)
        else:
            if self.variant == "fixed":
                qc.compose(QFT(n, do_swaps=True, inverse=True).decompose(), range(n), inplace=True)
            else:
                # mirrors `QFT(3, do_swaps=False).inverse()` appended on order [2,1,0]
                qc.compose(QFT(n, do_swaps=False, inverse=True).decompose(),
                           list(reversed(range(n))), inplace=True)
        qc.measure(range(n), range(n))
        return qc

    def enumerate_qft_round_trip(self, rng) -> List[ProgramRelationCandidate]:
        return [ProgramRelationCandidate(
            family="program_qft_round_trip",
            name="draper_qft_matches_library",
            source_input={"implementation": "library_qft", "phi": 3},
            followup_input={"implementation": "script", "phi": 3},
            canon_map=None,
            metadata={"se_link": self.link},
        )]


# ---------------------------------------------------------------------------
# input_permutation family: the QPE counting-register qubit ROLES are mishandled.
# A role-covariant builder is invariant under permuting the eig roles (controls +
# iQFT + measurement relabelled together); the buggy builder hard-codes the
# control->power assignment, so permuting the roles + canonicalizing diverges.
# ---------------------------------------------------------------------------
@dataclass
class MinedQPERoleSubject:
    """qcse_40171: QPE controlled-power mapping reversed (eig[3]->U^1 ... eig[0]->U^8)."""

    variant: str = "buggy"
    subject_id: str = "qcse_40171_program_qpe_role"
    n: int = 4               # counting (eig) qubits
    phase_num: int = 10      # phase = phase_num / 2**n  (=> 1010 for n=4)
    relations: Optional[List[str]] = None
    bug_category: str = "QPE control-qubit to power role mapping reversed"
    link: str = "https://quantumcomputing.stackexchange.com/questions/40171"

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_input_permutation"]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        n = self.n
        roles = list(input_spec.get("roles", list(range(n))))  # eig physical for logical i
        theta = 2 * math.pi * self.phase_num / (2 ** n)  # eigenphase of U on |1>
        eig = QuantumRegister(n, "eig")
        a = QuantumRegister(1, "anc")  # 1-qubit eigenstate register
        c = ClassicalRegister(n, "ceig")
        qc = QuantumCircuit(eig, a, c, name=f"{self.subject_id}_{self.variant}")
        qc.x(a[0])           # |1>: eigenstate of U=diag(1,e^{i theta})
        qc.h(eig)
        if self.variant == "fixed":
            # role-covariant: logical i (controlling U^(2^i)) sits on physical eig[roles[i]]
            for i in range(n):
                qc.cp((2 ** i) * theta, eig[roles[i]], a[0])
        else:
            # buggy: hard-codes eig[n-1-i] -> U^(2^i), ignoring the role map
            for i in range(n):
                qc.cp((2 ** i) * theta, eig[n - 1 - i], a[0])
        # inverse QFT over the eig register in logical role order, then read out
        qc.compose(QFT(n, do_swaps=True, inverse=True).decompose(),
                   [eig[roles[i]] for i in range(n)], inplace=True)
        for i in range(n):
            qc.measure(eig[roles[i]], c[i])
        return qc

    def enumerate_input_permutation(self, rng) -> List[ProgramRelationCandidate]:
        n = self.n
        perm = list(reversed(range(n)))  # permute eig roles
        # follow-up measures logical i on physical eig[perm[i]] into clbit i; the
        # source measures logical i on eig[i]. canon_map is identity: both record
        # logical bit i in clbit i, so a covariant builder agrees.
        return [ProgramRelationCandidate(
            family="program_input_permutation",
            name="qpe_role_covariance",
            source_input={"roles": list(range(n))},
            followup_input={"roles": perm},
            canon_map=None,
            metadata={"se_link": self.link},
        )]


MINED_SUBJECTS = [MinedShorIQFTSubject, MinedDraperQFTSubject, MinedQPERoleSubject]
