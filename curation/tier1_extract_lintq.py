"""Tier 1 extractor: LintQ (FSE'24) -> a candidates CSV for tier1_screen.py.

Reads LintQ's real on-disk artifacts (verified 2026-06-28):
  * SARIF detected-problems at data/analysis_results/<dataset>/<run>/data.sarif
    (each result = ruleId + message + file uri + line) -- the full detected population.
  * the curated, manually-labelled bug list bug_reports/Bug_reports_feedback_summary.csv
    (issue,rule_id,description,file,line,status,manifestation) -- the confirmed real bugs.

Emits one row per detected problem with columns tier1_screen.py expects
(id,title,description,buggy_path,fixed_path) plus provenance columns. This extractor does
NOT classify into builder-contract families -- that is tier1_screen.classify()'s job, and
the final in/out call is the human/LLM audit. It only turns the bug index into candidates.

NOTE: the flagged .py programs live in LintQ's CodeQL database (Figshare), not the git repo,
so buggy_path is usually empty (a `lintq_file` ref is kept for traceability); the text
prefilter still works. LintQ findings have no paired fix, so fixed_path is always empty.

Usage (runs anywhere; no qiskit needed):
  python curation/tier1_extract_lintq.py --lintq_dir curation/datasets/LintQ \
      --out curation/datasets/LintQ_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def _sarif_results(sarif_path):
    try:
        doc = json.loads(Path(sarif_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [warn] cannot read {sarif_path}: {e}")
        return
    for run in doc.get("runs", []):
        for r in run.get("results", []):
            rule = r.get("ruleId") or (r.get("rule") or {}).get("id") or ""
            msg = (r.get("message") or {}).get("text", "")
            uri, line = "", ""
            locs = r.get("locations") or []
            if locs:
                phys = locs[0].get("physicalLocation", {})
                uri = phys.get("artifactLocation", {}).get("uri", "")
                line = (phys.get("region") or {}).get("startLine", "")
            yield rule, msg, uri, line


def _build_index(lintq_dir: Path):
    """basename -> on-disk path, built once (the flagged programs are usually NOT in the
    git repo, so most lookups miss; a single walk beats rglob-per-candidate)."""
    idx = {}
    for p in lintq_dir.rglob("*.py"):
        idx.setdefault(p.name, str(p))
    return idx


def _resolve_path(index, uri: str):
    """Return an on-disk path to the flagged program if present in the repo, else ''."""
    return index.get(Path(uri).name, "") if uri else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lintq_dir", default="curation/datasets/LintQ")
    ap.add_argument("--out", default="curation/datasets/LintQ_candidates.csv")
    ap.add_argument("--dataset", default="exp_v08",
                    help="which analysis_results subdir to take SARIF from (substring match). "
                         "exp_v08 = the main real-GitHub-program run. Use 'all' for every run.")
    args = ap.parse_args()

    lintq = Path(args.lintq_dir)
    if not lintq.is_dir():
        raise SystemExit(f"LintQ dir not found: {lintq} (clone sola-st/LintQ and point --lintq_dir at it)")

    index = _build_index(lintq)
    rows = []
    seen = set()  # (source, rule, file, line) dedup

    # (1) SARIF detected-problem population. Skip the *_sample_* downsamples; take data.sarif.
    sarif_root = lintq / "data" / "analysis_results"
    sarifs = [p for p in sarif_root.rglob("data.sarif")
              if "_sample_" not in p.name and (args.dataset == "all" or args.dataset in str(p))]
    print(f"SARIF files selected ({args.dataset}): {len(sarifs)}")
    for sp in sarifs:
        dataset = sp.relative_to(sarif_root).parts[0]
        for rule, msg, uri, line in _sarif_results(sp):
            key = ("sarif", rule, uri, str(line))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "id": f"lintq_sarif_{dataset}_{rule}_{Path(uri).stem}_{line}",
                "title": rule,
                "description": msg,
                "buggy_path": _resolve_path(index, uri),
                "fixed_path": "",
                "source": f"sarif:{dataset}",
                "rule_id": rule,
                "lintq_file": uri,
                "line": line,
                "manual_status": "",
            })

    # (2) Curated, manually-confirmed bug list (higher-quality candidates).
    fb = lintq / "bug_reports" / "Bug_reports_feedback_summary.csv"
    if fb.is_file():
        n = 0
        for r in csv.DictReader(fb.open(encoding="utf-8")):
            rule = (r.get("rule_id") or "").strip()
            f = (r.get("file") or "").strip()
            ln = (r.get("line") or "").strip()
            key = ("feedback", rule, f, ln)
            if not rule or key in seen:
                continue
            seen.add(key)
            n += 1
            rows.append({
                "id": f"lintq_confirmed_{rule}_{f}_{ln}",
                "title": rule,
                "description": (r.get("description") or "").strip(),
                "buggy_path": _resolve_path(index, f),
                "fixed_path": "",
                "source": "feedback_summary",
                "rule_id": rule,
                "lintq_file": f,
                "line": ln,
                "manual_status": (r.get("status") or "").strip(),
            })
        print(f"feedback_summary confirmed-bug rows added: {n}")
    else:
        print(f"  [warn] {fb} not found; emitting SARIF candidates only")

    if not rows:
        raise SystemExit("No candidates extracted -- check --lintq_dir / --dataset.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["id", "title", "description", "buggy_path", "fixed_path",
            "source", "rule_id", "lintq_file", "line", "manual_status"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

    print(f"\nwrote {len(rows)} candidates -> {out}")
    print("by source:", dict(Counter(r["source"] for r in rows)))
    print("top rules:", dict(Counter(r["rule_id"] for r in rows).most_common(12)))
    print(f"on-disk program resolved for {sum(1 for r in rows if r['buggy_path'])}/{len(rows)} "
          "(0 is expected: programs live in the Figshare CodeQL DB, not the git repo)")
    print("\nNEXT: python curation/tier1_screen.py --candidates", out,
          "--out curation/triage/LintQ_triage.csv")


if __name__ == "__main__":
    main()
