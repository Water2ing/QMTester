from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "artifact"))

from qmtester.canonicalize import canonicalize


class CanonicalizeTests(unittest.TestCase):
    def test_flattens_multi_register_keys(self):
        ok, reason, src, fu = canonicalize({"01 00": 3}, {"01 00": 3}, None)
        self.assertTrue(ok, reason)
        self.assertEqual(src, {"0100": 3})
        self.assertEqual(fu, {"0100": 3})

    def test_bijective_remap(self):
        ok, reason, src, fu = canonicalize({"10": 5}, {"01": 5}, [1, 0])
        self.assertTrue(ok, reason)
        self.assertEqual(src, fu)

    def test_rejects_key_length_mismatch(self):
        ok, reason, *_ = canonicalize({"0": 1}, {"00": 1}, None)
        self.assertFalse(ok)
        self.assertIn("key_length_mismatch", reason)

    def test_rejects_non_bijective_map(self):
        ok, reason, *_ = canonicalize({"00": 1}, {"00": 1}, [0, 0])
        self.assertFalse(ok)
        self.assertIn("non_bijective_map", reason)

    def test_rejects_map_length_mismatch(self):
        ok, reason, *_ = canonicalize({"00": 1}, {"00": 1}, [0])
        self.assertFalse(ok)
        self.assertIn("map_length_mismatch", reason)


if __name__ == "__main__":
    unittest.main()
