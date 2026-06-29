#!/usr/bin/env bash
# Dump the real on-disk structure of the two Tier-1 datasets so the candidate extractors
# can be written against the ACTUAL schema (column names, file layout) -- not a guess.
# Run on the H100 after the datasets are in place:  bash curation/tier1_inspect.sh
set -uo pipefail
cd "$(dirname "$0")/.."
D=curation/datasets

sect() { echo; echo "########## $* ##########"; }
hdr()  { [ -f "$1" ] && { echo "-- columns of $1 --"; head -1 "$1" | tr ',' '\n' | cat -n; \
                          echo "-- first 2 data rows --"; sed -n '2,3p' "$1"; } || echo "(missing: $1)"; }

sect "PLATFORMS-OOPSLA'22  ($D/platforms_oopsla22)"
ls "$D/platforms_oopsla22" 2>/dev/null || echo "(dir missing)"
echo "-- artifacts/ --"; ls "$D/platforms_oopsla22/artifacts" 2>/dev/null
# the bug-annotation CSV (name may vary): show columns of any csv under artifacts/
for c in "$D/platforms_oopsla22/artifacts"/*.csv; do [ -f "$c" ] && hdr "$c"; done
echo "-- minimal_bugfixes layout (2 levels, first 30 entries) --"
find "$D/platforms_oopsla22/artifacts/minimal_bugfixes" -maxdepth 2 2>/dev/null | head -30
echo "-- example: one bug folder's files --"
ex=$(find "$D/platforms_oopsla22/artifacts/minimal_bugfixes" -maxdepth 1 -mindepth 1 2>/dev/null | head -1)
[ -n "${ex:-}" ] && { echo "($ex)"; ls -R "$ex" 2>/dev/null | head -20; }

sect "LintQ  ($D/LintQ)"
ls "$D/LintQ" 2>/dev/null || echo "(dir missing)"
echo "-- SARIF result files (first 10) --"
find "$D/LintQ" -name '*.sarif' 2>/dev/null | head -10
echo "-- one SARIF: top-level keys + a sample result --"
s=$(find "$D/LintQ" -name '*.sarif' 2>/dev/null | head -1)
if [ -n "${s:-}" ]; then
  python3 - "$s" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
run = d.get("runs", [{}])[0]
res = run.get("results", [])
print("runs:", len(d.get("runs", [])), " results in run0:", len(res))
if res:
    r = res[0]
    loc = (r.get("locations") or [{}])[0].get("physicalLocation", {})
    print("sample result keys:", list(r.keys()))
    print("  ruleId :", r.get("ruleId"))
    print("  message:", (r.get("message") or {}).get("text", "")[:120])
    print("  uri    :", loc.get("artifactLocation", {}).get("uri"))
    print("  region :", loc.get("region"))
PY
fi
echo "-- bug_reports/ CSVs + columns --"
ls "$D/LintQ/bug_reports" 2>/dev/null
for c in "$D/LintQ/bug_reports"/*.csv; do [ -f "$c" ] && hdr "$c"; done
echo "-- data/datasets program dir (sample) --"
find "$D/LintQ/data/datasets" -maxdepth 2 2>/dev/null | head -15

sect "DONE -- paste everything above back"
