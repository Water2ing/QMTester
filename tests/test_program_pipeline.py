from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from qmtester.program_examples import (
    PermutationParitySubject,
    QFTRoundTripSubject,
    RotationPeriodicitySubject,
)
from qmtester.program_pipeline import run_program_subject
from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT


class ProgramPipelineTests(unittest.TestCase):
    def test_program_relations_hold_on_correct_subjects(self):
        for subject in [
            PermutationParitySubject(),
            RotationPeriodicitySubject(),
            QFTRoundTripSubject(),
        ]:
            result = run_program_subject(
                subject,
                PROGRAM_FAMILIES_DEFAULT,
                shots=1024,
                seed=99,
                alpha=1e-6,
            )
            self.assertFalse(result.detected, subject.subject_id)
            self.assertGreater(len(result.admitted_pairs), 0)

    def test_program_positive_controls_detect_without_swap(self):
        subjects = [
            PermutationParitySubject(buggy_ignore_order=True),
            RotationPeriodicitySubject(buggy_halve_angle=True),
            QFTRoundTripSubject(buggy_omit_inverse=True),
        ]
        detections = []
        for subject in subjects:
            result = run_program_subject(
                subject,
                PROGRAM_FAMILIES_DEFAULT,
                shots=4096,
                seed=123,
                alpha=0.05,
            )
            detections.append(result.detected)
        self.assertGreaterEqual(sum(detections), 2)


if __name__ == "__main__":
    unittest.main()
