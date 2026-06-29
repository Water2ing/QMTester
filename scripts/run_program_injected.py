"""Run builder-level program mutation smoke evaluation."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--run_id", default=os.environ.get("QMT_RUN_ID", "manual"))
    p.add_argument("--manifest", default="data/manifests/program_mutants_manifest.csv")
    p.add_argument("--enabled_families", nargs="+", default=[
        "program_input_permutation",
        "program_classical_remap",
        "program_qft_round_trip",
        "program_parameter_periodicity",
        "program_ancilla_uncompute",
    ])
    p.add_argument("--with_morphq", action="store_true")
    args = p.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

    from qmtester.program_mutants import load_program_mutation_cases
    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from baselines.morphq_runner import run_morphq

    label = "full" if set(args.enabled_families) == {
        "program_input_permutation",
        "program_classical_remap",
        "program_qft_round_trip",
        "program_parameter_periodicity",
        "program_ancilla_uncompute",
    } else "_".join(args.enabled_families)
    raw_path = out_dir / f"program_injected_{label}.jsonl"
    summary_path = out_dir / f"program_injected_summary_{label}.jsonl"
    morphq_path = out_dir / f"program_injected_morphq_{label}.jsonl"

    for case in load_program_mutation_cases(root, root / args.manifest):
        for variant, subject, expected in [
            ("fixed", case.fixed_subject, False),
            ("mutant", case.mutant_subject, True),
        ]:
            base_subject_id = subject.subject_id
            subject.subject_id = f"{case.mutant_id}_{variant}"
            result = run_program_subject(
                subject,
                PROGRAM_FAMILIES_DEFAULT,
                shots=args.shots,
                seed=args.seed,
                alpha=args.alpha,
                log_path=raw_path,
                enabled_families=args.enabled_families,
                run_id=args.run_id,
            )
            row = {
                "run_id": args.run_id,
                "mutant_id": case.mutant_id,
                "source_id": case.source_id,
                "operator": case.operator,
                "relation_family": case.relation_family,
                "variant": variant,
                "base_subject_id": base_subject_id,
                "program_subject_id": subject.subject_id,
                "method": "qmtester_program",
                "detected": result.detected,
                "expected_detected": expected,
                "matches_expected": result.detected == expected,
                "n_admitted": len(result.admitted_pairs),
                "n_rejected": result.rejected_count,
                "min_p": result.min_p,
                "corrected_alpha": result.corrected_alpha,
                "source_path": case.source_path,
                "fixed_path": case.fixed_path,
            }
            with summary_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(
                f"{case.mutant_id}/{variant}: detected={result.detected} "
                f"expected={expected} n_admitted={len(result.admitted_pairs)}"
            )

        if args.with_morphq:
            source_qc = _morphq_source_circuit(case)
            m_result = run_morphq(
                subject_id=case.mutant_id,
                source_qc=source_qc,
                shots=args.shots,
                seed=args.seed,
                log_path=morphq_path,
                run_id=args.run_id,
            )
            mrow = {
                "run_id": args.run_id,
                "mutant_id": case.mutant_id,
                "source_id": case.source_id,
                "operator": case.operator,
                "relation_family": case.relation_family,
                "variant": "mutant",
                "base_subject_id": case.source_id,
                "program_subject_id": case.mutant_id,
                "method": "morphq",
                "detected": m_result.detected,
                "expected_detected": case.expected_detected,
                "matches_expected": m_result.detected == case.expected_detected,
                "n_admitted": len(m_result.admitted_pairs),
                "n_rejected": m_result.rejected_count,
                "min_p": m_result.min_p,
                "corrected_alpha": m_result.corrected_alpha,
                "source_path": case.source_path,
                "fixed_path": case.fixed_path,
            }
            with summary_path.open("a") as f:
                f.write(json.dumps(mrow) + "\n")


def _morphq_source_circuit(case):
    subject = case.mutant_subject
    method = {
        "program_input_permutation": "enumerate_input_permutation",
        "program_classical_remap": "enumerate_classical_remap",
        "program_qft_round_trip": "enumerate_qft_round_trip",
        "program_parameter_periodicity": "enumerate_parameter_periodicity",
        "program_ancilla_uncompute": "enumerate_ancilla_uncompute",
    }[case.relation_family]
    candidate = getattr(subject, method)(None)[0]
    return subject.build(candidate.source_input)


if __name__ == "__main__":
    main()
