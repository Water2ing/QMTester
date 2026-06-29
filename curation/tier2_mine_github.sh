#!/usr/bin/env bash
# Tier 2 (a) - pre-registered, EXHAUSTIVE GitHub mining of bug-labeled Qiskit issues.
# Requires: gh CLI authenticated (gh auth login). Produces a candidates CSV for tier1_screen.py.
# The point is EXHAUSTIVENESS over a frozen window (no sampling) -> defeats "you hand-picked".
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=curation/datasets
mkdir -p "$OUT"

# Pre-register the frozen population here (edit before running, then DO NOT change):
REPOS=("Qiskit/qiskit" "Qiskit/qiskit-aer" "Qiskit/qiskit-terra")
SINCE="2019-01-01"
UNTIL="2025-01-01"
LIMIT=10000

command -v gh >/dev/null || { echo "ERROR: gh not installed. See curation/env_h100.sh note."; exit 1; }

CSV="$OUT/github_candidates.csv"
echo "id,source,title,description,buggy_path,fixed_path,url" > "$CSV"
for repo in "${REPOS[@]}"; do
  echo "== mining $repo (label:bug, $SINCE..$UNTIL) =="
  gh issue list -R "$repo" --label bug --state all --limit "$LIMIT" \
     --json number,title,body,url,closedAt \
     --jq ".[] | select(.closedAt != null and .closedAt >= \"$SINCE\" and .closedAt <= \"$UNTIL\")
            | [ (\"gh_${repo//\//_}_\" + (.number|tostring)), \"github:$repo\",
                (.title|gsub(\",\";\";\")), ((.body//\"\")[0:400]|gsub(\"[\\n,]\";\" \")), \"\", \"\", .url ]
            | @csv" >> "$CSV"
done
echo "Wrote $CSV ($(($(wc -l < "$CSV")-1)) candidates). Now: python curation/tier1_screen.py --candidates $CSV --out curation/triage/github_triage.csv"
echo "Then extract buggy/fixed from each INCLUDED issue's linked PR/commit and fill buggy_path/fixed_path."
