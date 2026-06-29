################################################################################
# QMTester — Makefile
#
# make repro     rebuild canonical_results.csv from raw_runs.jsonl (Algorithm 3)
# make prepare   build manifests/data on the login node
# make submit    submit experiment SLURM jobs in the correct order
# make program-smoke  run hand-audited Bugs4Q program-level subjects locally
# make program-injected-smoke  run builder-level program mutation smoke locally
# make program-prepare  build frozen program-level manifests locally
# make program-run      run full program-level experiments locally
# make program-hard     run supplemental lower-effect program mutants locally
# make smoke     quick end-to-end smoke test (no HPC, login node)
# make tests     unit tests inside the container
# make clean     remove derived output files only
################################################################################

ROOT     := $(shell pwd)
APP      := /apps/system/software/apptainer/latest/bin/apptainer
SIF      := $(ROOT)/containers/qmtester.sif
PYTHON   := OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 $(APP) exec --bind $(ROOT):/work $(SIF) python

RAW      := $(ROOT)/data/results/raw_runs.jsonl
CSV      := $(ROOT)/data/results/canonical_results.csv
LOGS     := $(ROOT)/slurm/logs
RUN_ID  ?= $(shell date -u +%Y%m%dT%H%M%SZ)
RUN_DIR  = $(ROOT)/data/results/runs/$(RUN_ID)

# ── Reproduce canonical CSV from raw logs ────────────────────────────────────
.PHONY: repro
repro:
	$(PYTHON) /work/scripts/derive_metrics.py \
		--root /work \
		--shard_dir data/results/runs/$(RUN_ID)/shards \
		--out data/results/runs/$(RUN_ID)/canonical_results.csv \
		--run_id $(RUN_ID)
	@echo "Canonical CSV regenerated: $(RUN_DIR)/canonical_results.csv"

# ── Prepare manifests/data on the login node ────────────────────────────────
.PHONY: prepare
prepare:
	$(PYTHON) /work/scripts/fetch_mqt_bench.py \
		--out /work/benchmarks/correct \
		--n 50
	$(PYTHON) /work/scripts/build_bugs4q_manifest.py \
		--root /work
	$(PYTHON) /work/scripts/build_injected_manifest.py \
		--root /work \
		--mutants 250 \
		--max_per_source 25 \
		--min_tvd 0.02 \
		--effect_shots 8192
	$(PYTHON) /work/scripts/build_program_bugs4q_manifest.py \
		--root /work
	$(PYTHON) /work/scripts/build_program_mutants_manifest.py \
		--root /work

