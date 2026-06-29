"""Audit a fetched Tier 3 corpus -- run in .venv_curation (the campaign's pre-1.0 env).

This is the ground-truth check that a fetch actually produced a USABLE corpus. A file
saving successfully in the fetch env (Qiskit >=1.0) does NOT guarantee it (a) re-loads in
the pre-1.0 campaign env or (b) has rotation sites -- and Tier 3's period-shift sweep is a
no-op on programs with zero rotation sites (it silently skips them). This script reports,
using the EXACT load path and PERIOD_PI gate set the campaign uses:

  * loads OK / fails to re-load here (the cross-version QASM2 round-trip)
  * programs WITH vs WITHOUT rotation sites (the ones Tier 3 can actually sweep)
  * per-family breakdown and the total rotation-site count

Usage:
  source .venv_curation/bin/activate
  python curation/audit_corpus.py --corpus_dir curation/corpus
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path


def _load_with_error(path):
    """Mirror tier3_fault_campaign.load_circuit, but surface WHY a load failed."""
    from qiskit import QuantumCircuit
    ns = {"__name__": "__main__", "__file__": str(path), "__builtins__": __builtins__}
    try:
        exec(compile(path.read_text(), str(path), "exec"), ns)  # noqa: S102
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e).splitlines()[0][:140]}"
    cands = [v for v in ns.values() if isinstance(v, QuantumCircuit) and v.num_qubits > 0]
    if not cands:
        return None, "no QuantumCircuit object produced"
    return max(cands, key=lambda c: len(c.data)), None


def _family(stem: str) -> str:
    parts = stem.split("_")
    while parts and parts[-1].isdigit():
        parts.pop()
    return "_".join(parts) or stem


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus_dir", default="curation/corpus")
    ap.add_argument("--root", default=".")
    ap.add_argument("--show", type=int, default=12, help="how many examples to list per issue")
    args = ap.parse_args()

    # Reuse the campaign's authoritative rotation accounting so this audit and the run agree.
    sys.path.insert(0, str(Path(args.root).resolve() / "curation"))
    from tier3_fault_campaign import shift_rotations, ensure_measured, PERIOD_PI

    progs = sorted(Path(args.corpus_dir).glob("*.py"))
    if not progs:
        sys.exit(f"No .py programs in {args.corpus_dir}")

    load_fail, zero_rot, with_rot, parameterized = [], [], [], []
    total_rot = 0
    by_family = defaultdict(lambda: {"n": 0, "loads": 0, "with_rot": 0, "rot": 0})
    gate_hist = defaultdict(int)

    for p in progs:
        fam = _family(p.stem)
        by_family[fam]["n"] += 1
        qc, err = _load_with_error(p)
        if qc is None:
            load_fail.append((p.name, err))
            continue
        by_family[fam]["loads"] += 1
        if getattr(qc, "num_parameters", 0):
            parameterized.append((p.name, qc.num_parameters))
        qc = ensure_measured(qc)
        # Mirror the campaign: surface rotations buried in custom gate blocks before counting.
        try:
            from tier3_fault_campaign import expose_rotations
            qc = expose_rotations(qc)
        except Exception:
            pass
        _, n_rot = shift_rotations(qc, 0.0)
        for ci in qc.data:
            nm = ci.operation.name.lower()
            if nm in PERIOD_PI:
                gate_hist[nm] += 1
        total_rot += n_rot
        if n_rot == 0:
            zero_rot.append(p.name)
        else:
            with_rot.append((p.name, n_rot))
            by_family[fam]["with_rot"] += 1
            by_family[fam]["rot"] += n_rot

    n = len(progs)
    n_load = n - len(load_fail)
    print("=" * 70)
    print(f"CORPUS AUDIT  {args.corpus_dir}   ({n} files)")
    print("=" * 70)
    print(f"  load OK (re-loads in this pre-1.0 env): {n_load}/{n}")
    print(f"  with rotation sites (Tier 3 can sweep): {len(with_rot)}/{n_load}")
    print(f"  zero rotation sites (silently skipped): {len(zero_rot)}/{n_load}")
    print(f"  total rotation sites across corpus:     {total_rot}")
    print(f"  rotation-gate histogram:                {dict(sorted(gate_hist.items()))}")

    print("\n  per family (files | load | with-rot | rot-sites):")
    for fam in sorted(by_family):
        d = by_family[fam]
        print(f"    {fam:<22} {d['n']:>3} | {d['loads']:>3} | {d['with_rot']:>3} | {d['rot']:>4}")

    if load_fail:
        print(f"\n  !! {len(load_fail)} FILE(S) FAIL TO RE-LOAD HERE "
              "(saved in the fetch env but broken for the campaign):")
        for name, err in load_fail[:args.show]:
            print(f"     {name}: {err}")

    if parameterized:
        print(f"\n  !! {len(parameterized)} FILE(S) HAVE UNBOUND PARAMETERS "
              "(un-runnable in Aer, invisible to the rotation sweep):")
        for name, k in parameterized[:args.show]:
            print(f"     {name}: {k} free parameter(s)")

    if with_rot:
        rich = sorted(with_rot, key=lambda x: -x[1])[:args.show]
        print(f"\n  top rotation-rich programs: " + ", ".join(f"{nm}({k})" for nm, k in rich))

    # Verdict tuned to what Tier 3 needs: enough rotation-bearing programs across families.
    fams_with_rot = sum(1 for d in by_family.values() if d["with_rot"] > 0)
    print("\n" + "-" * 70)
    if load_fail:
        print(f"PROBLEM: {len(load_fail)} program(s) do not re-load in the campaign env "
              "(cross-version QASM2). The campaign would silently skip these.")
    if parameterized:
        print(f"PROBLEM: {len(parameterized)} program(s) have unbound parameters; re-fetch "
              "with random_parameters pinned (the fetcher now asserts this).")
    if len(with_rot) < 10:
        print(f"PROBLEM: only {len(with_rot)} program(s) have rotation sites -- Tier 3's "
              "power surface would rest on too few real programs.")
    elif fams_with_rot < 3:
        print(f"WEAK: rotation sites concentrated in {fams_with_rot} families; want broader "
              "coverage of the 5 contract surfaces.")
    if not load_fail and not parameterized and len(with_rot) >= 10 and fams_with_rot >= 3:
        print(f"OK: {len(with_rot)} rotation-bearing programs across {fams_with_rot} families, "
              f"{total_rot} rotation sites, 0 load failures. Corpus is usable for Tier 3.")
    print("-" * 70)
    # Non-zero exit if the corpus can't support the campaign, for CI/scripting.
    sys.exit(1 if (load_fail or parameterized or len(with_rot) < 10) else 0)


if __name__ == "__main__":
    main()
