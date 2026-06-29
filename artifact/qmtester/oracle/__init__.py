"""Stage 6: calibrated two-sample statistical oracle.

Components:
  chisq         - Pearson two-sample chi-squared with sparse-cell handling.
  correction    - Bonferroni / Holm multiple-testing correction.
  calibration   - K=20-seed noise calibration for noisy backends.
"""
from .chisq import two_sample_test, TwoSampleResult
from .correction import bonferroni_threshold, holm_threshold
from .calibration import calibrate_threshold

__all__ = [
    "two_sample_test",
    "TwoSampleResult",
    "bonferroni_threshold",
    "holm_threshold",
    "calibrate_threshold",
]
