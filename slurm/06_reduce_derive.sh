#!/bin/bash
#SBATCH --job-name=qmt_reduce
#SBATCH --partition=milan
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=0:15:00
#SBATCH --output=slurm/logs/06_reduce_%j.out
#SBATCH --error=slurm/logs/06_reduce_%j.err
#SBATCH --dependency=singleton   # Run after all qmt_* jobs finish

# Final reduce: concatenate shards -> raw_runs.jsonl -> canonical_results.csv.
# Dependency on 'singleton' ensures all array tasks of prior jobs finish first.
# Submit with: sbatch --dependency=afterok:<job1>,<job2>,<job3> slurm/06_reduce_derive.sh

set -euo pipefail
ROOT=/fred/oz402/nhunguyen/ICSE_QMTester
APP=/apps/system/software/apptainer/latest/bin/apptainer
SIF=$ROOT/containers/qmtester.sif
RUN_ID=${QMT_RUN_ID:-legacy_mixed}
if [ -z "${QMT_RUN_ID:-}" ]; then
    echo "[$(date)] WARNING: QMT_RUN_ID unset; deriving diagnostic output under run legacy_mixed"
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
RUN_DIR=$ROOT/data/results/runs/$RUN_ID
SHARD_DIR=$RUN_DIR/shards
EXPECTED_BUGS4Q=$(python - <<'PY'
import csv
with open("/fred/oz402/nhunguyen/ICSE_QMTester/data/manifests/bugs4q_manifest.csv", newline="") as f:
    print(sum(1 for row in csv.DictReader(f) if row.get("runnable") == "true"))
PY
)
EXPECTED_INJECTED=$(($(wc -l < "$ROOT/data/manifests/injected_mutants.csv") - 1))
EXPECTED_CORRECT=50
EXPECTED_PROGRAM_BUGS4Q=$(($(wc -l < "$ROOT/data/manifests/program_bugs4q_manifest.csv") - 1))
EXPECTED_PROGRAM_INJECTED=$(($(wc -l < "$ROOT/data/manifests/program_mutants_manifest.csv") - 1))
EXPECTED_PROGRAM_FIXED=$((EXPECTED_PROGRAM_BUGS4Q + EXPECTED_PROGRAM_INJECTED))

echo "[$(date)] Reducing shards..."
$APP exec --bind "$ROOT:/work" "$SIF" python /work/scripts/reduce.py \
    --root /work \
    --shard_dir /work/data/results/runs/$RUN_ID/shards \
    --out data/results/runs/$RUN_ID/raw_runs.jsonl

echo "[$(date)] Deriving canonical metrics..."
$APP exec --bind "$ROOT:/work" "$SIF" python /work/scripts/derive_metrics.py \
    --root /work \
    --shard_dir data/results/runs/$RUN_ID/shards \
    --out data/results/runs/$RUN_ID/canonical_results.csv \
    --run_id "$RUN_ID" \
    --expected_bugs4q "$EXPECTED_BUGS4Q" \
    --expected_injected "$EXPECTED_INJECTED" \
    --expected_correct "$EXPECTED_CORRECT" \
    --expected_ablation "$EXPECTED_INJECTED" \
    --expected_shots "$EXPECTED_INJECTED" \
    --expected_program_bugs4q "$EXPECTED_PROGRAM_BUGS4Q" \
    --expected_program_injected "$EXPECTED_PROGRAM_INJECTED" \
    --expected_program_fixed "$EXPECTED_PROGRAM_FIXED"

echo "[$(date)] Done. Canonical CSV at $RUN_DIR/canonical_results.csv"
