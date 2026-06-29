"""Oracle-behavior and empirical type-I statistics for QMTester (computed from
existing logs only; does not alter any baseline or run new experiments).

Computes two quantities:

  (1) Oracle branch usage: fraction of admitted program-level pairs that took the
      Monte-Carlo permutation fallback vs the asymptotic chi-squared branch, plus the
      Cochran cell-merging histogram.
  (2) Empirical null p-value / type-I behaviour on correct programs under
      ideal/noisy/calibrated-noisy simulators, with a KS uniformity test
      (the "valid null p-values" premise of Proposition 1).

Usage:
    python scripts/analyze_oracle_and_typeI.py \
        [--run data/results/runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z]

Source of truth: the canonical program-level run.
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scipy import stats as _sp
except Exception:  # pragma: no cover
    _sp = None

DEFAULT_RUN = "data/results/runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z"


def _stat(d):
    return d.get("statistic") or {}


def _iter(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except Exception:
                continue


def oracle_branch_usage(path: Path, label: str):
    n = fb = det = 0
    pol = Counter()
    merged = Counter()
    fam = defaultdict(lambda: [0, 0])  # name -> [n, fallback]
    pvals = []
    for d in _iter(path):
        rf = str(d.get("relation_family") or "")
        if not rf.startswith("program_"):
            continue
        s = _stat(d)
        if not s:
            continue
        n += 1
        req = bool(s.get("fallback_required"))
        fb += req
        pol[s.get("sparse_policy")] += 1
        merged[int(s.get("merged_categories") or 0)] += 1
        fam[rf][0] += 1
        fam[rf][1] += int(req)
        det += int(bool(d.get("detected")))
        if d.get("p_value") is not None:
            pvals.append(float(d["p_value"]))
    print(f"--- {label}  (file: {path.name}) ---")
    if not n:
        print("  no program-level pairs found\n")
        return
    print(f"  program-level pairs : {n}   detected (pair-level): {det}")
    print(f"  permutation fallback: {fb}/{n} ({fb/n:.1%})   asymptotic chi2: {n-fb} ({(n-fb)/n:.1%})")
    print(f"  sparse_policy       : {dict(pol)}")
    print(f"  merged_categories   : {dict(sorted(merged.items()))}  (0 => Cochran merge never fired)")
    for k in sorted(fam):
        print(f"    {k:<34} fallback {fam[k][1]:>3}/{fam[k][0]}")
    if pvals:
        print(f"  pair p min/median/max: {min(pvals):.2e} / {statistics.median(pvals):.3f} / {max(pvals):.3f}")
    print()


def null_pvalues(path: Path, label: str):
    pvals = []
    fb = n = 0
    subjects = set()
    for d in _iter(path):
        p = d.get("p_value")
        if p is None:
            continue
        n += 1
        subjects.add(d.get("subject_id"))
        pvals.append(float(p))
        fb += int(bool(_stat(d).get("fallback_required")))
    if not n:
        print(f"[{label}] no per-pair p-values\n")
        return
    lt05 = sum(1 for v in pvals if v < 0.05)
    lt01 = sum(1 for v in pvals if v < 0.01)
    ks = ""
    if _sp is not None and len(pvals) >= 5:
        D, pv = _sp.kstest(pvals, "uniform")
        ks = f"  KS vs Uniform(0,1): D={D:.3f}, p={pv:.3f}"
    print(f"[{label}]  subjects={len(subjects)}  per-pair tests={n}")
    print(f"  uncorrected p<0.05 : {lt05}/{n} ({lt05/n:.2%})    p<0.01 : {lt01}/{n} ({lt01/n:.2%})")
    print(f"  p min/median/max   : {min(pvals):.3f} / {statistics.median(pvals):.3f} / {max(pvals):.3f}")
    print(f"  permutation branch : {fb}/{n} ({fb/n:.1%})")
    if ks:
        print(ks)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=DEFAULT_RUN)
    args = ap.parse_args()
    shards = Path(args.run) / "shards"

    print("=" * 72)
    print("(1) ORACLE BRANCH USAGE ON PROGRAM-LEVEL DETECTION PAIRS")
    print("=" * 72)
    oracle_branch_usage(shards / "program_bugs4q.jsonl", "Bugs4Q program pairs (buggy+fixed)")
    oracle_branch_usage(shards / "program_injected_full.jsonl", "Injected program mutant pairs")

    print("=" * 72)
    print("(2) NULL P-VALUE / TYPE-I BEHAVIOUR ON CORRECT PROGRAMS")
    print("=" * 72)
    for label, fn in (("ideal", "falsepos_ideal.jsonl"),
                      ("noisy", "falsepos_noisy.jsonl"),
                      ("noisy_cal", "falsepos_noisy_cal.jsonl")):
        null_pvalues(shards / fn, label)

    print("scipy available:", _sp is not None)


if __name__ == "__main__":
    main()
