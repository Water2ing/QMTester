"""Relation families (Stage 2/3): enumerate candidate transformations, admit valid ones.

Each family implements the contract in :mod:`qmtester.relations.base` and encodes the
relation-validity obligations of Table II (preconditions, invariant, invalid contexts).
"""
from .base import Candidate, RelationFamily, FAMILIES, enumerate_admitted
from .identity import IdentityInsertion
from .swap import SwapRewriting
from .phase import PhaseRewriting
from .equivalence import EquivalenceRewriting

__all__ = [
    "Candidate",
    "RelationFamily",
    "FAMILIES",
    "enumerate_admitted",
    "IdentityInsertion",
    "SwapRewriting",
    "PhaseRewriting",
    "EquivalenceRewriting",
]
