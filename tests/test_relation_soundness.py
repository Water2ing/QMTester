from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from qmtester.circuit_io import normalize
from qmtester.pipeline import run_subject
from qmtester.relations import (
    EquivalenceRewriting,
    IdentityInsertion,
    PhaseRewriting,
    SwapRewriting,
)


class RelationSoundnessTests(unittest.TestCase):
    def _first_swap_candidate(self, qc):
        norm = normalize(qc)
        rel = SwapRewriting()
        cand = rel.enumerate(norm, np.random.default_rng(7))[0]
        return rel.admissible(norm, cand)

    def test_swap_rejects_reset(self):
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.reset(0)
        qc.measure([0, 1], [0, 1])
        ok, reason = self._first_swap_candidate(qc)
        self.assertFalse(ok)
        self.assertIn("reset", reason)

    def test_swap_rejects_midcircuit_measure(self):
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.measure(0, 0)
        qc.x(0)
        qc.measure(1, 1)
        ok, reason = self._first_swap_candidate(qc)
        self.assertFalse(ok)
        self.assertIn("midcircuit_measure", reason)

    def test_swap_rejects_nonterminal_measure(self):
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.measure(0, 0)
        qc.x(1)
        qc.measure(1, 1)
        ok, reason = self._first_swap_candidate(qc)
        self.assertFalse(ok)
        self.assertIn("nonterminal_measure", reason)

    def test_swap_rejects_non_bijective_classical_map(self):
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure(0, 0)
        qc.measure(1, 0)
        ok, reason = self._first_swap_candidate(qc)
        self.assertFalse(ok)
        self.assertIn("non_bijective_classical_measure_map", reason)

    def test_swap_rejects_conditionals(self):
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.x(1).c_if(qc.cregs[0], 1)
        qc.measure([0, 1], [0, 1])
        ok, reason = self._first_swap_candidate(qc)
        self.assertFalse(ok)
        self.assertIn("classical_side_effect", reason)

    def test_swap_rejects_delay(self):
        qc = QuantumCircuit(2, 2)
        qc.h(0)
        qc.delay(10, 0)
        qc.measure([0, 1], [0, 1])
        ok, reason = self._first_swap_candidate(qc)
        self.assertFalse(ok)
        self.assertIn("delay", reason)

    def test_terminal_measure_relations_are_sound_smoke(self):
        qc = QuantumCircuit(3, 3)
        qc.h(0)
        qc.rx(0.37, 1)
        qc.cx(0, 2)
        qc.ry(0.91, 2)
        qc.cz(1, 2)
        qc.measure([0, 1, 2], [0, 1, 2])
        result = run_subject(
            "terminal_soundness",
            qc,
            [IdentityInsertion(), SwapRewriting(), PhaseRewriting(), EquivalenceRewriting()],
            shots=1024,
            seed=12345,
            alpha=1e-6,
        )
        self.assertFalse(result.detected)
        self.assertGreater(len(result.admitted_pairs), 0)


if __name__ == "__main__":
    unittest.main()
