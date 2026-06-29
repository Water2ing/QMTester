"""Per-pair raw log records (data/results/raw_runs.jsonl).

Every admitted pair writes one JSON line containing every field that
Table VII / Table IX require (seeds, count vectors, chi2, p-values,
sparse decision, fallback p, corrected threshold, decision label).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def record(
    *,
    subject_id: str,
    source_program: str,
    followup_program: str,
    relation_family: str,
    candidate_name: str,
    backend: str,
    shots: int,
    seed: int,
    noise_model: Optional[str],
    canonical_counts_src: Dict[str, int],
    canonical_counts_fu: Dict[str, int],
    chi2: float,
    degrees_of_freedom: int,
    raw_p_value: float,
    sparse_policy: str,
    fallback_required: bool,
    fallback_p_value: Optional[float],
    num_pairs: int,
    corrected_alpha: float,
    correction_family: str,
    calibrated_threshold: Optional[float],
    calibration_runs: Optional[int],
    p_value: float,
    detected: bool,
    false_positive: Optional[bool],
    timeout: bool,
    unsupported: bool,
    unsupported_reason: Optional[str],
    rejected_pairs: List[Dict[str, str]],
    merged_categories: int,
    runtime_seconds: float,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a raw-log dict (one JSONL line)."""
    rec = dict(
        ts=time.time(),
        subject_id=subject_id,
        source_program=source_program,
        followup_program=followup_program,
        relation_family=relation_family,
        candidate_name=candidate_name,
        backend=backend,
        shots=shots,
        seed=seed,
        noise_model=noise_model,
        canonicalized_counts=dict(
            src=canonical_counts_src,
            fu=canonical_counts_fu,
        ),
        statistic=dict(
            chi2=chi2,
            degrees_of_freedom=degrees_of_freedom,
            raw_p_value=raw_p_value,
            sparse_policy=sparse_policy,
            fallback_required=fallback_required,
            fallback_p_value=fallback_p_value,
            merged_categories=merged_categories,
        ),
        correction=dict(
            num_pairs=num_pairs,
            corrected_alpha=corrected_alpha,
            correction_family=correction_family,
        ),
        calibration=dict(
            calibrated_threshold=calibrated_threshold,
            calibration_runs=calibration_runs,
        ),
        p_value=p_value,
        detected=detected,
        false_positive=false_positive,
        timeout=timeout,
        unsupported=unsupported,
        unsupported_reason=unsupported_reason,
        rejected_pairs=rejected_pairs,
        runtime_seconds=runtime_seconds,
    )
    if extra:
        rec.update(extra)
    return rec


def append_jsonl(path: Path, rec: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")
