"""Program-level subject and relation interfaces.

Circuit-level relations remain useful for artifact sanity checks, but publishable
detection experiments need relations over program inputs/builders.  These classes
define that boundary without requiring every benchmark adapter to inherit from a
heavy base class.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol

from qiskit import QuantumCircuit


InputSpec = Dict[str, Any]
Canonicalizer = Callable[[dict, dict, Optional[List[int]]], tuple]


class ProgramSubject(Protocol):
    subject_id: str
    relations: List[str]
    canonicalizer: Optional[Canonicalizer]
    bug_category: str
    source_path: Optional[Path]
    fixed_path: Optional[Path]

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        """Build the circuit for one concrete program input."""


@dataclass
class ProgramRelationCandidate:
    family: str
    name: str
    source_input: InputSpec
    followup_input: InputSpec
    canon_map: Optional[List[int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProgramRelation(Protocol):
    name: str

    def enumerate(self, subject: ProgramSubject, rng) -> List[ProgramRelationCandidate]:
        """Create concrete source/follow-up input pairs for this subject."""
