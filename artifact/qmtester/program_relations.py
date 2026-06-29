"""Reusable program-level metamorphic relation families."""
from __future__ import annotations

from typing import List

from .program_subject import ProgramRelationCandidate, ProgramSubject


def _call_capability(subject: ProgramSubject, name: str, rng) -> List[ProgramRelationCandidate]:
    fn = getattr(subject, name, None)
    if fn is None:
        return []
    out = fn(rng)
    return list(out or [])


class InputPermutationCovariance:
    """Builder-level input/qubit permutation covariance."""

    name = "program_input_permutation"

    def enumerate(self, subject: ProgramSubject, rng) -> List[ProgramRelationCandidate]:
        return _call_capability(subject, "enumerate_input_permutation", rng)


class ClassicalRegisterRemapping:
    """Program-level classical-bit/register remapping relation."""

    name = "program_classical_remap"

    def enumerate(self, subject: ProgramSubject, rng) -> List[ProgramRelationCandidate]:
        return _call_capability(subject, "enumerate_classical_remap", rng)


class QFTRoundTripRelation:
    """QFT/IQFT round-trip and bit-reversal relation."""

    name = "program_qft_round_trip"

    def enumerate(self, subject: ProgramSubject, rng) -> List[ProgramRelationCandidate]:
        return _call_capability(subject, "enumerate_qft_round_trip", rng)


class ParameterPeriodicityRelation:
    """Parameter periodicity/sign relations for rotation-heavy builders."""

    name = "program_parameter_periodicity"

    def enumerate(self, subject: ProgramSubject, rng) -> List[ProgramRelationCandidate]:
        return _call_capability(subject, "enumerate_parameter_periodicity", rng)


class AncillaUncomputeResetRelation:
    """Ancilla uncompute/reset relation for reset/ancilla benchmark cases."""

    name = "program_ancilla_uncompute"

    def enumerate(self, subject: ProgramSubject, rng) -> List[ProgramRelationCandidate]:
        return _call_capability(subject, "enumerate_ancilla_uncompute", rng)


PROGRAM_FAMILIES_DEFAULT = [
    InputPermutationCovariance(),
    ClassicalRegisterRemapping(),
    QFTRoundTripRelation(),
    ParameterPeriodicityRelation(),
    AncillaUncomputeResetRelation(),
]
