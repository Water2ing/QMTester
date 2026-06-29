#!/usr/bin/env bash
# Environment setup for the beyond-Bugs4Q curation campaign on an H100 GPU server.
#
# IMPORTANT: this creates TWO isolated venvs, on purpose.
#
#   .venv_curation  -- pinned PRE-1.0 Qiskit (terra/aer 0.45) + GPU Aer.  This is what
#                      runs the Tier 3 campaign and the qmtester tool (artifact/qmtester
#                      shims qiskit.Aer / qiskit.execute / qiskit.extensions.* which were
#                      REMOVED in Qiskit 1.0, so the tool only works on <1.0).
#   .venv_fetch     -- Qiskit >=1.0 + mqt.bench, used ONLY to (re)fetch the corpus.
#                      mqt.bench HARD-depends on Qiskit >=1.0; installing it into
#                      .venv_curation drags >=1.0 in on top of qiskit-terra 0.45 and
#                      corrupts the env ("both Qiskit >=1.0 and an earlier version").
#                      The two are decoupled by the corpus: the fetcher serializes every
#                      circuit to OpenQASM 2 (.py files that just `qasm2.loads(...)`), a
#                      portable interchange format the pre-1.0 campaign env can exec.
#
# Usage:  bash curation/env_h100.sh                 # from the repo root
#   fetch corpus:   source .venv_fetch/bin/activate    && python scripts/fetch_mqt_bench.py --out curation/corpus --n 200
#   run campaign:   source .venv_curation/bin/activate  && python curation/tier3_fault_campaign.py ...
#
# Assumes: NVIDIA H100 visible (`nvidia-smi` works), CUDA 12 runtime, Python 3.10/3.11.
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root

echo "== GPU check =="
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv || {
  echo "WARNING: nvidia-smi failed; Tier 3 will fall back to CPU."; }

PY=${PY:-python3}

# ---------------------------------------------------------------------------
# 1) .venv_curation  --  pinned pre-1.0 stack that RUNS the campaign + the tool
# ---------------------------------------------------------------------------
echo "== [.venv_curation] core QMTester stack (pinned, pre-1.0 Qiskit) =="
# Start clean: `python -m venv` over an existing dir does NOT remove already-installed
# packages, so a previously-corrupted env (mixed Qiskit versions) would survive. venvs
# are fully regenerable, so wipe and rebuild to make re-running self-healing.
rm -rf .venv_curation
$PY -m venv .venv_curation
# shellcheck disable=SC1091
source .venv_curation/bin/activate
python -m pip install --upgrade pip wheel
# NOTE: do NOT install mqt.bench here -- it requires Qiskit >=1.0 and breaks this env.
pip install --no-cache-dir \
  "qiskit==0.45.3" "qiskit-terra==0.45.3" "scipy" "numpy<2" "pandas" "requests"

echo "== [.venv_curation] GPU Aer =="
# H100 = CUDA 12 / compute capability 9.0. Try the CUDA-12 wheel first, then the
# legacy wheel, then CPU Aer as a last resort (the campaign auto-detects the device).
pip install --no-cache-dir "qiskit-aer-gpu-cu12==0.13.3" \
  || pip install --no-cache-dir "qiskit-aer-gpu==0.13.3" \
  || { echo "GPU Aer install failed; installing CPU Aer (campaign will use --device CPU)"; \
       pip install --no-cache-dir "qiskit-aer==0.13.3"; }

echo "== [.venv_curation] Verify (this is the env the campaign actually uses) =="
python - <<'PY'
import sys
import qiskit, qiskit_aer
print("qiskit", qiskit.__version__, "aer", qiskit_aer.__version__)

# Fail LOUD and EARLY if the pre-1.0 pin was clobbered (e.g. by an mqt.bench install).
# This is exactly the corruption that produced the cryptic "both Qiskit >=1.0 and an
# earlier version" ImportError -- catch it here with an actionable message instead.
if not qiskit.__version__.startswith("0."):
    sys.exit(f"FATAL: .venv_curation has Qiskit {qiskit.__version__} (expected pre-1.0). "
             "Something pulled in Qiskit >=1.0 (usually mqt.bench). Recreate this venv "
             "and keep mqt.bench in .venv_fetch only.")

# The campaign imports the qmtester tool, which relies on the pre-1.0 compat shims.
sys.path.insert(0, "artifact")
from qmtester.qiskit_compat import install_qiskit_compat
install_qiskit_compat()
from qmtester.canonicalize import canonicalize          # noqa: F401
from qmtester.oracle.chisq import two_sample_test        # noqa: F401
print("qmtester tool imports OK (compat shims installed)")

try:
    from qiskit_aer import AerSimulator
    sim = AerSimulator(device="GPU")
    print("GPU Aer available:", "GPU" in sim.available_devices())
except Exception as e:
    print("GPU Aer NOT available (use --device CPU):", e)
PY
deactivate

# ---------------------------------------------------------------------------
# 2) .venv_fetch  --  isolated Qiskit >=1.0 + mqt.bench, ONLY to fetch the corpus
# ---------------------------------------------------------------------------
echo "== [.venv_fetch] corpus fetcher (Qiskit >=1.0 + mqt.bench) =="
rm -rf .venv_fetch
$PY -m venv .venv_fetch
# shellcheck disable=SC1091
source .venv_fetch/bin/activate
python -m pip install --upgrade pip wheel
if pip install --no-cache-dir "mqt.bench" "qiskit>=1.0"; then
  # Smoke-test an ACTUAL build via whichever API is installed (v2 enum / v1 kwargs),
  # so a get_benchmark signature mismatch shows up here, not after a 200-program run.
  python - <<'PY'
import sys
import qiskit
from mqt.bench import get_benchmark
try:
    from mqt.bench import BenchmarkLevel        # v2
    qc = get_benchmark("ghz", BenchmarkLevel.ALG, 4)
    api = "v2 (enum level)"
except Exception:
    qc = get_benchmark(benchmark_name="ghz", level="alg", circuit_size=4)  # v1
    api = "v1 (kwargs)"
n_names = "?"
import importlib
for _mod in ("mqt.bench", "mqt.bench.benchmarks"):
    try:
        _f = getattr(importlib.import_module(_mod), "get_available_benchmark_names", None)
        if _f:
            n_names = len(_f()); break
    except Exception:
        pass
print(f"[.venv_fetch] qiskit {qiskit.__version__}; mqt.bench API {api}; "
      f"{n_names} benchmarks; built ghz -> {qc.num_qubits}q OK")
PY
else
  echo "NOTE: mqt.bench install failed. The fetcher falls back to synthetic GHZ/QFT"
  echo "      circuits (which have NO rotation sites, so Tier 3 would skip them all)."
  echo "      Install mqt.bench on a machine with internet to get the diverse corpus."
fi
deactivate

echo
echo "NOTE (Tier 2 only): GitHub mining uses the 'gh' CLI. If absent, install it:"
echo "  (Debian/Ubuntu)  type -p curl >/dev/null || sudo apt install curl -y; \\"
echo "    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg; \\"
echo "    echo 'deb [arch=\$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main' | sudo tee /etc/apt/sources.list.d/github-cli.list; \\"
echo "    sudo apt update && sudo apt install gh -y && gh auth login"
echo
echo "Done."
echo "  Fetch corpus:  source .venv_fetch/bin/activate    && python scripts/fetch_mqt_bench.py --out curation/corpus --n 200"
echo "  Run campaign:  source .venv_curation/bin/activate  && python curation/tier3_fault_campaign.py --corpus_dir curation/corpus ..."
