from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from qmtester.program_mutants import (
    FAMILY_TARGET_COUNTS,
    generate_hard_program_mutation_cases,
    generate_program_mutation_cases,
)


ROOT = Path(__file__).resolve().parents[1]


class ProgramMutantTests(unittest.TestCase):
    def test_generator_is_balanced_100_cases(self):
        cases = generate_program_mutation_cases(ROOT)
        counts = Counter(case.relation_family for case in cases)
        self.assertEqual(len(cases), 100)
        self.assertEqual(dict(counts), FAMILY_TARGET_COUNTS)
        self.assertEqual(len({case.mutant_id for case in cases}), 100)

    def test_specs_round_trip_to_subjects(self):
        case = generate_program_mutation_cases(ROOT)[0]
        self.assertTrue(case.fixed_subject.subject_id)
        self.assertTrue(case.mutant_subject.subject_id)
        self.assertEqual(case.expected_detected, True)

    def test_hard_generator_is_lower_effect_supplement(self):
        cases = generate_hard_program_mutation_cases(ROOT)
        self.assertEqual(len(cases), 20)
        self.assertEqual(
            Counter(case.relation_family for case in cases),
            Counter({"program_parameter_periodicity": 20}),
        )
        self.assertEqual(len({case.mutant_id for case in cases}), 20)


if __name__ == "__main__":
    unittest.main()
