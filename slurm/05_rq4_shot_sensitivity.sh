#!/bin/bash
#SBATCH --job-name=qmt_shots
#SBATCH --partition=milan
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=1:00:00
#SBATCH --array=0-3          # 4 shot budgets: 1024, 2048, 4096, 8192
#SBATCH --output=slurm/logs/05_shots_%A_%a.out
#SBATCH --error=slurm/logs/05_shots_%A_%a.err

# RQ4: shot-count sensitivity (Table XIV) on 250 injected-fault variants.

set -euo pipefail
ROOT=/fred/oz402/nhunguyen/ICSE_QMTester
APP=/apps/system/software/apptainer/latest/bin/apptainer
SIF=$ROOT/containers/qmtester.sif
RUN_ID=${QMT_RUN_ID:-legacy_mixed}
if [ -z "${QMT_RUN_ID:-}" ]; then
    echo "[$(date)] WARNING: QMT_RUN_ID unset; writing diagnostic output under run legacy_mixed"
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

SHOT_BUDGETS=(1024 2048 4096 8192)
SHOTS=${SHOT_BUDGETS[$SLURM_ARRAY_TASK_ID]}
echo "[$(date)] Shot budget: $SHOTS"

mkdir -p "$ROOT/slurm/logs"
WORK=$JOBFS/qmt_shots_${SHOTS}
mkdir -p "$WORK"

OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_injected.py \
        --root /work \
        --shard 0 --nshards 1 \
        --shots $SHOTS --seed 20240519 \
        --out_dir "$WORK" \
        --run_id "$RUN_ID" \
        --tag shots_${SHOTS} \
        --enabled_families identity swap phase equivalence

OUT=$ROOT/data/results/runs/$RUN_ID/shards
mkdir -p "$OUT"
cp -v "$WORK"/*.jsonl "$OUT/" 2>/dev/null || true
echo "[$(date)] shot=$SHOTS done."
