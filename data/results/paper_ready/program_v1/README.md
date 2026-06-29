# QMTester Paper-Ready Bundle: Program V1

Created: 2026-06-18.
Run ID: `redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z`.

This directory freezes the current paper-candidate evidence bundle.

## Files

- `canonical_results.csv`: canonical metrics derived from run shards.
- `program_bugs4q_manifest.csv`: 7 included audited Bugs4Q program subjects.
- `program_excluded.csv`: 7 audited Bugs4Q exclusions and reasons.
- `program_mutants_manifest.csv`: 100 balanced program-level injected mutants.
- `program_hard_mutants_manifest.csv`: 20 lower-effect supplemental program mutants.
- `PAPER_RESULTS_SUMMARY.md`: current result summary.
- `PAPER_REVISION_NOTES.md`: manuscript rewrite notes.
- `BUGS4Q_RELATION_AUDIT.md`: per-subject relation preconditions and exclusions.
- `ICSE_2027_SCORECARD.md`: original-vs-corrected scorecards and submission decision.
- `RESULTS.md`: full current results after the hard-mutant supplemental run.
- `REFRAMING.md`: corrected paper framing and required manuscript changes.
- `STRUCTURE.md`: actual corrected implementation structure.
- `SHA256SUMS.txt`: checksums for bundle files.

## Main Results

- Program Bugs4Q: QMTester `7/7`, MorphQ `0/7`.
- Program injected mutants: QMTester `100/100`, MorphQ `20/100`.
- Supplemental hard mutants: QMTester `20/20`, MorphQ `0/20`.
- Fixed program variants false positives: `0/107`.
- Correct-program false positives: ideal/noisy/calibrated all `0/50`.

## Diagnostic Appendix Results

- Circuit-level Bugs4Q: QMTester `2/32`, MorphQ `2/32`.
- Circuit-level injected: QMTester `17/250`, MorphQ `17/250`.

## Reproduction Check

From repository root:

```bash
RUN_ID=redesign_hpc_1g_32bugs_fixcounts_20260616T093325Z
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /apps/system/software/apptainer/latest/bin/apptainer exec \
  --bind /fred/oz402/nhunguyen/ICSE_QMTester:/work \
  /fred/oz402/nhunguyen/ICSE_QMTester/containers/qmtester.sif \
  python /work/scripts/derive_metrics.py \
    --root /work \
    --shard_dir data/results/runs/$RUN_ID/shards \
    --out /tmp/qmt_canonical_check.csv \
    --run_id "$RUN_ID" \
    --expected_bugs4q 32 \
    --expected_injected 250 \
    --expected_correct 50 \
    --expected_ablation 250 \
    --expected_shots 250 \
    --expected_program_bugs4q 7 \
    --expected_program_injected 100 \
    --expected_program_fixed 107
```

The expected result is `Canonical integrity check: PASS`.
