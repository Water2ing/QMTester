"""Two-sample chi-squared oracle with sparse-cell handling (Sec. III-F).

Default oracle: Pearson's two-sample chi-squared over the K-bin contingency table.
Sparse-cell handling (two-step rule, Sec. III-F):
  1. Sort bins by e_k ascending. Merge bins with e_k < 5 ("Cochran's rule") into an
     "other" cell until either K' >= 5 and >= 80% of bins have e_k >= 5, then use
     the asymptotic chi-squared p-value.
  2. If condition not satisfied, mark pair sparse=True and use Fisher's exact
     extension (SciPy multinomial_test for q <= 14 and total support <= 256) or
     a B=10,000-permutation Monte-Carlo test on the pooled multinomial.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats

from .. import PERMUTATION_B


@dataclass
class TwoSampleResult:
    chi2: float
    p_asymptotic: float
    degrees_of_freedom: int
    sparse: bool
    p_value: float          # final p: asymptotic or fallback
    fallback_required: bool
    merged_categories: int
    n_src: int
    n_fu: int
    raw_counts_src: List[int]
    raw_counts_fu: List[int]
    keys: List[str]


def two_sample_test(
    src_counts: Dict[str, int],
    fu_counts: Dict[str, int],
    alpha: float,
    rng: np.random.Generator,
    B: int = PERMUTATION_B,
) -> TwoSampleResult:
    """Run the two-sample oracle on aligned count dicts (same key set, sorted)."""
    keys = sorted(src_counts.keys())
    x = np.array([src_counts[k] for k in keys], dtype=np.int64)
    y = np.array([fu_counts[k] for k in keys], dtype=np.int64)
    n_x = int(x.sum())
    n_y = int(y.sum())

    K = len(keys)
    if K == 0 or n_x == 0 or n_y == 0:
        return TwoSampleResult(
            chi2=0.0,
            p_asymptotic=1.0,
            degrees_of_freedom=0,
            sparse=True,
            p_value=1.0,
            fallback_required=False,
            merged_categories=0,
            n_src=n_x,
            n_fu=n_y,
            raw_counts_src=x.tolist(),
            raw_counts_fu=y.tolist(),
            keys=keys,
        )
    chi2, dof, p_asymp, sparse, p_final, fallback, merged = _chisq_with_sparse(
        x, y, n_x, n_y, K, alpha, rng, B
    )
    return TwoSampleResult(
        chi2=chi2,
        p_asymptotic=p_asymp,
        degrees_of_freedom=dof,
        sparse=sparse,
        p_value=p_final,
        fallback_required=fallback,
        merged_categories=merged,
        n_src=n_x,
        n_fu=n_y,
        raw_counts_src=x.tolist(),
        raw_counts_fu=y.tolist(),
        keys=keys,
    )


def _expected(x, y, n_x, n_y):
    pool = x + y
    e_x = pool * n_x / (n_x + n_y)
    e_y = pool * n_y / (n_x + n_y)
    return e_x, e_y


def _chi2_stat(x, y, n_x, n_y):
    e_x, e_y = _expected(x, y, n_x, n_y)
    denom = e_x + e_y
    mask = denom > 0
    chi2 = float(np.sum(((x[mask] - e_x[mask]) ** 2 + (y[mask] - e_y[mask]) ** 2) / denom[mask]))
    return chi2


def _chisq_with_sparse(x, y, n_x, n_y, K, alpha, rng, B):
    e_x, e_y = _expected(x, y, n_x, n_y)
    e_k = e_x + e_y  # total expected per bin

    # --- Step 1: Cochran merge ---
    order = np.argsort(e_k)  # ascending
    merged_x = list(x[order])
    merged_y = list(y[order])
    merged_e = list(e_k[order])
    n_merged = 0

    while len(merged_e) > 2 and merged_e[0] < 5:
        # merge smallest into "other" bin at index 0
        merged_x[1] = merged_x[0] + merged_x[1]
        merged_y[1] = merged_y[0] + merged_y[1]
        merged_e[1] = merged_e[0] + merged_e[1]
        merged_x.pop(0)
        merged_y.pop(0)
        merged_e.pop(0)
        n_merged += 1

    mx = np.array(merged_x, dtype=np.int64)
    my = np.array(merged_y, dtype=np.int64)
    me = np.array(merged_e)
    K_prime = len(mx)
    pct_adequate = float(np.mean(me >= 5))

    chi2 = _chi2_stat(mx, my, n_x, n_y)
    dof = max(K_prime - 1, 1)
    p_asymp = float(stats.chi2.sf(chi2, dof))

    sparse = not (K_prime >= 5 and pct_adequate >= 0.8)

    if not sparse:
        return chi2, dof, p_asymp, False, p_asymp, False, n_merged

    # --- Step 2: Exact / resampling fallback ---
    # Use Fisher's multinomial_test (SciPy >= 1.9) for small circuits,
    # else B=10,000 permutation on the pooled multinomial.
    q_est = int(round(math.log2(K))) if K > 0 else 0
    total_support = int(np.sum((x > 0) | (y > 0)))

    fallback_p = None
    if q_est <= 14 and total_support <= 256:
        try:
            # multinomial_test tests if the observed counts come from a given distribution.
            # We pool and test each sample against the pooled proportions.
            pool = (x + y).astype(float)
            pool_norm = pool / pool.sum() if pool.sum() > 0 else pool
            r = stats.multinomial_test(x, pool_norm)
            fallback_p = float(r.pvalue)
        except Exception:
            fallback_p = None

    if fallback_p is None:
        fallback_p = _permutation_test(x, y, n_x, n_y, chi2, rng, B)

    return chi2, dof, p_asymp, True, fallback_p, True, n_merged


def _permutation_test(x, y, n_x, n_y, obs_chi2, rng, B):
    """Monte-Carlo permutation test: pool n_x + n_y counts, resample B times."""
    pool = x + y
    n_total = n_x + n_y
    K = len(pool)
    probs = pool / pool.sum() if pool.sum() > 0 else np.ones(K) / K

    count_ge = 0
    for _ in range(B):
        perm_x = rng.multinomial(n_x, probs)
        perm_y = rng.multinomial(n_y, probs)
        perm_chi2 = _chi2_stat(perm_x, perm_y, n_x, n_y)
        if perm_chi2 >= obs_chi2:
            count_ge += 1

    # Censored at 1/(B+1) minimum (Sec. III-F)
    p = (count_ge + 1) / (B + 1)
    return float(p)