# ── Submit experiment SLURM jobs (dependency chain) ──────────────────────────
.PHONY: submit
submit:
	@set -eu; \
	mkdir -p "$(LOGS)"; \
	test -f "$(ROOT)/data/manifests/bugs4q_manifest.csv" || \
		(echo "Missing Bugs4Q manifest. Run: make prepare" >&2; exit 2); \
	test -f "$(ROOT)/data/manifests/injected_mutants.csv" || \
		(echo "Missing injected mutant manifest. Run: make prepare" >&2; exit 2); \
	test -f "$(ROOT)/data/manifests/program_bugs4q_manifest.csv" || \
		(echo "Missing program Bugs4Q manifest. Run: make prepare" >&2; exit 2); \
	test -f "$(ROOT)/data/manifests/program_mutants_manifest.csv" || \
		(echo "Missing program mutants manifest. Run: make prepare" >&2; exit 2); \
	test -d "$(ROOT)/benchmarks/correct" || \
		(echo "Missing correct benchmark directory. Run: make prepare" >&2; exit 2); \
	RUN_ID="$(RUN_ID)"; \
	echo "Running program-level experiments on login node for run $$RUN_ID"; \
	mkdir -p "$(ROOT)/data/results/runs/$$RUN_ID/shards"; \
	rm -f "$(ROOT)/data/results/runs/$$RUN_ID/shards"/program_*.jsonl; \
	$(PYTHON) /work/scripts/run_bugs4q_program.py \
		--root /work \
		--shots 4096 \
		--seed 20240519 \
		--run_id $$RUN_ID \
		--variant both \
		--with_morphq \
		--out_dir /work/data/results/runs/$$RUN_ID/shards; \
	$(PYTHON) /work/scripts/run_program_injected.py \
		--root /work \
		--shots 4096 \
		--seed 20240519 \
		--run_id $$RUN_ID \
		--with_morphq \
		--out_dir /work/data/results/runs/$$RUN_ID/shards; \
	for family in program_input_permutation program_classical_remap program_qft_round_trip program_parameter_periodicity program_ancilla_uncompute; do \
		$(PYTHON) /work/scripts/run_program_injected.py \
			--root /work \
			--shots 4096 \
			--seed 20240519 \
			--run_id $$RUN_ID \
			--enabled_families $$family \
			--out_dir /work/data/results/runs/$$RUN_ID/shards; \
	done; \
	JOB1=$$(sbatch --parsable --export=ALL,QMT_RUN_ID=$$RUN_ID "$(ROOT)/slurm/01_rq1_rq2_bugs4q.sh"); \
	echo "Submitted job 1 (RQ1/RQ2 Bugs4Q): $$JOB1"; \
	JOB2=$$(sbatch --parsable --export=ALL,QMT_RUN_ID=$$RUN_ID "$(ROOT)/slurm/02_rq2_injected.sh"); \
	echo "Submitted job 2 (RQ2 injected): $$JOB2"; \
	JOB3=$$(sbatch --parsable --export=ALL,QMT_RUN_ID=$$RUN_ID "$(ROOT)/slurm/03_rq3a_ablation.sh"); \
	echo "Submitted job 3 (RQ3a ablation): $$JOB3"; \
	JOB4=$$(sbatch --parsable --export=ALL,QMT_RUN_ID=$$RUN_ID "$(ROOT)/slurm/04_rq4_falsepos_noisy.sh"); \
	echo "Submitted job 4 (RQ4 false-pos noisy): $$JOB4"; \
	JOB5=$$(sbatch --parsable --export=ALL,QMT_RUN_ID=$$RUN_ID "$(ROOT)/slurm/05_rq4_shot_sensitivity.sh"); \
	echo "Submitted job 5 (RQ4 shot sensitivity): $$JOB5"; \
	JOB6=$$(sbatch --parsable --export=ALL,QMT_RUN_ID=$$RUN_ID --dependency=afterok:$$JOB1,$$JOB2,$$JOB3,$$JOB4,$$JOB5 "$(ROOT)/slurm/06_reduce_derive.sh"); \
	echo "Submitted job 6 (reduce + derive): $$JOB6"; \
	echo ""; \
	echo "Run ID: $$RUN_ID"; \
	echo "All jobs submitted. Monitor with: squeue -u $$USER"; \
	echo "Final output will appear in: $(ROOT)/data/results/runs/$$RUN_ID/canonical_results.csv"

# ── Quick end-to-end smoke test (login node, no SLURM) ───────────────────────
.PHONY: smoke
smoke:
	@echo "=== Smoke test: container verify ==="
	$(APP) exec --bind $(ROOT):/work $(SIF) python -c "\
import qiskit, qiskit_aer; \
print('qiskit', qiskit.__version__, 'aer', qiskit_aer.__version__)"
	@echo ""
	@echo "=== Smoke test: build manifests ==="
	$(PYTHON) /work/scripts/build_bugs4q_manifest.py --root /work
	$(PYTHON) /work/scripts/build_injected_manifest.py \
		--root /work --mutants 10 --max_per_source 3 --min_tvd 0.01 --effect_shots 1024 \
		--out data/manifests/injected_mutants_smoke.csv \
		--qpy_dir data/manifests/injected_mutants_smoke_qpy
	@echo ""
	@echo "=== Smoke test: run Bugs4Q shard ==="
	$(PYTHON) /work/scripts/run_bugs4q.py \
		--root /work --shard 0 --nshards 90 \
		--shots 1024 --seed 20240519 \
		--run_id smoke \
		--out_dir /tmp/qmt_smoke
	@echo ""
	@echo "=== Smoke test: fetch correct programs ==="
	$(PYTHON) /work/scripts/fetch_mqt_bench.py \
		--out /work/benchmarks/correct --n 5
	$(PYTHON) /work/scripts/run_falsepos.py \
		--root /work --shots 256 --seed 20240519 \
		--run_id smoke --limit 5 --out_dir /tmp/qmt_smoke_falsepos
	@echo "Smoke test PASSED."

