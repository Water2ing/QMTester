#!/usr/bin/env bash
# Tier 1 - fetch existing real quantum-bug datasets for exhaustive builder-contract screening.
# Run on a machine with internet (the H100 server is fine). Clones into curation/datasets/.
#
# Links verified live on 2026-06-28. Only the two datasets below have a confirmed PUBLIC
# artifact with extractable buggy/fixed material -- these are the Tier 1 priorities. The
# three paper-only entries at the bottom have NO verified downloadable dataset repo; do not
# hardcode a clone URL for them (an earlier draft guessed wrong URLs that 404).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=curation/datasets
mkdir -p "$DEST"

clone() { # url dir
  if [ -d "$DEST/$2/.git" ]; then echo "exists: $2"; return; fi
  if ! git clone --depth 1 "$1" "$DEST/$2"; then
    echo "  !! clone FAILED for $1 -- verify the URL is still live before screening." >&2
  fi
}

echo "== LintQ (FSE'24) - static analysis over 7,568 real Qiskit programs, 216 detected problems =="
# Repo: detected-problem SARIF at data/analysis_results/, manual TP/FP annotations at bug_reports/,
# program dataset at data/datasets/exp_v08/ (the full CodeQL DB is on Figshare, linked from the repo).
clone https://github.com/sola-st/LintQ.git LintQ
#   Stable archive fallback (FSE'24 artifact): https://zenodo.org/records/11095456  (doi 10.5281/zenodo.11095456)

echo "== Bugs in Quantum Computing Platforms (OOPSLA'22, Paltenghi & Pradel) - 223 bugs, ~89 Qiskit =="
# Repo: artifacts/annotation_bugs.csv (bug type/component/symptom/pattern) +
#       artifacts/minimal_bugfixes/ (before/after code pairs -> the buggy/fixed pairs we need).
clone https://github.com/MattePalte/Bugs-Quantum-Computing-Platforms.git platforms_oopsla22
#   Stable archive fallback: https://doi.org/10.5281/zenodo.5834281

echo
echo "Cloned into $DEST/. Next: build a candidates CSV per dataset (id,title,buggy_path,fixed_path)"
echo "and run curation/tier1_screen.py on it (see the runbook in BEYOND_BUGS4Q_CURATION_PLAN.md)."
echo
echo "PAPER-ONLY (no verified public dataset repo as of 2026-06-28 -- read the paper's data-availability"
echo "section; do NOT assume a GitHub repo). Builder-contract relevance is also weaker than first estimated:"
echo "  - QBugLM / QBugGen (arXiv 2606.07314): an LLM-debugging benchmark; QBugGen injects synthetic"
echo "    mutations into just 5 5-qubit OpenQASM3 circuits (dj/grover/bv/ghz/wstate) -> mostly NON-builder-"
echo "    contract. Low Tier-1 value; the earlier ChrisBaldoni/QBugLM URL is a 404."
echo "  - Understanding Bugs in Quantum Simulators (arXiv 2603.22789): 394 bugs, but emphasis is on CLASSICAL"
echo "    simulator infrastructure (memory/indexing/config), not Qiskit builder contracts. No public artifact found."
echo "  - Characterizing Bugs ... Large-Scale (arXiv 2512.24656): ecosystem-scale; no verified artifact/subset found."
