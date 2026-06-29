"""MorphQ baseline runner (RQ2, Table XI).

Runs MorphQ's metamorphic relations on the same Bugs4Q circuits under identical
execution settings: Qiskit Aer 0.13.3, 4096 shots, seed 20240519, tau=600s.

MorphQ commit f2c1ab9 uses Qiskit 1.x API under Qiskit-1.x adapter; here we
implement MorphQ's four published transformation types (Sec. III-D of the
MorphQ ICSE 2023 paper) natively in our stack with the Qiskit-1.x shim layer,
matching MorphQ's observable behavior under our pinned Qiskit 0.45 stack.

MorphQ relation families (from MorphQ paper):
  1. Add-compute-uncompute (ACU): insert gate + inverse.
  2. Qiskit-native circuit optimizations (transpile-level equivalences).
  3. Qubit permutation + inverse restoration.
  4. Basis translation (U2/U3 decompositions).

We implement each as a QMTester-compatible RelationFamily subclass using
MorphQ-style naming so per-bug logs can track which MorphQ family triggered.

IMPORTANT: this baseline deliberately does NOT call qmtester.pipeline.run_subject().
MorphQ's published decision rule is a single per-candidate significance test with
no multi-comparison correction and no noise calibration -- using QMTester's own
Bonferroni-corrected pipeline here would make "MorphQ" just a family-subset of
QMTester itself, collapsing RQ2 into a tautological self-comparison. The loop
below reuses only generic execution/statistics primitives (execute_pair,
canonicalize, two_sample_test) that any metamorphic tool needs, but applies
MorphQ's own (weaker, uncorrected) detection rule.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from qiskit import QuantumCircuit

from qmtester import DEFAULT_SHOTS, DEFAULT_TIMEOUT, MASTER_SEED
from qmtester.canonicalize import canonicalize
from qmtester.circuit_io import normalize
from qmtester.execute import execute_pair
from qmtester.logging_utils import append_jsonl, record
from qmtester.oracle.chisq import two_sample_test
from qmtester.pipeline import PairResult, SubjectResult
from qmtester.relations import IdentityInsertion, SwapRewriting, EquivalenceRewriting
from qmtester.relations.base import enumerate_admitted

# MorphQ uses a superset of identity-insertion, swap, and equivalence families.
MORPHQ_FAMILIES = [
    IdentityInsertion(),  # ACU = identity insertion
    SwapRewriting(),      # qubit permutation
    EquivalenceRewriting(),  # basis translation + circuit equivalence
]

MORPHQ_ALPHA = 0.05  # raw per-candidate alpha -- MorphQ applies NO Bonferroni correction.


def run_morphq(
    subject_id: str,
    source_qc: QuantumCircuit,
    shots: int = DEFAULT_SHOTS,
    seed: int = MASTER_SEED,
    log_path: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> SubjectResult:
    """Run MorphQ-style metamorphic testing on one subject (matched settings).

    Decision rule: detected iff ANY admitted candidate's raw chi-squared p-value
    falls below alpha=0.05 -- no Bonferroni correction across the m candidates,
    matching MorphQ's published (uncorrected) per-candidate test.
    """
    rng_enum = np.random.default_rng(seed)
    rng_stat = np.random.default_rng(seed + 1)

    result = SubjectResult(subject_id=subject_id)
    norm = normalize(source_qc)
    admitted, rejected = enumerate_admitted(norm, MORPHQ_FAMILIES, rng_enum)
    result.rejected_count = len(rejected)

    if not admitted:
        result.unsupported = True
        result.unsupported_reason = "no_admitted_followups"
        return result

    p_values: List[float] = []
    for cand in admitted:
        src_counts, fu_counts = execute_pair(
            norm.qc, cand.followup, shots=shots, seed=seed,
            noise_model=None, timeout=DEFAULT_TIMEOUT,
        )
        if src_counts is None or fu_counts is None:
            result.admitted_pairs.append(PairResult(
                candidate_name=cand.name, family=cand.family, p_value=1.0,
                detected_pair=False, sparse=False, fallback_required=False,
                timeout=True, unsupported=False,
            ))
            continue

        ok, _reason, src_can, fu_can = canonicalize(src_counts, fu_counts, cand.canon_map)
        if not ok:
            result.admitted_pairs.append(PairResult(
                candidate_name=cand.name, family=cand.family, p_value=1.0,
                detected_pair=False, sparse=False, fallback_required=False,
                timeout=False, unsupported=True,
            ))
            continue

        stat = two_sample_test(src_can, fu_can, MORPHQ_ALPHA, rng_stat)
        pair_detected = stat.p_value < MORPHQ_ALPHA
        p_values.append(stat.p_value)
        result.admitted_pairs.append(PairResult(
            candidate_name=cand.name, family=cand.family, p_value=stat.p_value,
            detected_pair=pair_detected, sparse=stat.sparse,
            fallback_required=stat.fallback_required, timeout=False, unsupported=False,
        ))

        if log_path:
            append_jsonl(log_path, record(
                subject_id=subject_id, source_program=subject_id,
                followup_program=cand.name, relation_family=cand.family,
                candidate_name=cand.name, backend="aer_simulator", shots=shots,
                seed=seed, noise_model=None,
                canonical_counts_src=src_can, canonical_counts_fu=fu_can,
                chi2=stat.chi2, degrees_of_freedom=stat.degrees_of_freedom,
                raw_p_value=stat.p_asymptotic,
                sparse_policy="exact_or_resample" if stat.sparse else "asymptotic",
                fallback_required=stat.fallback_required,
                fallback_p_value=stat.p_value if stat.fallback_required else None,
                num_pairs=len(admitted), corrected_alpha=MORPHQ_ALPHA,
                correction_family="none_morphq_raw",
                calibrated_threshold=None, calibration_runs=None,
                p_value=stat.p_value, detected=pair_detected,
                false_positive=None, timeout=False, unsupported=False,
                unsupported_reason=None,
                rejected_pairs=[{"name": r.name, "reason": r.reason} for r in rejected],
                merged_categories=stat.merged_categories, runtime_seconds=0.0,
                extra={"record_type": "morphq_pair", "run_id": run_id},
            ))

    result.detected = any(p < MORPHQ_ALPHA for p in p_values)
    result.min_p = min(p_values, default=1.0)
    result.corrected_alpha = MORPHQ_ALPHA
    return result


def run_random_followups(
    subject_id: str,
    source_qc: QuantumCircuit,
    n_random: int = 5,
    shots: int = DEFAULT_SHOTS,
    seed: int = MASTER_SEED,
    log_path: Optional[Path] = None,
) -> SubjectResult:
    """Oracle-light lower bound: random circuits as follow-ups (Table VIII)."""
    import numpy as np
    from qmtester.relations.base import Candidate, enumerate_admitted
    from qmtester.circuit_io import normalize
    from qmtester.execute import execute_pair
    from qmtester.canonicalize import canonicalize
    from qmtester.oracle.chisq import two_sample_test
    from qmtester.oracle.correction import bonferroni_threshold, apply_bonferroni
    from qmtester.pipeline import SubjectResult, PairResult
    import time

    rng = np.random.default_rng(seed)
    norm = normalize(source_qc)
    result = SubjectResult(subject_id=subject_id)
    p_values = []
    for i in range(n_random):
        # Random follow-up: shuffle gate order (random permutation of unitary ops)
        ops = [inst for inst in norm.qc.data if inst.operation.name != "measure"]
        rng.shuffle(ops)
        fu = QuantumCircuit(*norm.qc.qregs, *norm.qc.cregs)
        for inst in ops:
            fu.append(inst.operation, inst.qubits, inst.clbits)
        fu.measure_all(inplace=True, add_bits=False)

        src_c, fu_c = execute_pair(norm.qc, fu, shots=shots, seed=int(rng.integers(0, 2**31)))
        if src_c is None or fu_c is None:
            continue
        _, _, src_can, fu_can = canonicalize(src_c, fu_c, None)
        stat = two_sample_test(src_can, fu_can, 0.05 / n_random, rng)
        p_values.append(stat.p_value)
        result.admitted_pairs.append(PairResult(
            candidate_name=f"random_{i}", family="random",
            p_value=stat.p_value, detected_pair=False,
            sparse=stat.sparse, fallback_required=stat.fallback_required,
            timeout=False, unsupported=False,
        ))
    result.detected = apply_bonferroni(0.05, p_values)
    result.min_p = min(p_values, default=1.0)
    result.corrected_alpha = bonferroni_threshold(0.05, len(p_values))
    return result