# ── Hand-audited program-level Bugs4Q smoke ─────────────────────────────────
.PHONY: program-smoke
program-smoke:
	$(PYTHON) /work/scripts/build_program_bugs4q_manifest.py \
		--root /work
	$(PYTHON) /work/scripts/run_bugs4q_program.py \
		--root /work \
		--shots 4096 \
		--seed 20240519 \
		--run_id program_smoke \
		--variant both \
		--with_morphq \
		--out_dir /tmp/qmt_program_smoke

.PHONY: program-injected-smoke
program-injected-smoke:
	$(PYTHON) /work/scripts/run_program_injected.py \
		--root /work \
		--shots 4096 \
		--seed 20240519 \
		--run_id program_injected_smoke \
		--out_dir /tmp/qmt_program_injected_smoke

.PHONY: program-prepare
program-prepare:
	$(PYTHON) /work/scripts/build_program_bugs4q_manifest.py \
		--root /work
	$(PYTHON) /work/scripts/build_program_mutants_manifest.py \
		--root /work
	$(PYTHON) /work/scripts/build_program_hard_mutants_manifest.py \
		--root /work

.PHONY: program-run
program-run:
	@mkdir -p "$(RUN_DIR)/shards"
	rm -f "$(RUN_DIR)/shards"/program_*.jsonl
	$(PYTHON) /work/scripts/run_bugs4q_program.py \
		--root /work \
		--shots 4096 \
		--seed 20240519 \
		--run_id $(RUN_ID) \
		--variant both \
		--with_morphq \
		--out_dir /work/data/results/runs/$(RUN_ID)/shards
	$(PYTHON) /work/scripts/run_program_injected.py \
		--root /work \
		--shots 4096 \
		--seed 20240519 \
		--run_id $(RUN_ID) \
		--with_morphq \
		--out_dir /work/data/results/runs/$(RUN_ID)/shards
	for family in program_input_permutation program_classical_remap program_qft_round_trip program_parameter_periodicity program_ancilla_uncompute; do \
		$(PYTHON) /work/scripts/run_program_injected.py \
			--root /work \
			--shots 4096 \
			--seed 20240519 \
			--run_id $(RUN_ID) \
			--enabled_families $$family \
			--out_dir /work/data/results/runs/$(RUN_ID)/shards; \
	done

.PHONY: program-hard
program-hard:
	@mkdir -p "$(RUN_DIR)/shards"
	rm -f "$(RUN_DIR)/shards"/program_injected_*program_parameter_periodicity*.jsonl
	$(PYTHON) /work/scripts/build_program_hard_mutants_manifest.py \
		--root /work
	$(PYTHON) /work/scripts/run_program_injected.py \
		--root /work \
		--shots 8192 \
		--seed 20240519 \
		--run_id $(RUN_ID) \
		--manifest data/manifests/program_hard_mutants_manifest.csv \
		--enabled_families program_parameter_periodicity \
		--with_morphq \
		--out_dir /work/data/results/runs/$(RUN_ID)/shards

# ── Unit tests ───────────────────────────────────────────────────────────────
.PHONY: tests
tests:
	$(PYTHON) -m unittest discover -s /work/tests -v

# ── Clean derived outputs ─────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -f $(CSV) $(RAW)
	rm -rf $(ROOT)/data/results/shards/
	rm -rf $(ROOT)/data/results/runs/
	@echo "Cleaned derived outputs (container and raw benchmarks untouched)."
