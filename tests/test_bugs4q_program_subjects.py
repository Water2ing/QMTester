from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from qmtester.bugs4q_program_subjects import (
    Bugs4QCCXRoleSubject,
    Bugs4QCCXUncomputeSubject,
    Bugs4QGroverAncillaSubject,
    Bugs4QMeasurementEndianSubject,
    Bugs4QMeasurementOrderSubject,
    Bugs4QStackOverflowQFTSubject,
    Bugs4QTeleportationFeedbackSubject,
    load_bugs4q_program_subjects,
)
from qmtester.program_pipeline import run_program_subject
from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT


ROOT = Path(__file__).resolve().parents[1]


class Bugs4QProgramSubjectTests(unittest.TestCase):
    def _run(self, subject):
        return run_program_subject(
            subject,
            PROGRAM_FAMILIES_DEFAULT,
            shots=4096,
            seed=20260616,
            alpha=0.05,
        )

    def test_measurement_order_bug_detected_and_fixed_holds(self):
        for cls in [
            Bugs4QMeasurementOrderSubject,
            Bugs4QCCXRoleSubject,
            Bugs4QTeleportationFeedbackSubject,
            Bugs4QCCXUncomputeSubject,
            Bugs4QMeasurementEndianSubject,
            Bugs4QStackOverflowQFTSubject,
            Bugs4QGroverAncillaSubject,
        ]:
            with self.subTest(subject=cls.__name__):
                buggy = self._run(cls(ROOT, variant="buggy"))
                fixed = self._run(cls(ROOT, variant="fixed"))

                self.assertTrue(buggy.detected)
                self.assertFalse(fixed.detected)
                self.assertEqual(len(buggy.admitted_pairs), 1)
                self.assertEqual(len(fixed.admitted_pairs), 1)

    def test_loader_returns_audited_subjects(self):
        subjects = load_bugs4q_program_subjects(ROOT, variant="buggy")
        self.assertGreaterEqual(len(subjects), 7)
        self.assertTrue(all(s.source_path and s.source_path.exists() for s in subjects))
        self.assertTrue(all(s.fixed_path and s.fixed_path.exists() for s in subjects))


if __name__ == "__main__":
    unittest.main()
