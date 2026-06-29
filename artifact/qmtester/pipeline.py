"""QMTester detection pipeline — Algorithm 1.

Inputs:
  subjects S, relations R, backend b, shots n, seeds, timeout tau, alpha.
Outputs:
  per-pair logs, source decisions, rejected relation records.

Usage::

    from qmtester.pipeline import run_subject
    result = run_subject(
        subject_id="b01",
        source_qc=qc,
        families=FAMILIES_DEFAULT,
        backend_name="aer_simulator",
        shots=4096,
        seed=20240519,
        alpha=0.05,
        noise_model=None,
        calibrate=False,
        log_path=Path("data/results/raw_runs.jsonl"),
    )
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import DEFAULT_ALPHA, DEFAULT_SHOTS, DEFAULT_TIMEOUT, CALIBRATION_K, MASTER_SEED
from .canonicalize import canonicalize
from .circuit_io import NormalizedCircuit, normalize
from .execute import execute_circuit, execute_pair
from .logging_utils import append_jsonl, record
from .oracle.calibration import calibrate_threshold, calibrated_p_value, compute_null_chi2s
from .oracle.chisq import two_sample_test
from .oracle.correction import apply_bonferroni, bonferroni_threshold
from .relations import enumerate_admitted, RelationFamily
from qiskit import QuantumCircuit


@dataclass
class PairResult:
    candidate_name: str
    family: str
    p_value: float
    detected_pair: bool
    sparse: bool
    fallback_required: bool
    timeout: bool
    unsupported: bool


@dataclass
class SubjectResult:
    subject_id: str
    admitted_pairs: List[PairResult] = field(default_factory=list)
    rejected_count: int = 0
    detected: bool = False
    corrected_alpha: float = 0.0
    min_p: float = 1.0
    timeout: bool = False
    unsupported: bool = False
    unsupported_reason: Optional[str] = None


def run_subject(
    subject_id: str,
    source_qc: QuantumCircuit,
    families: List[RelationFamily],
    backend_name: str = "aer_simulator",
    shots: int = DEFAULT_SHOTS,
    seed: int = MASTER_SEED,
    alpha: float = DEFAULT_ALPHA,
    noise_model=None,
    calibrate: bool = False,
    log_path: Optional[Path] = None,
    enabled_families: Optional[List[str]] = None,
    run_id: Optional[str] = None,
) -> SubjectResult:
    """Run Algorithm 1 for a single source circuit."""
    t_start = time.monotonic()
    rng_enum = np.random.default_rng(seed)
    rng_stat = np.random.default_rng(seed + 1)

    result = SubjectResult(subject_id=subject_id)

    # Stage 1: normalize.
    norm = normalize(source_qc)

    # Filter families if requested (ablation).
    active_families = [
        f for f in families
        if enabled_families is None or f.name in enabled_families
    ]

    # Stages 2-3: enumerate and admit follow-ups.
    admitted, rejected = enumerate_admitted(norm, active_families, rng_enum)
    result.rejected_count = len(rejected)

    if not admitted:
        result.unsupported = True
        result.unsupported_reason = "no_admitted_followups"
        return result

    m = len(admitted)
    corrected_alpha = bonferroni_threshold(alpha, m)
    result.corrected_alpha = corrected_alpha

    # Calibration (noisy backend): K=20 seeds for source circuit.
    null_chi2s: Optional[List[float]] = None
    calibrated_tau: Optional[float] = None
    if calibrate and noise_model is not None:
        seed_counts = []
        for k in range(CALIBRATION_K):
            cal_seed = seed + 10000 + k
            cnt = execute_circuit(source_qc, shots=shots, seed=cal_seed, noise_model=noise_model)
            if cnt is not None:
                seed_counts.append(cnt)
        if len(seed_counts) >= 2:
            null_chi2s = compute_null_chi2s(seed_counts, shots)
            calibrated_tau = calibrate_threshold(null_chi2s, corrected_alpha)
            if log_path:
                append_jsonl(log_path, {
                    "record_type": "calibration",
                    "run_id": run_id,
                    "subject_id": subject_id,
                    "backend": backend_name,
                    "shots": shots,
                    "seed": seed,
                    "noise_model": str(noise_model) if noise_model else None,
                    "corrected_alpha": corrected_alpha,
                    "calibrated_threshold": calibrated_tau,
                    "calibration_runs": len(seed_counts),
                    "calibration_counts": seed_counts,
                    "null_chi2s": null_chi2s,
                })

    # Stage 4-6: execute + canonicalize + oracle.
    pair_p_values: List[float] = []
    for cand in admitted:
        t0 = time.monotonic()
        src_counts, fu_counts = execute_pair(
            norm.qc, cand.followup,
            shots=shots, seed=seed,
            noise_model=noise_model, timeout=DEFAULT_TIMEOUT,
        )

        if src_counts is None or fu_counts is None:
            pr = PairResult(
                candidate_name=cand.name, family=cand.family,
                p_value=1.0, detected_pair=False,
                sparse=False, fallback_required=False,
                timeout=True, unsupported=False,
            )
            result.admitted_pairs.append(pr)
            if log_path:
                _write_log(log_path, subject_id, norm, cand, corrected_alpha, m,
                           backend_name, shots, seed, noise_model, calibrated_tau,
                           {}, {}, 1.0, False, False, 1.0, True, False, rejected,
                           time.monotonic() - t0, run_id=run_id)
            continue

        ok, reason, src_can, fu_can = canonicalize(src_counts, fu_counts, cand.canon_map)
        if not ok:
            # Canonicalization failure = coverage loss (logged as rejected).
            pr = PairResult(
                candidate_name=cand.name, family=cand.family,
                p_value=1.0, detected_pair=False,
                sparse=False, fallback_required=False,
                timeout=False, unsupported=True,
            )
            result.admitted_pairs.append(pr)
            continue

        stat = two_sample_test(src_can, fu_can, corrected_alpha, rng_stat)

        # Choose final p-value: calibrated or asymptotic/fallback.
        if calibrated_tau is not None and null_chi2s is not None:
            p_final = calibrated_p_value(stat.chi2, null_chi2s)
        else:
            p_final = stat.p_value

        pair_detected = p_final < corrected_alpha
        pair_p_values.append(p_final)
        rt = time.monotonic() - t0

        pr = PairResult(
            candidate_name=cand.name, family=cand.family,
            p_value=p_final, detected_pair=pair_detected,
            sparse=stat.sparse, fallback_required=stat.fallback_required,
            timeout=False, unsupported=False,
        )
        result.admitted_pairs.append(pr)

        if log_path:
            _write_log(
                log_path, subject_id, norm, cand, corrected_alpha, m,
                backend_name, shots, seed, noise_model, calibrated_tau,
                src_can, fu_can, stat.chi2, stat.sparse, stat.fallback_required,
                p_final, False, pair_detected, rejected, rt,
                dof=stat.degrees_of_freedom, raw_p=stat.p_asymptotic,
                merged=stat.merged_categories,
                run_id=run_id,
            )

    # Source-level decision.
    result.detected = apply_bonferroni(alpha, pair_p_values)
    result.min_p = min(pair_p_values, default=1.0)
    return result


def _write_log(
    log_path, subject_id, norm, cand, corrected_alpha, m,
    backend_name, shots, seed, noise_model, calibrated_tau,
    src_can, fu_can, chi2, sparse, fallback_required,
    p_value, timeout, detected, rejected,
    runtime, dof=0, raw_p=1.0, merged=0, run_id=None,
):
    rec = record(
        subject_id=subject_id,
        source_program=subject_id,
        followup_program=cand.name,
        relation_family=cand.family,
        candidate_name=cand.name,
        backend=backend_name,
        shots=shots,
        seed=seed,
        noise_model=str(noise_model) if noise_model else None,
        canonical_counts_src=src_can,
        canonical_counts_fu=fu_can,
        chi2=chi2,
        degrees_of_freedom=dof,
        raw_p_value=raw_p,
        sparse_policy="exact_or_resample" if sparse else "asymptotic",
        fallback_required=fallback_required,
        fallback_p_value=p_value if fallback_required else None,
        num_pairs=m,
        corrected_alpha=corrected_alpha,
        correction_family="bonferroni",
        calibrated_threshold=calibrated_tau,
        calibration_runs=CALIBRATION_K if calibrated_tau else None,
        p_value=p_value,
        detected=detected,
        false_positive=None,
        timeout=timeout,
        unsupported=False,
        unsupported_reason=None,
        rejected_pairs=[{"name": r.name, "reason": r.reason} for r in rejected],
        merged_categories=merged,
        runtime_seconds=runtime,
        extra={"record_type": "pair", "run_id": run_id},
    )
    append_jsonl(log_path, rec)
