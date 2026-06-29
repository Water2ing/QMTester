"""Run hand-audited Bugs4Q program-level metamorphic subjects.

This runner is intentionally separate from ``run_bugs4q.py``.  The latter is a
circuit-level diagnostic path over every runnable Qiskit script; this file only
runs Bugs4Q cases whose bug has been manually promoted to a sound program/input
relation.
"""
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
    p.add_argument("--variant", choices=["buggy", "fixed", "both"], default="both")
    p.add_argument("--manifest", default="data/manifests/program_bugs4q_manifest.csv")
    p.add_argument("--with_morphq", action="store_true")
    args = p.parse_args()

    root = Path(args.root).resolve()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root / "artifact"))
    sys.path.insert(0, str(root))

    from qmtester.bugs4q_program_subjects import load_bugs4q_program_subjects
    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT
    from baselines.morphq_runner import run_morphq

    variants = ["buggy", "fixed"] if args.variant == "both" else [args.variant]
    raw_path = out_dir / "program_bugs4q.jsonl"
    summary_path = out_dir / "program_bugs4q_summary.jsonl"
    morphq_path = out_dir / "program_bugs4q_morphq.jsonl"
    allowed = _load_allowed_subjects(root / args.manifest)

    for variant in variants:
        for subject in load_bugs4q_program_subjects(root, variant=variant):
            if allowed is not None and subject.subject_id not in allowed:
                continue
            base_subject_id = subject.subject_id
            subject.subject_id = f"{base_subject_id}_{variant}"
            result = run_program_subject(
                subject,
                PROGRAM_FAMILIES_DEFAULT,
                shots=args.shots,
                seed=args.seed,
                alpha=args.alpha,
                log_path=raw_path,
                run_id=args.run_id,
            )
            row = {
                "run_id": args.run_id,
                "subject_id": base_subject_id,
                "program_subject_id": subject.subject_id,
                "variant": variant,
                "method": "qmtester_program",
                "bug_category": subject.bug_category,
                "source_path": str(subject.source_path) if subject.source_path else None,
                "fixed_path": str(subject.fixed_path) if subject.fixed_path else None,
                "detected": result.detected,
                "n_admitted": len(result.admitted_pairs),
                "n_rejected": result.rejected_count,
                "min_p": result.min_p,
                "corrected_alpha": result.corrected_alpha,
                "unsupported": result.unsupported,
                "unsupported_reason": result.unsupported_reason,
            }
            with summary_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(
                f"{subject.subject_id}: detected={result.detected} "
                f"n_admitted={len(result.admitted_pairs)} min_p={result.min_p}"
            )
            if args.with_morphq and variant == "buggy":
                source_qc = _morphq_source_circuit(subject)
                m_result = run_morphq(
                    subject_id=subject.subject_id,
                    source_qc=source_qc,
                    shots=args.shots,
                    seed=args.seed,
                    log_path=morphq_path,
                    run_id=args.run_id,
                )
                mrow = {
                    "run_id": args.run_id,
                    "subject_id": base_subject_id,
                    "program_subject_id": subject.subject_id,
                    "variant": variant,
                    "method": "morphq",
                    "bug_category": subject.bug_category,
                    "source_path": str(subject.source_path) if subject.source_path else None,
                    "fixed_path": str(subject.fixed_path) if subject.fixed_path else None,
                    "detected": m_result.detected,
                    "n_admitted": len(m_result.admitted_pairs),
                    "n_rejected": m_result.rejected_count,
                    "min_p": m_result.min_p,
                    "corrected_alpha": m_result.corrected_alpha,
                    "unsupported": m_result.unsupported,
                    "unsupported_reason": m_result.unsupported_reason,
                }
                with summary_path.open("a") as f:
                    f.write(json.dumps(mrow) + "\n")


def _load_allowed_subjects(path: Path):
    if not path.exists():
        return None
    import csv
    with path.open(newline="") as f:
        return {row["subject_id"] for row in csv.DictReader(f)}


def _morphq_source_circuit(subject):
    relation = subject.relations[0]
    method = {
        "program_input_permutation": "enumerate_input_permutation",
        "program_classical_remap": "enumerate_classical_remap",
        "program_qft_round_trip": "enumerate_qft_round_trip",
        "program_parameter_periodicity": "enumerate_parameter_periodicity",
        "program_ancilla_uncompute": "enumerate_ancilla_uncompute",
    }[relation]
    candidate = getattr(subject, method)(None)[0]
    return subject.build(candidate.source_input)


if __name__ == "__main__":
    main()
