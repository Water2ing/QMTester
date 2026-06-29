"""Noisy-simulator calibration (Sec. III-F, step 3).

Separates backend variability from real follow-up deviations. Run the source
circuit P under K=20 independent seeds (same shot budget n), producing K count
vectors x^(1), ..., x^(K). Compute C(K,2)=190 pairwise null chi-squared
statistics chi2_{ij} = chi2(x^(i), x^(j)). Estimate the (1-alpha/m)-quantile of
{chi2_{ij}} as the calibrated threshold tau_P.

A calibrated p-value p-hat = #{j: chi2_j >= chi2_obs} / 190 (censored at 1/191).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np

from .. import CALIBRATION_K
from .chisq import _chi2_stat, _expected


def calibrate_threshold(
    null_chi2s: List[float],
    alpha_over_m: float,
) -> float:
    """Estimate the (1-alpha/m)-quantile from null chi-squared statistics.

    Parameters
    ----------
    null_chi2s:    C(K,2) pairwise null chi-squared values (190 for K=20).
    alpha_over_m:  Bonferroni-corrected per-pair significance level.

    Returns
    -------
    tau_P: calibrated threshold.
    """
    if not null_chi2s:
        return float("inf")
    arr = np.array(null_chi2s)
    q = np.quantile(arr, 1.0 - alpha_over_m)
    return float(q)


def compute_null_chi2s(
    seed_counts: List[Dict[str, int]],
    n: int,
) -> List[float]:
    """Compute all C(K,2) pairwise chi-squared values from K seed executions.

    Parameters
    ----------
    seed_counts: list of K count dicts (each from a different seed, same shots n).
    n:          shots (same for all seeds).

    Returns
    -------
    List of C(K,2) chi-squared statistics.
    """
    K = len(seed_counts)
    # Build aligned arrays over the union of support.
    all_keys = sorted(set(k for d in seed_counts for k in d))
    arrays = []
    for d in seed_counts:
        arrays.append(np.array([d.get(k, 0) for k in all_keys], dtype=np.int64))

    null_chi2s: List[float] = []
    for i in range(K):
        for j in range(i + 1, K):
            x, y = arrays[i], arrays[j]
            chi2 = _chi2_stat(x, y, int(x.sum()), int(y.sum()))
            null_chi2s.append(float(chi2))
    return null_chi2s


def calibrated_p_value(obs_chi2: float, null_chi2s: List[float]) -> float:
    """Calibrated p-hat: fraction of null stats >= obs, censored at 1/(B+1)."""
    if not null_chi2s:
        return 1.0
    B = len(null_chi2s)
    count = sum(1 for v in null_chi2s if v >= obs_chi2)
    return (count + 1) / (B + 1)
