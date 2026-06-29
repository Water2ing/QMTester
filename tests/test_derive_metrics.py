from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import derive_metrics


def _complete_rows(denominator: int = 1):
    rows = []
    for rid in derive_metrics.REQUIRED_ROW_IDS:
        rows.append({
            "row_id": rid,
            "denominator": 0 if rid == "mcnemar_bugs4q" else denominator,
            "numerator": 0,
        })
    return rows


class DeriveMetricsTests(unittest.TestCase):
    def test_fails_on_missing_denominator(self):
        rows = _complete_rows()
        rows[0]["denominator"] = 0
        with self.assertRaises(SystemExit):
            derive_metrics._check_required(rows, {})

    def test_fails_on_missing_shot_row(self):
        rows = [r for r in _complete_rows() if r["row_id"] != "diagnostic_shots_8192"]
        with self.assertRaises(SystemExit):
            derive_metrics._check_required(rows, {})

    def test_fails_on_expected_denominator_mismatch(self):
        rows = _complete_rows(denominator=1)
        with self.assertRaises(SystemExit):
            derive_metrics._check_required(rows, {"injected": 2})

    def test_fails_on_missing_program_row_when_expected(self):
        rows = [
            r for r in _complete_rows()
            if r["row_id"] != "program_injected_qmtester"
        ]
        with self.assertRaises(SystemExit):
            derive_metrics._check_required(rows, {"program_injected": 100})

    def test_stale_duplicate_subjects_are_rejected(self):
        with self.assertRaises(ValueError):
            derive_metrics.dedup_by(
                [{"subject_id": "s1", "detected": False}, {"subject_id": "s1", "detected": True}],
                "subject_id",
            )

    def test_multiple_run_ids_require_explicit_run_id(self):
        with tempfile.TemporaryDirectory() as td:
            shard_dir = Path(td)
            p = shard_dir / "summary_shard0000.jsonl"
            p.write_text(
                json.dumps({"run_id": "a", "subject_id": "s1", "method": "qmtester"}) + "\n"
                + json.dumps({"run_id": "b", "subject_id": "s2", "method": "qmtester"}) + "\n"
            )
            with self.assertRaises(ValueError):
                derive_metrics._assert_single_run_id(shard_dir, None)

    def test_numbered_shards_excludes_ablation_and_shot_tags(self):
        with tempfile.TemporaryDirectory() as td:
            shard_dir = Path(td)
            prefix = "injected_summary_identity_swap_phase_equivalence_shard"
            for name in [
                f"{prefix}0000.jsonl",
                f"{prefix}0001.jsonl",
                f"{prefix}0000_abl.jsonl",
                f"{prefix}0000_shots_4096.jsonl",
            ]:
                (shard_dir / name).write_text("{}\n")

            got = [p.name for p in derive_metrics.numbered_shards(shard_dir, prefix)]
            self.assertEqual(got, [f"{prefix}0000.jsonl", f"{prefix}0001.jsonl"])


if __name__ == "__main__":
    unittest.main()
