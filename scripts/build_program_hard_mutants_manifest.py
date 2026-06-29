"""Build supplemental lower-effect program mutant manifest."""
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


def _first_candidate(subject):
    candidates = subject.enumerate_parameter_periodicity(None)
    if not candidates:
        raise ValueError(f"{subject.subject_id} has no hard parameter candidate")
    return candidates[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="data/manifests/program_hard_mutants_manifest.csv")
    p.add_argument("--shots", type=int, default=8192)
    p.add_argument("--effect_shots", type=int, default=32768)
    p.add_argument("--seed", type=int, default=20240519)
    p.add_argument("--min_tvd", type=float, default=0.02)
    p.add_argument("--max_tvd", type=float, default=0.20)
    p.add_argument("--expected_count", type=int, default=20)
    args = p.parse_args()

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "artifact"))

    from qmtester.canonicalize import canonicalize
    from qmtester.execute import execute_circuit
    from qmtester.program_mutants import generate_hard_program_mutation_cases
    from qmtester.program_pipeline import run_program_subject
    from qmtester.program_relations import PROGRAM_FAMILIES_DEFAULT

    rows = []
    failures = []
    for case in generate_hard_program_mutation_cases(root, args.seed):
        fixed = run_program_subject(
            case.fixed_subject,
            PROGRAM_FAMILIES_DEFAULT,
            shots=args.shots,
            seed=case.seed,
            alpha=0.05,
        )
        mutant = run_program_subject(
            case.mutant_subject,
            PROGRAM_FAMILIES_DEFAULT,
            shots=args.shots,
            seed=case.seed,
            alpha=0.05,
        )
        cand = _first_candidate(case.fixed_subject)
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
        if case.effect_tvd > args.max_tvd:
            failures.append((case.mutant_id, f"effect_tvd_above_max:{case.effect_tvd:.8f}"))
            continue
        rows.append(case.manifest_row())

    counts = Counter(r["relation_family"] for r in rows)
    if len(rows) != args.expected_count:
        failures.append(("program_hard_mutants", f"count_{len(rows)}_expected_{args.expected_count}"))
    if set(counts) != {"program_parameter_periodicity"}:
        failures.append(("program_hard_mutants", f"unexpected_families:{dict(counts)}"))

    if failures:
        print("FATAL: hard program mutant manifest validation failed", file=sys.stderr)
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

    tvds = [float(r["effect_tvd"]) for r in rows]
    print(f"Wrote {len(rows)} validated hard program mutants -> {out}")
    print(f"  program_parameter_periodicity: {counts['program_parameter_periodicity']}")
    print(f"  tvd_min={min(tvds):.8f} tvd_max={max(tvds):.8f}")


if __name__ == "__main__":
    main()
