"""Relation-soundness admission checks (Table II "invalid contexts").

These checks run *before* the statistical test and reject a candidate whose
declared relation is unsound for the concrete built circuit, logging it as a
coverage loss rather than scoring it as a test outcome. They make the paper's
"admission machinery catches mis-declared relations" claim operative.

Currently enforced: the **controlled-rotation periodicity rule**.
A period-2pi shift of a rotation parameter is sound for an *uncontrolled*
single-qubit Pauli rotation, because Rz(theta+2pi) = -Rz(theta) differs only by a
*global* phase that the Born rule cannot observe. For a **controlled** Pauli
rotation (crx/cry/crz) that -1 becomes a *relative* phase between the control=0
and control=1 branches and the measured distribution is **not** invariant -- the
correct period is 4pi. A 2pi declaration on such a gate is therefore a *false*
metamorphic relation that would flag a correct program; we reject it.

Note: controlled-*phase* gates (cp, cu1) are genuinely 2pi-periodic
(diag(1,1,1,e^{i theta}) with e^{i 2pi}=1), so they are NOT rejected.
"""
from __future__ import annotations

import math
from typing import Tuple

# Inputs whose difference defines the periodicity shift.
_ANGLE_KEYS = ("theta", "angle", "phi", "lam", "lambda")
_CONTROLLED_PAULI_ROT_NAMES = {"crx", "cry", "crz", "mcrx", "mcry", "mcrz"}
_PAULI_ROT_BASE = {"rx", "ry", "rz"}


def _input_shift(candidate) -> float | None:
    """Periodicity shift = follow-up angle - source angle, if both inputs carry one."""
    src = getattr(candidate, "source_input", None) or {}
    fu = getattr(candidate, "followup_input", None) or {}
    for key in _ANGLE_KEYS:
        if key in src and key in fu:
            try:
                return float(fu[key]) - float(src[key])
            except (TypeError, ValueError):
                return None
    return None


def has_controlled_pauli_rotation(qc) -> bool:
    """True iff the circuit contains a controlled Pauli rotation (crx/cry/crz),
    including generic ControlledGate wrappers around rx/ry/rz."""
    for inst in getattr(qc, "data", []):
        op = getattr(inst, "operation", inst[0] if isinstance(inst, tuple) else None)
        if op is None:
            continue
        name = (getattr(op, "name", "") or "").lower()
        if name in _CONTROLLED_PAULI_ROT_NAMES:
            return True
        nctrl = getattr(op, "num_ctrl_qubits", 0) or 0
        base = (getattr(getattr(op, "base_gate", None), "name", "") or "").lower()
        if nctrl > 0 and base in _PAULI_ROT_BASE:
            return True
    return False


def periodicity_relation_admissible(candidate, source_qc) -> Tuple[bool, str]:
    """Reject a 2pi (odd-multiple) periodicity shift on a controlled Pauli rotation."""
    shift = _input_shift(candidate)
    if shift is None:
        return True, "OK"
    if not has_controlled_pauli_rotation(source_qc):
        return True, "OK"
    k = shift / (2.0 * math.pi)
    k_round = round(k)
    if abs(k - k_round) > 1e-6:
        # Not a multiple of 2pi at all -- out of scope for this check.
        return True, "OK"
    if k_round % 2 != 0:
        return (
            False,
            "INVALID_CONTEXT:periodicity_2pi_on_controlled_rotation"
            "(controlled_pauli_rotation_has_period_4pi)",
        )
    return True, "OK"


def check_relation_soundness(candidate, source_qc) -> Tuple[bool, str]:
    """Dispatch admission checks by relation family. Returns (admissible, reason)."""
    family = getattr(candidate, "family", "")
    if family == "program_parameter_periodicity":
        return periodicity_relation_admissible(candidate, source_qc)
    return True, "OK"
