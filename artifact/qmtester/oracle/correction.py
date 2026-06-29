"""Multiple-testing correction (Sec. III-F, Proposition 1).

Bonferroni: per-source correction over m admitted follow-up pairs.
Holm step-down: sensitivity check (not used for headline decisions, Sec. III-F).
"""
from __future__ import annotations

from typing import List


def bonferroni_threshold(alpha: float, m: int) -> float:
    """Per-pair Bonferroni threshold alpha/m for a source with m admitted pairs."""
    if m <= 0:
        return alpha
    return alpha / m


def holm_threshold(alpha: float, p_values: List[float]) -> float:
    """Smallest per-pair Holm threshold for the full set of p-values (sensitivity).

    Returns the threshold for the *most significant* pair: alpha / m.
    (Holm applies alpha/(m-i+1) to the i-th smallest p; for checking if any pair
    triggers, only the first rank matters so threshold = alpha/m.)
    """
    m = len(p_values)
    if m == 0:
        return alpha
    return alpha / m


def apply_bonferroni(alpha: float, p_values: List[float]) -> bool:
    """Source-level detection decision: True if any p_i < alpha/m (Bonferroni)."""
    m = len(p_values)
    if m == 0:
        return False
    thresh = bonferroni_threshold(alpha, m)
    return any(p < thresh for p in p_values)
