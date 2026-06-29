"""Oracle-light program-level baselines.

These baselines isolate what QMTester's two pieces of machinery actually add, by
sharing the program-level metamorphic *rebuild* but stripping one component each:

  - ``same_input``    : rebuild from the SAME input twice, then two-sample chi-squared.
                        No metamorphic transform => tests whether *any* rebuild-and-
                        compare detects bugs (expected: ~0, builds are identical).
  - ``no_canon_chi2`` : metamorphic follow-up + chi-squared, but WITHOUT the bijective
                        canonicalization / admission map. Representation changes
                        (qubit-role relabel, register endianness, QFT relabel) are no
                        longer undone, so the test fires on *both* buggy and fixed
                        variants => loses specificity.
  - ``raw_equality``  : metamorphic follow-up + exact raw count-equality oracle (the
                        trivial "rebuild and compare counts" oracle).

The canonical pipeline in :mod:`qmtester.program_pipeline` is left untouched; this
module only *reuses* its building blocks so the baselines are apples-to-apples
(same enumeration, same execution, same Bonferroni correction unit).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from . import DEFAULT_ALPHA, DEFAULT_SHOTS, DEFAULT_TIMEOUT, MASTER_SEED
from .canonicalize import _align_support, _flatten_counts
from .execute import execute_pair
from .oracle.chisq import two_sample_test
from .oracle.correction import apply_bonferroni, bonferroni_threshold

BASELINE_MODES = ("same_input", "no_canon_chi2", "raw_equality")


@dataclass
class BaselineResult:
    subject_id: str
    mode: str
    detected: bool = False
    n_admitted: int = 0
    n_pairs_flagged: int = 0
    min_p: float = 1.0
    corrected_alpha: float = DEFAULT_ALPHA
    unsupported: bool = False
    unsupported_reason: Optional[str] = None


def run_program_subject_baseline(
    subject,
    families,
    mode: str,
    *,
    shots: int = DEFAULT_SHOTS,
    seed: int = MASTER_SEED,
    alpha: float = DEFAULT_ALPHA,
    enabled_families: Optional[List[str]] = None,
) -> BaselineResult:
    """Run one oracle-light baseline over a program subject's relation candidates."""
    if mode not in BASELINE_MODES:
        raise ValueError(f"unknown baseline mode: {mode!r}")

    rng_enum = np.random.default_rng(seed)
    rng_stat = np.random.default_rng(seed + 1)
    res = BaselineResult(subject_id=subject.subject_id, mode=mode)

    active = [f for f in families if enabled_families is None or f.name in enabled_families]
    candidates = []
    for family in active:
        if subject.relations and family.name not in subject.relations:
            continue
        candidates.extend(family.enumerate(subject, rng_enum))

    if not candidates:
        res.unsupported = True
        res.unsupported_reason = "no_program_relation_candidates"
        return res

    corrected_alpha = bonferroni_threshold(alpha, len(candidates))
    res.corrected_alpha = corrected_alpha
    pair_p_values: List[float] = []

    for cand in candidates:
        try:
            src_qc = subject.build(cand.source_input)
            fu_input = cand.source_input if mode == "same_input" else cand.followup_input
            fu_qc = subject.build(fu_input)
        except Exception:
            continue

        src_counts, fu_counts = execute_pair(
            src_qc, fu_qc, shots=shots, seed=seed, noise_model=None, timeout=DEFAULT_TIMEOUT
        )
        if src_counts is None or fu_counts is None:
            continue

        res.n_admitted += 1
        # Align the RAW supports (union of keys, no bijective remap / no admission).
        sc, fc = _align_support(_flatten_counts(src_counts), _flatten_counts(fu_counts))

        if mode == "raw_equality":
            differs = any(sc[k] != fc.get(k, 0) for k in sc)
            res.n_pairs_flagged += int(differs)
            pair_p_values.append(0.0 if differs else 1.0)
        else:  # same_input or no_canon_chi2
            stat = two_sample_test(sc, fc, corrected_alpha, rng_stat)
            pair_p_values.append(stat.p_value)
            res.n_pairs_flagged += int(stat.p_value < corrected_alpha)

    if mode == "raw_equality":
        res.detected = res.n_pairs_flagged > 0
    else:
        res.detected = apply_bonferroni(alpha, pair_p_values)
    res.min_p = min(pair_p_values, default=1.0)
    return res
