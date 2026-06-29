"""Build frozen 100-case builder-level program mutant manifest."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


def _tvd(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    ta = sum(a.values()) or 1
    tb = sum(b.values()) or 1
    return 0.5 * sum(abs(a.get(k, 0) / ta - b.get(k, 0) / tb) for k in keys)


def _first_candidate(subject, family: str):
    method = {
        "program_input_permutation": "enumerate_input_permutation",
        "program_classical_remap": "enumerate_classical_remap",
        "program_qft_round_trip": "enumerate_qft_round_trip",
        "program_parameter_periodicity": "enumerate_parameter_periodicity",
        "program_ancilla_uncompute": "enumerate_ancilla_uncompute",
    }[family]
    candidates = getattr(subject, method)(None)
    if not candidates:
        raise ValueError(f"{subject.subject_id} has no candidate for {family}")
    return candidates[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="data/manifests/program_mutants_manifest.csv")
    p.add_argument("--shots", type=int, default=4096)
    p.add_argument("--effect_shots", type=int, default=8192)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--min_tvd", type=float, default=0.02)
    args = p.parse_args()

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "artifact"))

    from qmtester.canonicalize import canonicalize
    from qmtester.execute import execute_circuit
    from qmtester.program_mutants import FAMILY_TARGET_COUNTS, generate_program_mutation_cases
    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT

    rows = []
    failures = []
    for case in generate_program_mutation_cases(root, args.seed):
        fixed = run_program_subject(
            case.fixed_subject, PROGRAM_FAMILIES_DEFAULT,
            shots=args.shots, seed=case.seed, alpha=0.05,
        )
        mutant = run_program_subject(
            case.mutant_subject, PROGRAM_FAMILIES_DEFAULT,
            shots=args.shots, seed=case.seed, alpha=0.05,
        )
        cand = _first_candidate(case.fixed_subject, case.relation_family)
        source_counts = execute_circuit(
            case.fixed_subject.build(cand.source_input),
            shots=args.effect_shots,
            seed=case.seed + 1000,
        )
        mutant_counts = execute_circuit(
            case.mutant_subject.build(cand.followup_input),
            shots=args.effect_shots,
            seed=case.seed + 1000,
        )
        if source_counts is None or mutant_counts is None:
            failures.append((case.mutant_id, "execution_failed_for_tvd"))
            continue
        ok, reason, src_can, mut_can = canonicalize(source_counts, mutant_counts, cand.canon_map)
        if not ok:
            failures.append((case.mutant_id, reason))
            continue
        case.effect_tvd = _tvd(src_can, mut_can)
        if fixed.detected:
            failures.append((case.mutant_id, "fixed_variant_detected"))
            continue
        if not mutant.detected:
            failures.append((case.mutant_id, "mutant_variant_not_detected"))
            continue
        if case.effect_tvd < args.min_tvd:
            failures.append((case.mutant_id, f"effect_tvd_below_min:{case.effect_tvd:.8f}"))
            continue
        rows.append(case.manifest_row())

    counts = Counter(r["relation_family"] for r in rows)
    for family, expected in FAMILY_TARGET_COUNTS.items():
        if counts[family] != expected:
            failures.append((family, f"family_count_{counts[family]}_expected_{expected}"))

    if failures:
        print("FATAL: program mutant manifest validation failed", file=sys.stderr)
        for item, reason in failures[:50]:
            print(f"  {item}: {reason}", file=sys.stderr)
        if len(failures) > 50:
            print(f"  ... {len(failures) - 50} more", file=sys.stderr)
        sys.exit(1)

    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "mutant_id", "source_id", "relation_family", "operator", "site", "seed",
        "fixed_subject", "mutant_subject", "effect_tvd", "expected_detected",
        "source_path", "fixed_path",
    ]
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} validated program mutants -> {out}")
    for family in sorted(FAMILY_TARGET_COUNTS):
        print(f"  {family}: {counts[family]}")


if __name__ == "__main__":
    main()
