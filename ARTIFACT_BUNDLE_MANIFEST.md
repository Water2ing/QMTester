# Artifact Bundle Manifest

This manifest lists what a complete, self-contained artifact bundle contains and
maps each headline number in the paper to its backing file. Assemble the bundle with:

```
python scripts/assemble_artifact_bundle.py --out artifact_bundle
```

(additive — copies into a new directory, never mutates the source tree).

## Bundle contents

| Bundle path | Source in repo | Purpose |
|---|---|---|
| `tool/qmtester/` | `artifact/qmtester/` | Full tool source (relations, canonicalization, oracle, pipeline, subjects). |
| `tool/scripts/derive_metrics.py` | `scripts/derive_metrics.py` | Regenerates the canonical CSV from shards. |
| `tool/scripts/run_*program*.py` | `scripts/run_bugs4q_program.py`, `run_program_injected.py`, `run_falsepos.py` | Run drivers. |
| `manifests/` | `data/results/paper_ready/program_v1/` (`program_*_manifest.csv`, `program_excluded.csv`) | Frozen subject/mutant manifests. |
| `results/canonical_results.csv` | `data/results/paper_ready/program_v1/canonical_results.csv` | Authoritative program-level canonical CSV (not the stale top-level copy). |
| `results/SHA256SUMS.txt` | `data/results/paper_ready/program_v1/SHA256SUMS.txt` | Integrity hashes. |
| `raw/shards/` | `data/results/runs/redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z/shards/` | Per-(subject, seed, family) summary JSONL consumed by `derive_metrics.py`. |
| `raw/raw_runs.jsonl` | `…/redesign_…/raw_runs.jsonl` | Per-pair records (p-value, sparse branch, chi^2, dof); large, optional. |
| `env/` | container / requirements | Reproduction environment. |

## Headline number to backing file

| Paper claim | Canonical row | Raw backing |
|---|---|---|
| Bugs4Q 7/7 (QMTester) | `program_bugs4q_qmtester` | `shards/program_bugs4q.jsonl` |
| Bugs4Q 0/7 (MorphQ) | `program_bugs4q_morphq` | `shards/program_bugs4q_morphq*.jsonl` |
| Injected 100/100 vs 20/100 | `program_injected_{qmtester,morphq}` | `shards/program_injected_full.jsonl` |
| Fixed-variant FP 0/107 | `program_fp_fixed` | bugs4q + injected fixed pairs |
| Correct-program FP 0/50 (x3) | `fp_ideal`, `fp_noisy`, `fp_noisy_calibrated` | `shards/falsepos_{ideal,noisy,noisy_cal}.jsonl` |
| Diagnostic 2/32, 17/250 | `diagnostic_*` | circuit-level shards |

The three mined subjects (10/10 detection) are in `artifact/qmtester/mined_program_subjects.py`
with provenance in `data/manifests/program_mined_manifest.csv`; their matched baselines are
reproduced by `scripts/run_baselines_on_mined.py`.
