#!/bin/bash
#SBATCH --job-name=qmt_ablation
#SBATCH --partition=milan
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=1:00:00
#SBATCH --array=0-6          # 7 ablation configs x Bugs4Q
#SBATCH --output=slurm/logs/03_ablation_%A_%a.out
#SBATCH --error=slurm/logs/03_ablation_%A_%a.err

# RQ3a: relation-family ablation (Table XII, Fig. 3).
# 7 configs: I, S, Ph, E, I+S, I+S+Ph, I+S+Ph+E on the audited Bugs4Q
# runnable set + injected mutants.

set -euo pipefail
ROOT=/fred/oz402/nhunguyen/ICSE_QMTester
APP=/apps/system/software/apptainer/latest/bin/apptainer
SIF=$ROOT/containers/qmtester.sif
CFG_IDX=$SLURM_ARRAY_TASK_ID
RUN_ID=${QMT_RUN_ID:-legacy_mixed}
if [ -z "${QMT_RUN_ID:-}" ]; then
    echo "[$(date)] WARNING: QMT_RUN_ID unset; writing diagnostic output under run legacy_mixed"
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# 7 ablation configurations (Table XII row order)
CONFIGS=(
    "identity"
    "swap"
    "phase"
    "equivalence"
    "identity swap"
    "identity swap phase"
    "identity swap phase equivalence"
)
FAMILIES=${CONFIGS[$CFG_IDX]}
TAG_ARGS=()
if [ "$CFG_IDX" -eq 6 ]; then
    TAG_ARGS=(--tag abl)
fi
echo "[$(date)] Ablation config $CFG_IDX: $FAMILIES"

mkdir -p "$ROOT/slurm/logs"
WORK=$JOBFS/qmt_ablation_${CFG_IDX}
mkdir -p "$WORK"

# Run on Bugs4Q subjects.
OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_bugs4q.py \
        --root /work \
        --shard 0 --nshards 1 \
        --shots 4096 --seed 20240519 \
        --out_dir "$WORK/bugs4q" \
        --run_id "$RUN_ID" \
        --enabled_families $FAMILIES

# Run on injected faults.
OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_injected.py \
        --root /work \
        --shard 0 --nshards 1 \
        --shots 4096 --seed 20240519 \
        --out_dir "$WORK/injected" \
        --run_id "$RUN_ID" \
        "${TAG_ARGS[@]}" \
        --enabled_families $FAMILIES

OUT=$ROOT/data/results/runs/$RUN_ID/shards
mkdir -p "$OUT"
cp -v "$WORK"/injected/*.jsonl "$OUT/" 2>/dev/null || true
echo "[$(date)] ablation cfg=$CFG_IDX done."
