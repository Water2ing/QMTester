#!/bin/bash
#SBATCH --job-name=qmt_injected
#SBATCH --partition=milan
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=0:45:00
#SBATCH --array=0-9          # 10 shards for 250 mutants (~25 mutants/shard)
#SBATCH --output=slurm/logs/02_injected_%A_%a.out
#SBATCH --error=slurm/logs/02_injected_%A_%a.err

# RQ2 (injected-fault detection) + RQ3a ablation (all-family config).
# Also includes matched MorphQ rerun on the 250 variants.

set -euo pipefail
ROOT=/fred/oz402/nhunguyen/ICSE_QMTester
APP=/apps/system/software/apptainer/latest/bin/apptainer
SIF=$ROOT/containers/qmtester.sif
SHARD=$SLURM_ARRAY_TASK_ID
NSHARDS=10
RUN_ID=${QMT_RUN_ID:-legacy_mixed}
if [ -z "${QMT_RUN_ID:-}" ]; then
    echo "[$(date)] WARNING: QMT_RUN_ID unset; writing diagnostic output under run legacy_mixed"
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

mkdir -p "$ROOT/slurm/logs"
WORK=$JOBFS/qmt_injected_$SHARD
mkdir -p "$WORK"

echo "[$(date)] node=$(hostname) shard=$SHARD FAMILIES=all"

OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_injected.py \
        --root /work \
        --shard $SHARD \
        --nshards $NSHARDS \
        --shots 4096 \
        --seed 20240519 \
        --out_dir "$WORK" \
        --run_id "$RUN_ID" \
        --enabled_families identity swap phase equivalence \
        --with_morphq

OUT=$ROOT/data/results/runs/$RUN_ID/shards
mkdir -p "$OUT"
cp -v "$WORK"/*.jsonl "$OUT/" 2>/dev/null || true
echo "[$(date)] shard $SHARD done."
