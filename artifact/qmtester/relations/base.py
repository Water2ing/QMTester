"""Relation-family contract shared by the four QMTester transformation families.

A candidate transformation ``t`` for source ``P`` carries:
  * the follow-up circuit ``P' = t(P)`` (built lazily by ``apply``),
  * an admissibility predicate ``A_R(P, t)`` (Table II preconditions),
  * an output-bit canonicalization map ``c_R`` (a permutation of clbit positions)
    that restores follow-up bitstrings to the source bit order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from qiskit import QuantumCircuit

from ..circuit_io import NormalizedCircuit


@dataclass
class Candidate:
    """One enumerated transformation instance."""

    family: str
    name: str
    params: dict = field(default_factory=dict)
    # canon_map[i] = source clbit position that follow-up clbit position i maps to.
    # Identity map => None (no remapping needed).
    canon_map: Optional[List[int]] = None
    # filled in once admissibility is checked
    admissible: Optional[bool] = None
    reason: Optional[str] = None
    followup: Optional[QuantumCircuit] = None


class RelationFamily:
    """Abstract relation family. Subclasses implement the four hooks below."""

    name: str = "abstract"

    def enumerate(self, norm: NormalizedCircuit, rng) -> List[Candidate]:
        raise NotImplementedError

    def admissible(self, norm: NormalizedCircuit, cand: Candidate) -> Tuple[bool, str]:
        raise NotImplementedError

    def apply(self, norm: NormalizedCircuit, cand: Candidate) -> QuantumCircuit:
        raise NotImplementedError


def enumerate_admitted(
    norm: NormalizedCircuit,
    families: List[RelationFamily],
    rng,
) -> Tuple[List[Candidate], List[Candidate]]:
    """Enumerate every candidate from ``families`` and split into admitted/rejected.

    Rejected candidates are returned (with a reason) so they can be logged as a
    coverage loss rather than silently dropped (Sec. III-D, III-G).
    """
    admitted: List[Candidate] = []
    rejected: List[Candidate] = []
    for fam in families:
        for cand in fam.enumerate(norm, rng):
            ok, reason = fam.admissible(norm, cand)
            cand.admissible = ok
            cand.reason = reason
            if ok:
                cand.followup = fam.apply(norm, cand)
                admitted.append(cand)
            else:
                rejected.append(cand)
    return admitted, rejected


# Registry of family name -> class, populated by submodule imports.
FAMILIES: Dict[str, type] = {}


def register(cls):
    FAMILIES[cls.name] = cls
    return cls
