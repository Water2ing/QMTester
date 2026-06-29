# `data/results/` — which canonical CSV is authoritative

This note disambiguates the two `canonical_results.csv` files in this tree.

## AUTHORITATIVE program-level results

- **`paper_ready/program_v1/canonical_results.csv`** — the frozen, paper-ready
  program-level canonical (with `SHA256SUMS.txt`). Contains every headline number:
  - `program_bugs4q_qmtester` 7/7, `program_bugs4q_morphq` 0/7
  - `program_injected_qmtester` 100/100, `program_injected_morphq` 20/100
  - `program_fp_fixed` 0/107
  - `fp_ideal` / `fp_noisy` / `fp_noisy_calibrated` 0/50 each
  - diagnostic (appendix): `diagnostic_bugs4q_*` 2/32, `diagnostic_injected_*` 17/250
- Backing raw logs + shards:
  `runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z/` (`canonical_results.csv`,
  `raw_runs.jsonl`, `shards/`). This run's `canonical_results.csv` equals the
  paper_ready copy.

## NOT authoritative — do not use

- **`canonical_results.csv` (this directory, top level)** — STALE. It is the *default
  output path* hard-wired into the `Makefile` (`CSV :=`) and
  `scripts/derive_metrics.py` (`--out` default), and currently holds an old
  circuit-level diagnostic run (Bugs4Q 1/18, injected 21/250). It is left in place so
  `make` does not break. Regenerate the program-level canonical by passing
  `--out paper_ready/program_v1/canonical_results.csv`.

## Reproduce the headline numbers

```bash
python scripts/derive_metrics.py \
  --root . \
  --shard_dir data/results/runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z/shards \
  --out data/results/runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z/canonical_results.csv \
  --run_id redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z \
  --expected_program_bugs4q 7 --expected_program_injected 100 --expected_program_fixed 107 \
  --expected_bugs4q 32 --expected_injected 250 --expected_correct 50 \
  --expected_ablation 250 --expected_shots 250
```

Oracle-behavior statistics (permutation/asymptotic branch usage + empirical type-I):

```bash
python scripts/analyze_oracle_and_typeI.py
```
