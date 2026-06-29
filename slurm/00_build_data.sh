#!/bin/bash
#SBATCH --job-name=qmt_setup
#SBATCH --partition=trevor
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=0:30:00
#SBATCH --output=slurm/logs/00_setup_%j.out
#SBATCH --error=slurm/logs/00_setup_%j.err

# Phase 0 job: fetch benchmark data on Trevor (has internet access).
# Run once, before any experiment jobs.

set -euo pipefail
ROOT=/fred/oz402/nhunguyen/ICSE_QMTester
mkdir -p "$ROOT/slurm/logs"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

echo "[$(date)] Fetching MQT Bench correct programs..."
# Install mqt.bench to $TMPDIR (no inode pressure on /fred)
APP=/apps/system/software/apptainer/latest/bin/apptainer
SIF=$ROOT/containers/qmtester.sif

# Fetch 50 correct programs from MQT Bench via pip inside the container.
# We write them as .py QuantumCircuit scripts to benchmarks/correct/
$APP exec --bind $ROOT:/work $SIF python /work/scripts/fetch_mqt_bench.py \
    --out /work/benchmarks/correct \
    --n 50

echo "[$(date)] Building frozen Bugs4Q manifest..."
$APP exec --bind $ROOT:/work $SIF python /work/scripts/build_bugs4q_manifest.py \
    --root /work

echo "[$(date)] Building frozen injected-mutant manifest..."
$APP exec --bind $ROOT:/work $SIF python /work/scripts/build_injected_manifest.py \
    --root /work \
    --mutants 250 \
    --max_per_source 25 \
    --min_tvd 0.02 \
    --effect_shots 8192

echo "[$(date)] Done."
