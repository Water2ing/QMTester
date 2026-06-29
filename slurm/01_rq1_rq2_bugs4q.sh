#!/bin/bash
#SBATCH --job-name=qmt_bugs4q
#SBATCH --partition=milan
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=0:30:00
#SBATCH --array=0-5          # 6 shards for 90 subjects (~15 subjects/shard)
#SBATCH --output=slurm/logs/01_bugs4q_%A_%a.out
#SBATCH --error=slurm/logs/01_bugs4q_%A_%a.err

# RQ1 + RQ2: QMTester (all 4 families) on Bugs4Q + matched MorphQ rerun.
# Partition: milan. This Python workload is intentionally single-threaded.
# Writes pair logs to $JOBFS, then copies shards back to /fred.
# PartitionDown: if this fails with PartitionDown, just re-submit (see HPC_guide.txt).

set -euo pipefail
ROOT=/fred/oz402/nhunguyen/ICSE_QMTester
APP=/apps/system/software/apptainer/latest/bin/apptainer
SIF=$ROOT/containers/qmtester.sif
SHARD=$SLURM_ARRAY_TASK_ID
NSHARDS=6
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

# Use node-local NVMe for intermediate outputs (inode strategy: keep /fred clean)
WORK=$JOBFS/qmt_bugs4q_$SHARD
mkdir -p "$WORK"

echo "[$(date)] node=$(hostname) shard=$SHARD"

OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_bugs4q.py \
        --root /work \
        --shard $SHARD \
        --nshards $NSHARDS \
        --shots 4096 \
        --seed 20240519 \
        --out_dir "$WORK" \
        --run_id "$RUN_ID" \
        --with_morphq \
        --enabled_families identity swap phase equivalence

echo "[$(date)] Copying shards back to /fred..."
OUT=$ROOT/data/results/runs/$RUN_ID/shards
mkdir -p "$OUT"
cp -v "$WORK"/*.jsonl "$OUT/" 2>/dev/null || true

echo "[$(date)] shard $SHARD done."
