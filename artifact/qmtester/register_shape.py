"""``program_register_shape``: a sixth relation family that brings the most common real
builder-contract defect --- the ``measure_all()`` register-shape change --- in scope.

The five distribution families require a *bijective* output map on the measured support,
so they reject any candidate whose output key length changes (canonicalize.py
``_validate_key_length``). That is exactly why the prevalent ``measure_all`` defect (the
excluded Bugs4Q subject ``qiskit_github_12``; 37 LintQ findings) is out of scope: appending
a fresh ``meas`` register changes the output shape from n to 2n bits, which is not a
bijective remap.

This family RELAXES admission to a documented *register-shape contract*: a builder asked to
report its result in an n-bit declared layout must emit exactly that shape. Emitting surplus
classical bits beyond the declared measurement (a redundant register) is a contract
violation and is DETECTED --- i.e., the ``key_length_mismatch`` that the distribution
families treat as an admission rejection is, for this family, the detection signal. A
correct builder honours the layout (n-bit output) and is clean.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

from .canonicalize import _flatten_counts
from .execute import execute_circuit
from . import DEFAULT_SHOTS, MASTER_SEED


@dataclass
class RegisterShapeSubject:
    """A builder that should report n results in its declared n-bit register.

    ``buggy``: appends a redundant register via ``measure_all`` (n -> 2n bit output).
    ``fixed``: measures into the declared register (n-bit output).
    Mirrors the LintQ ``ql-measure-all-abuse`` pattern and the excluded ``qiskit_github_12``.
    """

    variant: str = "buggy"
    subject_id: str = "qiskit_measure_all_register_shape"
    n: int = 3
    relations: Optional[List[str]] = None
    bug_category: str = "measure_all register-shape change"

    def __post_init__(self) -> None:
        if self.relations is None:
            self.relations = ["program_register_shape"]
        self.declared_n = self.n

    def build(self, input_spec: Mapping[str, Any]) -> QuantumCircuit:
        n = int(input_spec.get("n", self.n))
        q = QuantumRegister(n, "q")
        c = ClassicalRegister(n, "c")
        qc = QuantumCircuit(q, c, name=f"{self.subject_id}_{self.variant}")
        qc.h(0)
        for i in range(n - 1):
            qc.cx(i, i + 1)
        if self.variant == "buggy":
            # Mirrors `qc.measure_all()` on a circuit that already declares `c`: a fresh
            # `meas` register is appended, so the declared `c` stays constant-0 and the
            # output is 2n bits (the LintQ "twice as long output").
            qc.measure_all()
        else:
            qc.measure(q, c)
        return qc

    def enumerate_register_shape(self, rng):
        from .program_subject import ProgramRelationCandidate
        return [ProgramRelationCandidate(
            family="program_register_shape",
            name="declared_register_shape_honored",
            source_input={"n": self.n},
            followup_input={"n": self.n},
            metadata={"declared_n": self.n,
                      "excluded_subject": "qiskit_github_12",
                      "lintq_rule": "ql-measure-all-abuse"},
        )]


class RegisterShapeRelation:
    """Detects a register-shape contract violation (output wider than the declared layout)."""

    name = "program_register_shape"

    def enumerate(self, subject, rng):
        fn = getattr(subject, "enumerate_register_shape", None)
        return list(fn(rng) or []) if fn else []


def detect_register_shape(counts: dict, declared_n: int):
    """(violated, reason): the documented register-shape oracle.

    A violation is an output whose flattened key length exceeds the declared n bits with a
    constant surplus register (information-free redundant bits) --- the measure_all defect.
    """
    flat = _flatten_counts(counts)
    lens = {len(k) for k in flat}
    if len(lens) != 1:
        return True, f"non-uniform output width {sorted(lens)}"
    width = next(iter(lens))
    if width <= declared_n:
        return False, f"output width {width} == declared {declared_n}"
    surplus = width - declared_n
    # Are there `surplus` adjacent classical bits that are constant across every shot?
    # (a redundant register the builder appended but did not need). Check both ends, since
    # register order in the flattened key depends on which register was added last.
    leading_const = len({k[:surplus] for k in flat}) == 1
    trailing_const = len({k[-surplus:] for k in flat}) == 1
    if leading_const or trailing_const:
        return True, f"output {width} bits > declared {declared_n}: redundant constant register"
    return True, f"output {width} bits > declared {declared_n}"


def run_register_shape_subject(subject, *, shots: int = DEFAULT_SHOTS, seed: int = MASTER_SEED):
    """Evaluate the register-shape relation on one subject. Returns (detected, reason)."""
    for cand in subject.enumerate_register_shape(None):
        counts = execute_circuit(subject.build(cand.source_input), shots=shots, seed=seed)
        if counts is None:
            continue
        violated, reason = detect_register_shape(counts, cand.metadata.get("declared_n", subject.n))
        if violated:
            return True, reason
    return False, "register-shape contract honoured"
