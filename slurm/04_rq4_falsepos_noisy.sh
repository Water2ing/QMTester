#!/bin/bash
#SBATCH --job-name=qmt_falsepos
#SBATCH --partition=milan
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=2:00:00
# Correct programs are <=9 qubits; observed peak RSS is well under 1G.
# No need for largemem1t (dave301-311); any standard milan node works.
#SBATCH --output=slurm/logs/04_falsepos_%j.out
#SBATCH --error=slurm/logs/04_falsepos_%j.err

# RQ4: false-positive rate + noisy-simulator calibration (Table VIII, XIV).
# Runs 3 configs: ideal, noisy (uncalibrated), noisy+calibrated.

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

mkdir -p "$ROOT/slurm/logs"
WORK=$JOBFS/qmt_falsepos
mkdir -p "$WORK"

echo "[$(date)] node=$(hostname) RAM=$(free -h | awk '/^Mem/{print $2}')"

# 1. Ideal simulation (50 programs, density matrix not needed)
echo "[$(date)] Running ideal false-positive check..."
OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_falsepos.py \
        --root /work --shots 4096 --seed 20240519 \
        --run_id "$RUN_ID" \
        --out_dir "$WORK/ideal"

# 2. Noisy simulation (uncalibrated)
echo "[$(date)] Running noisy (uncalibrated) false-positive check..."
OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_falsepos.py \
        --root /work --shots 4096 --seed 20240519 \
        --run_id "$RUN_ID" \
        --out_dir "$WORK/noisy" \
        --noisy

# 3. Noisy simulation with K=20 calibration
echo "[$(date)] Running noisy+calibrated false-positive check..."
OMP_NUM_THREADS=1 $APP exec \
    --bind "$ROOT:/work,$JOBFS:$JOBFS" \
    "$SIF" python /work/scripts/run_falsepos.py \
        --root /work --shots 4096 --seed 20240519 \
        --run_id "$RUN_ID" \
        --out_dir "$WORK/noisy_cal" \
        --noisy --calibrate

OUT=$ROOT/data/results/runs/$RUN_ID/shards
mkdir -p "$OUT"
cp -v "$WORK"/**/*.jsonl "$OUT/" 2>/dev/null || true
echo "[$(date)] falsepos done."
