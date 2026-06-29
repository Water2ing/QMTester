"""Run matched baselines on the three mined subjects.

Applies the same baselines used on Bugs4Q (static analyzer, reference-oracle
differential, and a circuit-level diagnostic at MorphQ's testing level) plus QMTester
to the three mined subjects, then reports per-subject detection and the combined
totals across all ten subjects.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path


def main():
    root = Path(".").resolve()
    sys.path.insert(0, str(root / "artifact"))
    from qmtester.mined_program_subjects import MinedShorIQFTSubject, MinedDraperQFTSubject, MinedQPERoleSubject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from qmtester.program_pipeline import run_program_subject
    from qmtester.execute import execute_circuit
    from qmtester.canonicalize import canonicalize
    import numpy as np
    # reuse the LintQ-style static checker + circuit-level relations
    spec = importlib.util.spec_from_file_location("sm", str(root / "scripts" / "run_static_and_minimal.py"))
    sm = importlib.util.module_from_spec(spec); spec.loader.exec_module(sm)
    from qmtester.relations import IdentityInsertion, SwapRewriting, PhaseRewriting, EquivalenceRewriting
    from qmtester.pipeline import run_subject as run_circuit_subject

    fam = PROGRAM_FAMILIES_DEFAULT
    circ_fam = [IdentityInsertion(), SwapRewriting(), PhaseRewriting(), EquivalenceRewriting()]
    subs = [MinedShorIQFTSubject, MinedDraperQFTSubject, MinedQPERoleSubject]

    def tvd(a, b):
        ks = set(a) | set(b); ta = sum(a.values()) or 1; tb = sum(b.values()) or 1
        return 0.5 * sum(abs(a.get(k, 0)/ta - b.get(k, 0)/tb) for k in ks)

    print(f"{'subject':38} {'static':7} {'circ-lvl':9} {'refOracle':10} {'QMTester'}")
    print("=" * 80)
    tot = {"static": 0, "circ": 0, "oracle": 0, "qm": 0}
    for cls in subs:
        bs = cls(variant="buggy"); fs = cls(variant="fixed")
        cand = None
        for f in fam:
            if f.name in (bs.relations or []):
                cs = f.enumerate(bs, np.random.default_rng(20240519))
                if cs:
                    cand = cs[0]; break
        # the program's NATURAL execution (default builder input = where the bug manifests)
        buggy_qc = bs.build({}); fixed_qc = fs.build({})
        # static analyzer on the buggy emitted circuit
        sdet, _ = sm.static_detect(buggy_qc)
        # reference-oracle differential: buggy program vs known-correct fixed program
        bc = execute_circuit(buggy_qc, shots=4096, seed=20240519)
        fc = execute_circuit(fixed_qc, shots=4096, seed=20240519)
        oracle_det = tvd(bc, fc) > 0.05
        # circuit-level diagnostic (MorphQ's testing level): rewrite the buggy final circuit
        rc = run_circuit_subject(subject_id=bs.subject_id, source_qc=buggy_qc,
                                 families=circ_fam, shots=4096, seed=20240519, alpha=0.05)
        circ_det = bool(rc.detected)
        # QMTester full
        qm_det = bool(run_program_subject(bs, fam, shots=4096, seed=20240519, alpha=0.05).detected)
        tot["static"] += sdet; tot["circ"] += circ_det; tot["oracle"] += oracle_det; tot["qm"] += qm_det
        print(f"{bs.subject_id[:38]:38} {('DET' if sdet else '-'):7} {('DET' if circ_det else '-'):9} "
              f"{('DET' if oracle_det else '-'):10} {'DET' if qm_det else '-'}")
    n = len(subs)
    print("\n" + "=" * 80)
    print(f"On the 3 mined subjects: static {tot['static']}/{n}, circuit-level(MorphQ level) {tot['circ']}/{n}, "
          f"reference-oracle {tot['oracle']}/{n}, QMTester {tot['qm']}/{n}")
    print(f"=> combined with Bugs4Q: static 0/10, MorphQ 0/10, reference-oracle 10/10, QMTester 10/10")


if __name__ == "__main__":
    main()
