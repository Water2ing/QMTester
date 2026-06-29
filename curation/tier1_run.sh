#!/usr/bin/env bash
# One-command driver for the remaining Tier-1 LintQ steps:
#   extract candidates -> screen (prefilter) -> print a prioritized triage summary.
# Run on whichever machine holds curation/datasets/LintQ (no qiskit needed for LintQ):
#   bash curation/tier1_run.sh
# Then paste the whole output back.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python3}

echo "########## 1) extract LintQ candidates ##########"
$PY curation/tier1_extract_lintq.py \
    --lintq_dir curation/datasets/LintQ \
    --out curation/datasets/LintQ_candidates.csv || { echo "EXTRACT FAILED"; exit 1; }

echo; echo "########## 2) screen (text prefilter; no --run_pairs: LintQ programs are off-disk) ##########"
$PY curation/tier1_screen.py \
    --candidates curation/datasets/LintQ_candidates.csv \
    --out curation/triage/LintQ_triage.csv || { echo "SCREEN FAILED"; exit 1; }

echo; echo "########## 3) prioritized triage summary ##########"
$PY - <<'PY'
import csv, collections
rows = list(csv.DictReader(open("curation/triage/LintQ_triage.csv", encoding="utf-8")))
dec = collections.Counter(r["prefilter_decision"] for r in rows)
print(f"total candidates: {len(rows)}   decisions: {dict(dec)}")
conf = collections.Counter(r.get("manual_status","") for r in rows if r.get("manual_status"))
if conf: print("manual_status (from feedback_summary):", dict(conf))
print("\n--- distinct rules x prefilter decision (the audit work-list) ---")
by_rule = collections.defaultdict(lambda: collections.Counter())
ex = {}
for r in rows:
    by_rule[r["rule_id"]][r["prefilter_decision"]] += 1
    ex.setdefault((r["rule_id"], r["prefilter_decision"]), r["description"][:90])
for rule in sorted(by_rule, key=lambda k: -sum(by_rule[k].values())):
    c = by_rule[rule]
    fam = next((r["prefilter_family"] for r in rows if r["rule_id"]==rule and r["prefilter_family"]), "")
    print(f"  {rule:<34} {dict(c)}  fam~{fam or '-'}")
    print(f"       e.g. {ex.get((rule,'review')) or ex.get((rule,'likely_out')) or ''}")
print("\nNEXT: open curation/triage/LintQ_triage.csv and fill final_in_scope / final_family /")
print("audit_note for EVERY row (the soundness judgment; prefilter only orders the work).")
PY

echo; echo "########## platforms readiness ##########"
if [ -n "$(ls -A curation/datasets/platforms_oopsla22 2>/dev/null)" ]; then
  echo "platforms_oopsla22 present -> run:  bash curation/tier1_inspect.sh   and paste the PLATFORMS section"
  echo "(so tier1_extract_platforms.py can be written against its real schema)."
else
  echo "platforms_oopsla22 is EMPTY/missing -> re-upload the"
  echo "MattePalte/Bugs-Quantum-Computing-Platforms clone, then re-run inspect."
fi
