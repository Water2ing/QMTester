"""Algorithm 3: derive canonical_results.csv from per-experiment summary files.

Reads summary JSONL files directly (not raw_runs.jsonl) so that each cohort
and experiment type is unambiguously identified by filename convention:

  summary_shard*.jsonl                   — Bugs4Q QMTester  (method='qmtester')
  morphq_summary_shard*.jsonl            — Bugs4Q MorphQ    (method='morphq')
  injected_summary_<fam>_shard*.jsonl    — Injected faults  (fam = enabled families)
  falsepos_summary_{label}.jsonl         — False-positive rate per config
  injected_summary_<fam>_shard*_shots_*.jsonl — Shot sensitivity (tagged)

FAILS CLOSED if any required row is absent or has a zero denominator.

Usage:
    python scripts/derive_metrics.py \\
        --root . \\
        --shard_dir data/results/shards \\
        --out data/results/canonical_results.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def mcnemar_p(b: int, c: int) -> float:
    from scipy.stats import binom
    if b + c == 0:
        return 1.0
    n = b + c
    k = min(b, c)
    return min(2 * float(binom.cdf(k, n, 0.5)), 1.0)


def load_jsonl(path: Path) -> List[dict]:
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    raise ValueError(f"invalid JSONL record in {path}")
    return out


def load_glob(shard_dir: Path, pattern: str) -> List[dict]:
    out = []
    for p in sorted(shard_dir.glob(pattern)):
        out.extend(load_jsonl(p))
    return out


def numbered_shards(shard_dir: Path, prefix: str) -> List[Path]:
    """Return files named exactly ``<prefix><NNNN>.jsonl``.

    This keeps primary RQ2 shards separate from ablation and shot-sensitivity
    files that intentionally share the same family label.
    """
    pat = re.compile(rf"^{re.escape(prefix)}\d{{4}}\.jsonl$")
    return [p for p in sorted(shard_dir.glob(f"{prefix}*.jsonl")) if pat.match(p.name)]


def filter_run_id(recs: List[dict], run_id: Optional[str]) -> List[dict]:
    if run_id is None:
        return recs
    return [r for r in recs if r.get("run_id") == run_id]


def dedup_by(recs: List[dict], key: str) -> Dict[str, dict]:
    """Map records by key and fail on duplicates instead of hiding stale shards."""
    by_key: Dict[str, dict] = {}
    for r in recs:
        k = r.get(key, "")
        if not k:
            continue
        if k in by_key:
            raise ValueError(f"duplicate summary key {key}={k}; clean shard dir or use a fresh run_id")
        by_key[k] = r
    return by_key


def detection_row(row_id, cohort, method, subjects: Dict[str, dict]) -> dict:
    det = sum(1 for r in subjects.values() if r.get("detected"))
    tot = len(subjects)
    ci_lo, ci_hi = wilson_ci(det, tot)
    return dict(row_id=row_id, cohort=cohort, method=method, metric="detection_rate",
                numerator=det, denominator=tot,
                rate=det / tot if tot else 0,
                ci_low=ci_lo, ci_high=ci_hi)


def _keyed(records: List[dict], key_fields: List[str]) -> Dict[str, dict]:
    out = {}
    for record in records:
        key = "::".join(str(record.get(field, "")) for field in key_fields)
        if not key or key in out:
            raise ValueError(f"duplicate summary key {key_fields}={key}")
        out[key] = record
    return out


def _assert_single_run_id(shard_dir: Path, run_id: Optional[str]) -> None:
    if run_id is not None:
        return
    run_ids = set()
    for p in sorted(shard_dir.glob("*summary*.jsonl")):
        for rec in load_jsonl(p):
            rid = rec.get("run_id")
            if rid:
                run_ids.add(rid)
    if len(run_ids) > 1:
        raise ValueError(f"multiple run IDs in {shard_dir}: {sorted(run_ids)}; pass --run_id")


def derive(root: Path, shard_dir: Path, out_path: Path, run_id: Optional[str], expected: dict) -> None:
    _assert_single_run_id(shard_dir, run_id)
    rows = []

    # ------------------------------------------------------------------
    # RQ1 / TABLE VIII: Bugs4Q detection — QMTester all families
    # ------------------------------------------------------------------
    bugs4q_all = filter_run_id(load_glob(shard_dir, "summary_shard*.jsonl"), run_id)
    bugs4q_qmt = dedup_by([r for r in bugs4q_all if r.get("method") == "qmtester"], "subject_id")
    rows.append(detection_row(
        "diagnostic_bugs4q_qmtester", "DiagnosticBugs4Q", "QMTester", bugs4q_qmt
    ))

    # ------------------------------------------------------------------
    # RQ2 / TABLE VIII: MorphQ comparison on Bugs4Q
    # ------------------------------------------------------------------
    morphq_all = filter_run_id(load_glob(shard_dir, "morphq_summary_shard*.jsonl"), run_id)
    morphq_subjs = dedup_by(morphq_all, "subject_id")
    rows.append(detection_row(
        "diagnostic_bugs4q_morphq", "DiagnosticBugs4Q", "MorphQ", morphq_subjs
    ))

    # McNemar on paired decisions
    common_ids = set(bugs4q_qmt.keys()) & set(morphq_subjs.keys())
    qmt_only = sum(1 for sid in common_ids
                   if bugs4q_qmt[sid].get("detected") and not morphq_subjs[sid].get("detected"))
    morphq_only = sum(1 for sid in common_ids
                      if not bugs4q_qmt[sid].get("detected") and morphq_subjs[sid].get("detected"))
    mn_p = mcnemar_p(qmt_only, morphq_only)
    rows.append(dict(row_id="diagnostic_mcnemar_bugs4q", cohort="DiagnosticBugs4Q",
                     method="QMTester_vs_MorphQ", metric="mcnemar_p",
                     numerator=qmt_only, denominator=morphq_only,
                     rate=mn_p, ci_low=None, ci_high=None))

    # ------------------------------------------------------------------
    # RQ2 / TABLE VIII: Injected faults (all families, 4096 shots)
    # Only include primary numbered shards.  Ablation and shot-sensitivity files
    # intentionally share the family label and must not enter this denominator.
    # ------------------------------------------------------------------
    inj_full_label = "identity_swap_phase_equivalence"
    inj_all_files = numbered_shards(shard_dir, f"injected_summary_{inj_full_label}_shard")
    inj_all = []
    for p in inj_all_files:
        inj_all.extend(filter_run_id(load_jsonl(p), run_id))

    inj_qmt = dedup_by([r for r in inj_all if r.get("method") == "qmtester"], "mutant_id")
    inj_morphq = dedup_by([r for r in inj_all if r.get("method") == "morphq"], "mutant_id")
    rows.append(detection_row(
        "diagnostic_injected_qmtester", "DiagnosticInjectedFaults", "QMTester", inj_qmt
    ))
    rows.append(detection_row(
        "diagnostic_injected_morphq", "DiagnosticInjectedFaults", "MorphQ", inj_morphq
    ))

    # ------------------------------------------------------------------
    # Main RQ1/RQ2: audited program-level Bugs4Q and builder-level mutants.
    # ------------------------------------------------------------------
    program_bugs = filter_run_id(load_glob(shard_dir, "program_bugs4q_summary*.jsonl"), run_id)
    program_bugs_qmt = dedup_by([
        r for r in program_bugs
        if r.get("method") == "qmtester_program" and r.get("variant") == "buggy"
    ], "subject_id")
    program_bugs_morphq = dedup_by([
        r for r in program_bugs
        if r.get("method") == "morphq" and r.get("variant") == "buggy"
    ], "subject_id")
    rows.append(detection_row(
        "program_bugs4q_qmtester", "ProgramBugs4Q", "QMTester", program_bugs_qmt
    ))
    rows.append(detection_row(
        "program_bugs4q_morphq", "ProgramBugs4Q", "MorphQ", program_bugs_morphq
    ))

    program_full = filter_run_id(
        load_glob(shard_dir, "program_injected_summary_full.jsonl"), run_id
    )
    program_inj_qmt = dedup_by([
        r for r in program_full
        if r.get("method") == "qmtester_program" and r.get("variant") == "mutant"
    ], "mutant_id")
    program_inj_morphq = dedup_by([
        r for r in program_full
        if r.get("method") == "morphq" and r.get("variant") == "mutant"
    ], "mutant_id")
    rows.append(detection_row(
        "program_injected_qmtester", "ProgramInjectedFaults", "QMTester", program_inj_qmt
    ))
    rows.append(detection_row(
        "program_injected_morphq", "ProgramInjectedFaults", "MorphQ", program_inj_morphq
    ))

    fixed_rows = [
        r for r in program_bugs + program_full
        if r.get("method") == "qmtester_program" and r.get("variant") == "fixed"
    ]
    fixed_by_key = _keyed(fixed_rows, ["program_subject_id"])
    fixed_fp = sum(1 for r in fixed_by_key.values() if r.get("detected"))
    fixed_tot = len(fixed_by_key)
    ci_lo, ci_hi = wilson_ci(fixed_fp, fixed_tot)
    rows.append(dict(row_id="program_fp_fixed", cohort="ProgramFixedVariants",
                     method="QMTester", metric="false_positive_rate",
                     numerator=fixed_fp, denominator=fixed_tot,
                     rate=fixed_fp / fixed_tot if fixed_tot else 0,
                     ci_low=ci_lo, ci_high=ci_hi))

    program_families = [
        "program_input_permutation",
        "program_classical_remap",
        "program_qft_round_trip",
        "program_parameter_periodicity",
        "program_ancilla_uncompute",
    ]
    for family in program_families:
        records = filter_run_id(
            load_glob(shard_dir, f"program_injected_summary_{family}.jsonl"), run_id
        )
        qmt = dedup_by([
            r for r in records
            if r.get("method") == "qmtester_program" and r.get("variant") == "mutant"
        ], "mutant_id")
        det = sum(1 for r in qmt.values() if r.get("detected"))
        tot = len(qmt)
        ci_lo, ci_hi = wilson_ci(det, tot) if tot else (None, None)
        rows.append(dict(row_id=f"program_ablation_{family}",
                         cohort="ProgramInjectedFaults",
                         method=f"QMTester_ablation_{family}",
                         metric="detection_rate",
                         numerator=det, denominator=tot or None,
                         rate=det / tot if tot else None,
                         ci_low=ci_lo, ci_high=ci_hi))

    # ------------------------------------------------------------------
    # RQ4 / TABLE VIII: False-positive rate on correct programs
    # ------------------------------------------------------------------
    for label, row_label in [("ideal", "fp_ideal"), ("noisy", "fp_noisy"),
                              ("noisy_cal", "fp_noisy_calibrated")]:
        fp_file = shard_dir / f"falsepos_summary_{label}.jsonl"
        if fp_file.exists():
            fp_recs = filter_run_id(load_jsonl(fp_file), run_id)
            fp_subjs = dedup_by(fp_recs, "program_id")
            fp_count = sum(1 for r in fp_subjs.values() if r.get("false_positive"))
            tot = len(fp_subjs)
            ci_lo, ci_hi = wilson_ci(fp_count, tot)
            rows.append(dict(row_id=row_label, cohort="CorrectPrograms",
                             method="QMTester", metric="false_positive_rate",
                             numerator=fp_count, denominator=tot,
                             rate=fp_count / tot if tot else 0,
                             ci_low=ci_lo, ci_high=ci_hi))
        else:
            rows.append(dict(row_id=row_label, cohort="CorrectPrograms",
                             method="QMTester", metric="false_positive_rate",
                             numerator=0, denominator=0, rate=0,
                             ci_low=0.0, ci_high=1.0))

    # ------------------------------------------------------------------
    # RQ3a / TABLE XII: Relation-family ablation on injected faults
    # ------------------------------------------------------------------
    # Order matches SLURM script (run_injected.py uses "_".join(enabled_families), not sorted).
    ablation_configs = [
        ["identity"],
        ["swap"],
        ["phase"],
        ["equivalence"],
        ["identity", "swap"],
        ["identity", "swap", "phase"],
        ["identity", "swap", "phase", "equivalence"],
    ]
    for cfg in ablation_configs:
        label = "_".join(cfg)  # preserve SLURM-script order, not sorted
        # Ablation files have exactly one shard (nshards=1, shard=0).
        # Full-family config uses tag "_abl" to avoid overwriting RQ2 shard 0.
        if len(cfg) == 4:
            abl_pat = f"injected_summary_{label}_shard*_abl.jsonl"
        else:
            abl_pat = f"injected_summary_{label}_shard*.jsonl"
        abl_files = [p for p in sorted(shard_dir.glob(abl_pat))
                     if "shots_" not in p.name and "_bak" not in p.name]
        abl_recs = []
        for p in abl_files:
            abl_recs.extend(filter_run_id(load_jsonl(p), run_id))
        abl_qmt = dedup_by([r for r in abl_recs if r.get("method", "qmtester") == "qmtester"],
                           "mutant_id")
        det = sum(1 for r in abl_qmt.values() if r.get("detected"))
        tot = len(abl_qmt)
        ci_lo, ci_hi = wilson_ci(det, tot) if tot else (None, None)
        row_label = "_".join(sorted(cfg))  # canonical sorted label for CSV row_id
        rows.append(dict(row_id=f"diagnostic_ablation_{row_label}", cohort="DiagnosticInjectedFaults",
                         method=f"QMTester_ablation_{label}", metric="detection_rate",
                         numerator=det, denominator=tot or None,
                         rate=det / tot if tot else None,
                         ci_low=ci_lo, ci_high=ci_hi))

    # ------------------------------------------------------------------
    # RQ4 / TABLE XIV: Shot-count sensitivity
    # ------------------------------------------------------------------
    for shots in [1024, 2048, 4096, 8192]:
        tag = f"shots_{shots}"
        shot_files = sorted(shard_dir.glob(f"injected_summary_{inj_full_label}_shard*_{tag}.jsonl"))
        shot_recs = []
        for p in shot_files:
            shot_recs.extend(filter_run_id(load_jsonl(p), run_id))
        shot_qmt = dedup_by([r for r in shot_recs if r.get("method", "qmtester") == "qmtester"],
                            "mutant_id")
        det = sum(1 for r in shot_qmt.values() if r.get("detected"))
        tot = len(shot_qmt)
        ci_lo, ci_hi = wilson_ci(det, tot) if tot else (None, None)
        rows.append(dict(row_id=f"diagnostic_shots_{shots}", cohort="DiagnosticInjectedFaults",
                         method=f"QMTester_shots_{shots}", metric="detection_rate",
                         numerator=det, denominator=tot or None,
                         rate=det / tot if tot else None,
                         ci_low=ci_lo, ci_high=ci_hi))

    # Validate before writing so a failed derivation cannot leave behind a
    # fresh-looking incomplete canonical CSV.
    _check_required(rows, expected)

    # ------------------------------------------------------------------
    # Write CSV
    # ------------------------------------------------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["row_id", "cohort", "method", "metric",
                  "numerator", "denominator", "rate", "ci_low", "ci_high"]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


DIAGNOSTIC_ROW_IDS = [
    "diagnostic_bugs4q_qmtester",
    "diagnostic_bugs4q_morphq",
    "diagnostic_mcnemar_bugs4q",
    "diagnostic_injected_qmtester",
    "diagnostic_injected_morphq",
    "fp_ideal",
    "fp_noisy",
    "fp_noisy_calibrated",
    "diagnostic_ablation_identity",
    "diagnostic_ablation_swap",
    "diagnostic_ablation_phase",
    "diagnostic_ablation_equivalence",
    "diagnostic_ablation_identity_swap",
    "diagnostic_ablation_identity_phase_swap",
    "diagnostic_ablation_equivalence_identity_phase_swap",
    "diagnostic_shots_1024",
    "diagnostic_shots_2048",
    "diagnostic_shots_4096",
    "diagnostic_shots_8192",
]

PROGRAM_ROW_IDS = [
    "program_bugs4q_qmtester",
    "program_bugs4q_morphq",
    "program_injected_qmtester",
    "program_injected_morphq",
    "program_fp_fixed",
    "program_ablation_program_input_permutation",
    "program_ablation_program_classical_remap",
    "program_ablation_program_qft_round_trip",
    "program_ablation_program_parameter_periodicity",
    "program_ablation_program_ancilla_uncompute",
]

REQUIRED_ROW_IDS = DIAGNOSTIC_ROW_IDS + PROGRAM_ROW_IDS


def _check_required(rows: List[dict], expected: dict) -> None:
    required = []
    if expected.get("bugs4q") is not None or expected.get("injected") is not None:
        required.extend(DIAGNOSTIC_ROW_IDS)
    if (
        expected.get("program_bugs4q") is not None
        or expected.get("program_injected") is not None
        or expected.get("program_fixed") is not None
    ):
        required.extend(PROGRAM_ROW_IDS)
    if not required:
        required = REQUIRED_ROW_IDS
    present = {r["row_id"] for r in rows}
    missing = [rid for rid in required if rid not in present]
    if missing:
        print(f"FATAL: missing required rows: {missing}", file=sys.stderr)
        sys.exit(1)
    for row in rows:
        rid = row["row_id"]
        if rid == "diagnostic_mcnemar_bugs4q":
            continue
        if row.get("denominator") in (None, "", 0):
            if rid in required:
                print(f"FATAL: row {rid} has missing/zero denominator", file=sys.stderr)
                sys.exit(1)
            continue
        want = None
        if rid in ("diagnostic_bugs4q_qmtester", "diagnostic_bugs4q_morphq"):
            want = expected.get("bugs4q")
        elif rid in ("diagnostic_injected_qmtester", "diagnostic_injected_morphq"):
            want = expected.get("injected")
        elif rid.startswith("fp_"):
            want = expected.get("correct")
        elif rid.startswith("diagnostic_ablation_"):
            want = expected.get("ablation")
        elif rid.startswith("diagnostic_shots_"):
            want = expected.get("shots")
        elif rid in ("program_bugs4q_qmtester", "program_bugs4q_morphq"):
            want = expected.get("program_bugs4q")
        elif rid in ("program_injected_qmtester", "program_injected_morphq"):
            want = expected.get("program_injected")
        elif rid.startswith("program_ablation_"):
            want = expected.get("program_injected")
        elif rid == "program_fp_fixed":
            want = expected.get("program_fixed")
        if want is not None and int(row["denominator"]) != int(want):
            print(
                f"FATAL: row {rid} denominator {row['denominator']} != expected {want}",
                file=sys.stderr,
            )
            sys.exit(1)
    print("Canonical integrity check: PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--shard_dir", default="data/results/shards")
    p.add_argument("--raw", default="data/results/raw_runs.jsonl",
                   help="Ignored — kept for backwards compat with old reduce script")
    p.add_argument("--out", default="data/results/canonical_results.csv")
    p.add_argument("--run_id", default=None)
    p.add_argument("--expected_bugs4q", type=int, default=None)
    p.add_argument("--expected_injected", type=int, default=None)
    p.add_argument("--expected_correct", type=int, default=None)
    p.add_argument("--expected_ablation", type=int, default=None)
    p.add_argument("--expected_shots", type=int, default=None)
    p.add_argument("--expected_program_bugs4q", type=int, default=None)
    p.add_argument("--expected_program_injected", type=int, default=None)
    p.add_argument("--expected_program_fixed", type=int, default=None)
    args = p.parse_args()
    root = Path(args.root)
    expected = {
        "bugs4q": args.expected_bugs4q,
        "injected": args.expected_injected,
        "correct": args.expected_correct,
        "ablation": args.expected_ablation,
        "shots": args.expected_shots,
        "program_bugs4q": args.expected_program_bugs4q,
        "program_injected": args.expected_program_injected,
        "program_fixed": args.expected_program_fixed,
    }
    try:
        derive(root, root / args.shard_dir, root / args.out, args.run_id, expected)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
