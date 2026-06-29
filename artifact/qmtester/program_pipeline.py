"""Program-level QMTester pipeline."""
from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

import numpy as np

from . import DEFAULT_ALPHA, DEFAULT_SHOTS, DEFAULT_TIMEOUT, MASTER_SEED
from .canonicalize import canonicalize
from .execute import execute_pair
from .logging_utils import append_jsonl, record
from .oracle.chisq import two_sample_test
from .oracle.correction import apply_bonferroni, bonferroni_threshold
from .pipeline import PairResult, SubjectResult
from .program_subject import ProgramRelation, ProgramSubject
from .soundness import check_relation_soundness


def run_program_subject(
    subject: ProgramSubject,
    families: List[ProgramRelation],
    backend_name: str = "aer_simulator",
    shots: int = DEFAULT_SHOTS,
    seed: int = MASTER_SEED,
    alpha: float = DEFAULT_ALPHA,
    noise_model=None,
    log_path: Optional[Path] = None,
    enabled_families: Optional[List[str]] = None,
    run_id: Optional[str] = None,
) -> SubjectResult:
    """Run program-level relations for one subject."""
    rng_enum = np.random.default_rng(seed)
    rng_stat = np.random.default_rng(seed + 1)
    result = SubjectResult(subject_id=subject.subject_id)

    active = [f for f in families if enabled_families is None or f.name in enabled_families]
    candidates = []
    for family in active:
        if subject.relations and family.name not in subject.relations:
            continue
        candidates.extend(family.enumerate(subject, rng_enum))

    if not candidates:
        result.unsupported = True
        result.unsupported_reason = "no_program_relation_candidates"
        return result

    corrected_alpha = bonferroni_threshold(alpha, len(candidates))
    result.corrected_alpha = corrected_alpha
    pair_p_values = []

    for cand in candidates:
        t0 = time.monotonic()
        try:
            src_qc = subject.build(cand.source_input)
            fu_qc = subject.build(cand.followup_input)
        except Exception as exc:
            result.rejected_count += 1
            result.admitted_pairs.append(PairResult(
                candidate_name=cand.name,
                family=cand.family,
                p_value=1.0,
                detected_pair=False,
                sparse=False,
                fallback_required=False,
                timeout=False,
                unsupported=True,
            ))
            if log_path:
                append_jsonl(log_path, {
                    "record_type": "program_rejected",
                    "run_id": run_id,
                    "subject_id": subject.subject_id,
                    "candidate_name": cand.name,
                    "relation_family": cand.family,
                    "reason": f"BUILD_ERROR:{type(exc).__name__}:{exc}",
                })
            continue

        # Admission: reject relation declarations that are unsound for the built
        # circuit (e.g. a 2pi periodicity shift on a controlled Pauli rotation,
        # whose true period is 4pi) before any statistical test (Table II).
        admissible, admit_reason = check_relation_soundness(cand, src_qc)
        if not admissible:
            result.rejected_count += 1
            result.admitted_pairs.append(PairResult(
                candidate_name=cand.name,
                family=cand.family,
                p_value=1.0,
                detected_pair=False,
                sparse=False,
                fallback_required=False,
                timeout=False,
                unsupported=True,
            ))
            if log_path:
                append_jsonl(log_path, {
                    "record_type": "program_rejected",
                    "run_id": run_id,
                    "subject_id": subject.subject_id,
                    "candidate_name": cand.name,
                    "relation_family": cand.family,
                    "reason": admit_reason,
                })
            continue

        src_counts, fu_counts = execute_pair(
            src_qc,
            fu_qc,
            shots=shots,
            seed=seed,
            noise_model=noise_model,
            timeout=DEFAULT_TIMEOUT,
        )
        if src_counts is None or fu_counts is None:
            result.admitted_pairs.append(PairResult(
                candidate_name=cand.name,
                family=cand.family,
                p_value=1.0,
                detected_pair=False,
                sparse=False,
                fallback_required=False,
                timeout=True,
                unsupported=False,
            ))
            continue

        ok, reason, src_can, fu_can = canonicalize(src_counts, fu_counts, cand.canon_map)
        if not ok:
            result.rejected_count += 1
            result.admitted_pairs.append(PairResult(
                candidate_name=cand.name,
                family=cand.family,
                p_value=1.0,
                detected_pair=False,
                sparse=False,
                fallback_required=False,
                timeout=False,
                unsupported=True,
            ))
            if log_path:
                append_jsonl(log_path, {
                    "record_type": "program_rejected",
                    "run_id": run_id,
                    "subject_id": subject.subject_id,
                    "candidate_name": cand.name,
                    "relation_family": cand.family,
                    "reason": reason,
                })
            continue

        stat = two_sample_test(src_can, fu_can, corrected_alpha, rng_stat)
        detected = stat.p_value < corrected_alpha
        pair_p_values.append(stat.p_value)
        result.admitted_pairs.append(PairResult(
            candidate_name=cand.name,
            family=cand.family,
            p_value=stat.p_value,
            detected_pair=detected,
            sparse=stat.sparse,
            fallback_required=stat.fallback_required,
            timeout=False,
            unsupported=False,
        ))

        if log_path:
            rec = record(
                subject_id=subject.subject_id,
                source_program=str(cand.source_input),
                followup_program=str(cand.followup_input),
                relation_family=cand.family,
                candidate_name=cand.name,
                backend=backend_name,
                shots=shots,
                seed=seed,
                noise_model=str(noise_model) if noise_model else None,
                canonical_counts_src=src_can,
                canonical_counts_fu=fu_can,
                chi2=stat.chi2,
                degrees_of_freedom=stat.degrees_of_freedom,
                raw_p_value=stat.p_asymptotic,
                sparse_policy="exact_or_resample" if stat.sparse else "asymptotic",
                fallback_required=stat.fallback_required,
                fallback_p_value=stat.p_value if stat.fallback_required else None,
                num_pairs=len(candidates),
                corrected_alpha=corrected_alpha,
                correction_family="bonferroni",
                calibrated_threshold=None,
                calibration_runs=None,
                p_value=stat.p_value,
                detected=detected,
                false_positive=None,
                timeout=False,
                unsupported=False,
                unsupported_reason=None,
                rejected_pairs=[],
                merged_categories=stat.merged_categories,
                runtime_seconds=time.monotonic() - t0,
                extra={
                    "record_type": "program_pair",
                    "run_id": run_id,
                    "program_relation_metadata": cand.metadata,
                },
            )
            append_jsonl(log_path, rec)

    result.detected = apply_bonferroni(alpha, pair_p_values)
    result.min_p = min(pair_p_values, default=1.0)
    return result
