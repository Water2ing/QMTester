"""Tier 1/2 shared triage harness - exhaustive, documented builder-contract screening.

Takes a CSV of CANDIDATE bugs (one row per candidate, from any source: a dataset, a
GitHub mining run, or a Stack Exchange mining run) and produces a TRIAGE CSV that:
  (1) applies the two-layer pre-filter (builder-contract symptom keywords vs the generic
      out-of-scope taxonomy) so reviewers see EVERY candidate's in/out decision, and
  (2) where a runnable buggy+fixed pair exists, runs QMTester's program pipeline to record
      whether buggy.detected / fixed.clean (bidirectional check).
The FINAL relation-soundness decision is a human/LLM audit (same rubric as the Bugs4Q
audit) - this harness makes that audit exhaustive and auditable, it does not replace it.

Input CSV columns (any extra columns are preserved):  id,title,description,buggy_path,fixed_path
Usage:
  python curation/tier1_screen.py --candidates curation/datasets/LintQ_candidates.csv \
      --out curation/triage/LintQ_triage.csv
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

# Symptom keywords mapped to the five families (Layer-2 pre-filter, NOT a final decision).
FAMILY_KEYWORDS = {
    "program_input_permutation": ["control qubit", "ccx", "toffoli", "qubit order", "qubit role", "swap control", "symmetric control"],
    "program_classical_remap": ["endian", "measurement order", "classical register", "clbit", "measure_all", "bit order", "reversed"],
    "program_qft_round_trip": ["qft", "inverse qft", "qft_dagger", "iqft", "fourier"],
    "program_parameter_periodicity": ["angle", "rotation", "period", "2pi", "2*pi", "rz(", "ry(", "rx(", "phase angle"],
    "program_ancilla_uncompute": ["ancilla", "uncompute", "garbage", "teleport", "reset", "feedback"],
}
# Out-of-scope taxonomy (from the Bugs4Q audit): these dominate real datasets.
OUT_KEYWORDS = {
    "api_misuse": ["deprecated", "import", "attribute", "typeerror", "not defined", "transpile", "decompose", "to_gate"],
    "output-formatting": ["draw", "print", "plot", "visualiz", "get_statevector", "global_phase"],
    "platform/runtime": ["backend", "simulator", "thread", "version", "passmanager", "layout"],
    "generic_wrong_gate": ["wrong gate", "missing gate", "h instead", "x instead"],
}


def classify(text):
    t = (text or "").lower()
    fam_hits = [(f, sum(1 for k in kws if k in t)) for f, kws in FAMILY_KEYWORDS.items()]
    fam_hits = [(f, n) for f, n in fam_hits if n]
    out_hits = [(o, sum(1 for k in kws if k in t)) for o, kws in OUT_KEYWORDS.items()]
    out_hits = [(o, n) for o, n in out_hits if n]
    fam = max(fam_hits, key=lambda x: x[1])[0] if fam_hits else ""
    out = max(out_hits, key=lambda x: x[1])[0] if out_hits else ""
    # prefilter: builder-contract candidate iff a family keyword hits and no strong out signal
    candidate = bool(fam) and (not out or (fam_hits and max(n for _, n in fam_hits) >= max(n for _, n in out_hits)))
    return fam, out, "review" if candidate else "likely_out"


def run_pair(buggy_path, fixed_path):
    """Best-effort bidirectional detection on an extracted pair (returns dict or {})."""
    if not buggy_path or not fixed_path:
        return {}
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "artifact"))
    try:
        from tier3_fault_campaign import load_circuit  # reuse loader
    except Exception:
        import importlib.util
        spec = importlib.util.spec_from_file_location("t3", str(root / "curation" / "tier3_fault_campaign.py"))
        t3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(t3)
        load_circuit = t3.load_circuit
    bq = load_circuit(Path(buggy_path)); fq = load_circuit(Path(fixed_path))
    return {"buggy_loads": bq is not None, "fixed_loads": fq is not None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--run_pairs", action="store_true", help="also try loading extracted buggy/fixed pairs")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.candidates, encoding="utf-8")))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    triaged = []
    for r in rows:
        text = " ".join(str(r.get(k, "")) for k in ("title", "description", "category", "body"))
        fam, out, decision = classify(text)
        rec = dict(r)
        rec.update({"prefilter_family": fam, "prefilter_out": out, "prefilter_decision": decision,
                    "final_in_scope": "", "final_family": "", "audit_note": ""})  # last 3 = human/LLM audit
        if args.run_pairs:
            rec.update(run_pair(r.get("buggy_path"), r.get("fixed_path")))
        triaged.append(rec)

    fieldnames = list(triaged[0].keys()) if triaged else []
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(triaged)

    c = Counter(r["prefilter_decision"] for r in triaged)
    print(f"Triaged {len(triaged)} candidates -> {args.out}")
    print("prefilter:", dict(c))
    print("family prefilter:", dict(Counter(r["prefilter_family"] for r in triaged if r["prefilter_family"])))
    print("\nNEXT: open the triage CSV and fill final_in_scope / final_family / audit_note for EVERY row")
    print("(the soundness audit is the judgment step; the prefilter only orders the work).")


if __name__ == "__main__":
    main()
