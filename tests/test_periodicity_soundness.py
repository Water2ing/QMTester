"""Admission machinery: controlled-rotation periodicity soundness.

A 2pi periodicity shift is sound for an uncontrolled Pauli rotation (global phase)
but UNSOUND for a controlled Pauli rotation (period 4pi). These tests show the
admission check rejects the mis-declaration and does not over-reject the genuinely
2pi-periodic cases (single-qubit rotation, controlled-phase cp).
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

from qiskit import QuantumCircuit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from qmtester.program_subject import ProgramRelationCandidate
from qmtester.soundness import check_relation_soundness, has_controlled_pauli_rotation


def _cand(shift):
    return ProgramRelationCandidate(
        family="program_parameter_periodicity",
        name="t",
        source_input={"theta": 0.3},
        followup_input={"theta": 0.3 + shift},
    )


class PeriodicitySoundnessTests(unittest.TestCase):
    def test_rejects_2pi_on_controlled_rz(self):
        qc = QuantumCircuit(2, 1)
        qc.h(0)
        qc.crz(0.3, 0, 1)
        qc.measure(1, 0)
        ok, reason = check_relation_soundness(_cand(2 * math.pi), qc)
        self.assertFalse(ok)
        self.assertIn("controlled", reason)

    def test_admits_4pi_on_controlled_rz(self):
        qc = QuantumCircuit(2, 1)
        qc.h(0)
        qc.crz(0.3, 0, 1)
        qc.measure(1, 0)
        ok, _ = check_relation_soundness(_cand(4 * math.pi), qc)
        self.assertTrue(ok)

    def test_admits_2pi_on_single_qubit_rotation(self):
        qc = QuantumCircuit(1, 1)
        qc.ry(0.3, 0)
        qc.measure(0, 0)
        ok, _ = check_relation_soundness(_cand(2 * math.pi), qc)
        self.assertTrue(ok)

    def test_admits_2pi_on_controlled_phase(self):
        # cp(theta) = diag(1,1,1,e^{i theta}) is genuinely 2pi-periodic.
        qc = QuantumCircuit(2, 2)
        qc.h([0, 1])
        qc.cp(0.3, 0, 1)
        qc.measure([0, 1], [0, 1])
        self.assertFalse(has_controlled_pauli_rotation(qc))
        ok, _ = check_relation_soundness(_cand(2 * math.pi), qc)
        self.assertTrue(ok)

    def test_detects_generic_controlled_wrapper(self):
        from qiskit.circuit.library import RZGate
        qc = QuantumCircuit(3, 1)
        qc.append(RZGate(0.3).control(2), [0, 1, 2])
        qc.measure(2, 0)
        self.assertTrue(has_controlled_pauli_rotation(qc))


if __name__ == "__main__":
    unittest.main()
