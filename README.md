# QMTester: Program-Level Metamorphic Testing for Quantum Programs

Research artifact for the paper *QMTester: Program-Level Metamorphic Testing for
Quantum Programs*. QMTester defines metamorphic relations over a Qiskit program's
**inputs** (not its emitted circuit), rebuilds the circuit from a transformed
input, canonicalizes the measured count vectors through a documented bijection,
and applies a permutation two-sample test. Its core discipline is
*canonicalization-as-admission*: a relation is tested only when its output map is a
documented bijection on the measured support.

The compiled paper is `paper/main.pdf`.

## Repository structure

| Path | Contents |
|---|---|
| `paper/` | LaTeX source (`main.tex`, `submission/*.tex`, `tables/*.tex`, `figures/`) and the built `main.pdf`. |
| `artifact/qmtester/` | The tool: relation families (`program_relations.py`), canonicalization (`canonicalize.py`), the statistical oracle (`oracle/`), the pipeline (`program_pipeline.py`, `pipeline.py`), program-subject adapters (`bugs4q_program_subjects.py`, `program_examples.py`), the period-aware admission (`soundness.py`), the register-shape static check (`register_shape.py`), and the mined subjects (`mined_program_subjects.py`). |
| `scripts/` | Manifest builders (`build_*_manifest.py`), run drivers (`run_bugs4q_program.py`, `run_program_injected.py`, `run_falsepos.py`), the canonical-CSV derivation (`derive_metrics.py`), and the analysis scripts that reproduce individual paper results (see below). |
| `tests/` | Unit tests for relation/canonicalization soundness (`make tests`). |
| `benchmarks/correct/` | The 50 correct-program corpus used for false-positive measurement. |
| `data/manifests/` | Frozen subject/mutant manifests (`bugs4q_manifest.csv`, `injected_mutants.csv`, `program_*_manifest.csv`, `program_mined_manifest.csv`). |
| `data/results/paper_ready/program_v1/` | **Authoritative** frozen `canonical_results.csv` + `SHA256SUMS.txt` — every headline number resolves to a row here. |
| `data/results/runs/redesign_hpc_1g_32bugs_fixcounts_*/` | The frozen run: per-(subject, seed, family) summary shards that `derive_metrics.py` consumes. |
| `vendor/bugs4q/` | Bugs4Q data root (subjects referenced by the manifests). |
| `faults/`, `baselines/` | Mutation operator (`faults/mutator.py`) and the MorphQ circuit-level baseline (`baselines/morphq_runner.py`). |
| `containers/qmtester.sif` | Singularity image — the reproduction environment for the full HPC pipeline. |
| `slurm/` | SLURM job scripts that produced the frozen run (`make submit`). |
| `Makefile` | Entry point for the full pipeline (`prepare`, `submit`, `repro`, `tests`). |

## Reproducing the paper results

### A. Verify the frozen canonical numbers

Every headline number (Bugs4Q 7/7, MorphQ 0/7, injected 100/100 vs 20/100, fixed
variants 0/107, correct programs 0/50) resolves to a row of the authoritative
canonical CSV:

```
data/results/paper_ready/program_v1/canonical_results.csv     # the numbers
data/results/paper_ready/program_v1/SHA256SUMS.txt            # integrity check
```

To regenerate that CSV from the raw shards (byte-identical re-derivation check):

```
python scripts/derive_metrics.py --root . \
  --shard_dir data/results/runs/redesign_hpc_1g_32bugs_fixcounts_*/shards \
  --out data/results/runs/<run>/canonical_results.csv --run_id <run>
```

### B. Full pipeline (HPC / container)

The frozen run was produced inside `containers/qmtester.sif`:

```
make prepare    # build manifests + fetch the correct-program corpus
make submit     # submit the SLURM job chain (runs the experiments)
make repro      # derive the canonical CSV from the produced shards
make tests      # unit tests (relation/canonicalization soundness)
```

### C. Local reproduction of individual results (Python venvs, no container)

These scripts reproduce specific paper numbers on a single machine. They need a
Qiskit 0.45 environment (`.venv_local`); the cross-stack check needs a Cirq
environment (`.venv_cirq`).

```
# Qiskit 0.45 env (the --no-deps step avoids pulling Qiskit >=1.0 onto terra 0.45)
python -m venv .venv_local
.venv_local/Scripts/pip install qiskit-terra==0.45.3 "numpy<2" scipy
.venv_local/Scripts/pip install --no-deps qiskit-aer==0.13.3

# Cirq env (for the cross-stack replication only)
python -m venv .venv_cirq
.venv_cirq/Scripts/pip install "cirq-core>=1.3" "numpy<2" scipy
```

| Paper result | Command (`.venv_local/Scripts/python ...` unless noted) |
|---|---|
| Static-analyzer baseline (0/7 semantic) + minimal-QMTester (7/7) | `scripts/run_static_and_minimal.py` |
| Reference-oracle differential (7/7, 0/7) | `scripts/run_external_baseline.py` |
| Baselines on the 3 mined subjects (reference-oracle 10/10; static 0/10) | `scripts/run_baselines_on_mined.py` |
| Per-subject pair count *m* under realistic noise | `scripts/run_m_distribution.py` |
| Power-curve floor (fine sub-0.03 sweep) | `scripts/run_power_curve_fine.py` |
| Realistic-noise detection on the seven Bugs4Q subjects | `scripts/run_realistic_noise_detection.py` |
| QFT effect-size analysis (real subject vs injected mutants) | `scripts/run_qft_analysis.py` |
| Cross-stack replication on Cirq | `.venv_cirq/Scripts/python scripts/run_cirq_crossstack.py` |

The three mined subjects (`qcse_23954`, `qcse_28272`, `qcse_40171`) live in
`artifact/qmtester/mined_program_subjects.py`; their provenance is in
`data/manifests/program_mined_manifest.csv`.
