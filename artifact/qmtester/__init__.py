"""QMTester: statistically disciplined metamorphic testing for quantum programs.

Package layout mirrors the paper's five-stage workflow (Fig. 1, Algorithm 1):
  circuit_io     - Stage 1: normalize source circuit metadata.
  relations/     - Stage 2/3: enumerate + admit follow-ups (four relation families).
  execute        - Stage 4: matched paired execution.
  canonicalize   - Stage 5: output-bit remapping.
  oracle/        - Stage 6: calibrated two-sample chi-squared + correction.
  pipeline       - Stage 7: Algorithm 1 detection pipeline + decision/logs.
"""

MASTER_SEED = 20240519
DEFAULT_SHOTS = 4096
DEFAULT_ALPHA = 0.05
DEFAULT_TIMEOUT = 600.0
PERMUTATION_B = 10000
CALIBRATION_K = 20

__all__ = [
    "MASTER_SEED",
    "DEFAULT_SHOTS",
    "DEFAULT_ALPHA",
    "DEFAULT_TIMEOUT",
    "PERMUTATION_B",
    "CALIBRATION_K",
]
