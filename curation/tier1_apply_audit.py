"""Tier 1 pre-audit for LintQ: apply a RULE-LEVEL builder-contract verdict to every triage
row, so the exhaustive in/out decision is documented for all 33,995 candidates without
hand-labelling each one. LintQ findings are rule-based, so the in/out call is largely a
function of the RULE (the bug pattern) -- this encodes that judgment, with a few
message-conditional refinements, then leaves a small shortlist of in-scope CANDIDATES for
the human/second-rater to confirm against the actual program source.

This does NOT replace the soundness audit; it makes it tractable and auditable. Every row
gets final_in_scope in {out, candidate} + a documented audit_note. 'candidate' rows are the
ones a sound metamorphic relation plausibly detects -> fetch source, build buggy/fixed pair,
verify, then flip to a real yes/no.

Usage (pure stdlib):
  python curation/tier1_apply_audit.py --triage curation/triage/LintQ_triage.csv \
      --out curation/triage/LintQ_triage_audited.csv
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

# rule_id -> (default_in_scope, family, note). 'candidate' = a sound relation plausibly
# applies (confirm against source); 'out' = documented out-of-scope.
RULE_VERDICT = {
    # measure_all() changes the classical register SHAPE (n -> 2n bits): a real classical-
    # register builder defect, but NOT a bijective remap, so no sound canonical map exists in
    # the current relation set. The Bugs4Q audit already excluded this exact pattern
    # (qiskit_github_12, bugs4q_program_subjects.py PROGRAM_BUGS4Q_EXCLUSIONS). -> counts for
    # PREVALENCE (R2 #6) but NOT for the detection base. A future 'register-shape' relation could cover it.
    "ql-measure-all-abuse": ("builder_no_relation", "program_classical_remap",
        "measure_all() with pre-existing classical bits changes register SHAPE (n->2n); real classical-"
        "register builder defect but not a bijective remap -> no sound canon map (cf. excluded qiskit_github_12). "
        "Prevalence-only; needs a future register-shape relation."),
    "ql-op-after-optimization": ("builder_no_relation", "program_classical_remap",
        "measure/measure_all applied after transpilation; same register-shape / ordering issue, no bijective remap."),
    "ql-ungoverned-composition": ("candidate", "program_input_permutation",
        "composition without an explicit qubit mapping can misalign qubits/registers; confirm per source ('no wiring' may be style-only)."),
    # message-conditional rules (refined in _refine below)
    "ql-ghost-composition": ("out", "",
        "ghost composition; IN only when the message is the missing-inverse-QFT case."),
    "ql-superfluous-op": ("out", "",
        "operation on never-measured qubits; IN only for a genuine un-uncomputed ancilla (teleportation garbage)."),
    "ql-superfluous-op-precise": ("out", "",
        "as ql-superfluous-op; IN only for genuine ancilla garbage."),
    "ql-oversized-circuit": ("out", "",
        "never-manipulated qubits (size metric); IN only for genuine dirty-ancilla mismanagement."),
    "ql-constant-classic-bit": ("out", "",
        "measured-but-unused classical bit; usually dead measurement; IN only for ancilla/teleportation cases."),
    # explicit OUT (spurious family from name keywords / different bug class)
    "ql-qc-size": ("out", "", "circuit size metric (qubits vs clbits); 'qft' in the name is coincidental, not a QFT bug."),
    "ql-unmeasurable-qubits": ("out", "", "qubits>clbits size metric; name-keyword match only."),
    "ql-operation-after-measurement": ("out", "", "op-after-measurement smell; not one of the 5 relations; 'ccx' is coincidental."),
    "ql-operation-after-measurement-general": ("out", "", "as ql-operation-after-measurement."),
    "ql-conditional-without-measurement": ("out", "", "classical-conditioned gate w/o measurement; different bug class."),
}
DEFAULT = ("out", "", "out-of-scope: api-misuse / code-smell / security / output-formatting (Bugs4Q audit taxonomy).")


def _refine(rule, desc, base):
    """Message-conditional overrides for rules whose in/out depends on the finding text."""
    d = (desc or "").lower()
    if rule == "ql-ghost-composition":
        if "qft" in d or "inverse" in d or "fourier" in d:
            return ("candidate", "program_qft_round_trip",
                    "missing inverse QFT (Shor) -> qft_round_trip relation detects the non-identity round trip.")
        return ("out", "", "ghost composition unrelated to QFT round-trip.")
    if rule in ("ql-superfluous-op", "ql-superfluous-op-precise"):
        if any(k in d for k in ("teleport", "ancilla", "garbage", "uncompute")):
            return ("candidate", "program_ancilla_uncompute",
                    "operation leaves an ancilla un-uncomputed (teleportation/garbage) -> ancilla-uncompute relation.")
        return DEFAULT
    if rule == "ql-oversized-circuit":
        # 'mcx_dirty_ancilla never manipulates some qubits' is a LintQ static FALSE POSITIVE:
        # dirty ancillas are a valid Qiskit pattern (mcx uses them internally), not an uncompute bug.
        return ("out", "", "size/dead-qubit metric; dirty-ancilla is a valid Qiskit pattern (LintQ FP), not a builder defect.")
    if rule == "ql-constant-classic-bit":
        if "teleport" in d or "ancilla" in d:
            return ("candidate", "program_ancilla_uncompute",
                    "measured-but-unused bit in an ancilla/teleportation context; confirm per source.")
        return DEFAULT
    return base


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--triage", default="curation/triage/LintQ_triage.csv")
    ap.add_argument("--out", default="curation/triage/LintQ_triage_audited.csv")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.triage, encoding="utf-8")))
    if not rows:
        raise SystemExit(f"no rows in {args.triage}")

    shortlist = []
    for r in rows:
        rule = r.get("rule_id") or r.get("title") or ""
        base = RULE_VERDICT.get(rule, DEFAULT)
        verdict, family, note = _refine(rule, r.get("description"), base)
        r["final_in_scope"] = verdict           # candidate | builder_no_relation | out
        r["final_family"] = family
        r["audit_note"] = note
        if verdict == "candidate":
            shortlist.append(r)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    bnr = [r for r in rows if r["final_in_scope"] == "builder_no_relation"]
    print(f"audited {len(rows)} rows -> {out}")
    print("final_in_scope:", dict(Counter(r["final_in_scope"] for r in rows)))
    print("  candidate     = promotable: a current sound relation plausibly detects it (confirm vs source)")
    print("  builder_no_relation = REAL builder-contract defect but no sound relation yet "
          "(counts for PREVALENCE R2#6, not the detection base)")
    print("  out           = not a builder-contract defect (api-misuse/smell/security/FP)")
    if bnr:
        print("\nbuilder_no_relation by family (prevalence-only):",
              dict(Counter(r["final_family"] for r in bnr)))
    print("candidate family:", dict(Counter(r["final_family"] for r in shortlist)))
    print(f"\n--- IN-SCOPE CANDIDATE SHORTLIST ({len(shortlist)}) -- confirm each against source ---")
    for r in sorted(shortlist, key=lambda r: (r["final_family"], r.get("rule_id", ""))):
        st = f" [{r.get('manual_status')}]" if r.get("manual_status") else ""
        print(f"  {r['final_family']:<28} {r.get('rule_id',''):<26} {r.get('lintq_file','')}{st}")
        print(f"       {(r.get('description') or '')[:100]}")
    print("\nNEXT: confirm the shortlist (flip 'candidate'->yes/no after checking source), then promote the")
    print("'yes' ones to ProgramSubjects. All 'out' rows are documented for the exhaustive denominator.")


if __name__ == "__main__":
    main()
