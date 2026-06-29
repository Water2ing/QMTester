from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from baselines import morphq_runner


class MorphQRunnerTests(unittest.TestCase):
    def test_morphq_does_not_call_qmtester_run_subject(self):
        source = inspect.getsource(morphq_runner.run_morphq)
        self.assertNotIn("run_subject(", source)

    def test_morphq_uses_raw_alpha(self):
        self.assertEqual(morphq_runner.MORPHQ_ALPHA, 0.05)


if __name__ == "__main__":
    unittest.main()
