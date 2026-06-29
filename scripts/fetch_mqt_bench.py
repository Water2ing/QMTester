"""Fetch a DIVERSE corpus of correct quantum programs from MQT Bench as .py files.

Run in the .venv_fetch env (mqt.bench + Qiskit >=1.0). Each program is saved as a
standalone Python file that rebuilds a QuantumCircuit when exec'd, serialized via
OpenQASM 2 so the pre-1.0 campaign env (.venv_curation) can load it unchanged.

Version-robustness: MQT Bench v2 changed get_benchmark's signature
(``get_benchmark(name, BenchmarkLevel.ALG, n)`` -- positional, ``level`` is now an
enum) and renamed/removed several v1 benchmark names. Hardcoding a name list drifts
across versions and silently produces an all-skip run. Instead we ENUMERATE the names
the installed library actually offers (``get_available_benchmark_names``) and sweep
them over a size ladder, adapting to whichever API (v1 or v2) is present.

Anti-footgun: the synthetic GHZ/QFT fallback is OPT-IN (``--allow-synthetic``). A
synthetic-only corpus is degenerate for Tier 3 (GHZ has no rotation sites, so the
period-shift campaign skips every GHZ), so by default a failed fetch EXITS NON-ZERO
instead of writing 200 useless programs that look like success.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Size ladder, breadth-first: size 4 sweeps every available algorithm once (max
# diversity for any --n), then scaling sizes for the families that take them.
SIZE_LADDER = [4, 3, 5, 2, 6, 8, 10, 12, 14, 16]

# v1-only fallback table (used only when the installed mqt.bench predates
# get_available_benchmark_names). v2 enumerates names directly.
V1_ALGORITHMS = [
    ("ae", 3), ("dj", 4), ("ghz", 4), ("graphstate", 4), ("qft", 4),
    ("qftentangled", 4), ("qnn", 4), ("qpeexact", 4), ("qpeinexact", 4),
    ("realamprandom", 4), ("su2random", 4), ("twolocalrandom", 4), ("vqe", 4),
    ("wstate", 4), ("portfolioqaoa", 4), ("portfoliovqe", 4),
]


def _make_builder():
    """Return a build(name, n) -> QuantumCircuit closure for the installed API.

    v2: get_benchmark(name, BenchmarkLevel.ALG, n)   (positional, enum level)
    v1: get_benchmark(benchmark_name=name, level="alg", circuit_size=n)
    """
    from mqt.bench import get_benchmark
    level = None
    try:
        from mqt.bench import BenchmarkLevel
        level = BenchmarkLevel.ALG
    except Exception:
        level = None

    def build(name, n):
        if level is not None:                       # v2
            # Pin random_parameters=True so ALG-level ansatze ship BOUND concrete
            # angles, not free symbolic Parameters. Unbound params can't be QASM2-
            # serialized (fetch fails) nor simulated (campaign drops them) -- and the
            # failure would be silent. Pinning makes a future default-flip a no-op.
            try:
                qc = get_benchmark(name, level, n, random_parameters=True)
            except TypeError:
                qc = get_benchmark(name, level, n)  # older v2 without the kwarg
        else:
            qc = get_benchmark(benchmark_name=name, level="alg", circuit_size=n)  # v1
        # Hard guard: a circuit with free parameters is unusable downstream. Fail loud
        # at fetch rather than degrade silently if upstream defaults ever change.
        if getattr(qc, "num_parameters", 0):
            raise ValueError(f"{name}_{n} has {qc.num_parameters} unbound parameter(s)")
        return qc

    return build, (level is not None)


def _available_names():
    """Enumerate valid benchmark names from the installed mqt.bench, or None (v1)."""
    for mod in ("mqt.bench", "mqt.bench.benchmarks"):
        try:
            m = importlib.import_module(mod)
        except Exception:
            continue
        fn = getattr(m, "get_available_benchmark_names", None)
        if fn is not None:
            try:
                return sorted(fn())
            except Exception:
                pass
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=50, help="max programs to write")
    p.add_argument("--allow-synthetic", action="store_true",
                   help="permit (and top up with) synthetic GHZ/QFT circuits. OFF by "
                        "default: a synthetic-only corpus is degenerate for Tier 3.")
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        importlib.import_module("mqt.bench")
    except ImportError as e:
        msg = (f"mqt.bench not importable ({e}).")
        if args.allow_synthetic:
            print(f"{msg} Generating synthetic GHZ/QFT circuits (--allow-synthetic).")
            _generate_synthetic(out_dir, args.n)
            print(f"Total: {len(list(out_dir.glob('*.py')))} (synthetic) programs in {out_dir}")
            return
        sys.exit(f"FATAL: {msg}\nRefusing to write a synthetic-only corpus (it is degenerate "
                 "for Tier 3: GHZ has no rotation sites). Install mqt.bench in .venv_fetch, "
                 "or pass --allow-synthetic to override.")

    build, is_v2 = _make_builder()
    names = _available_names()
    print(f"mqt.bench API: {'v2 (enum level)' if is_v2 else 'v1 (kwargs)'}; "
          f"{'enumerated ' + str(len(names)) + ' benchmark names' if names else 'name enumeration unavailable -> v1 table'}")

    # Build the (name, size) plan: breadth-first over the size ladder.
    if names:
        plan = [(nm, s) for s in SIZE_LADDER for nm in names]
    else:
        plan = [(nm, n) for (nm, n) in V1_ALGORITHMS]

    written, rescued, skipped = 0, 0, []
    for name, n in plan:
        if written >= args.n:
            break
        try:
            qc = build(name, n)
        except Exception as e:
            skipped.append((name, n, str(e).splitlines()[0][:120]))
            continue
        out_file = out_dir / f"{name}_{n}.py"
        method = _save_qc_as_py(qc, out_file, f"{name}_{n}")
        if method is None:
            skipped.append((name, n, "QASM2 serialization failed (even after decompose/transpile)"))
            continue
        written += 1
        if method != "direct":
            rescued += 1
        print(f"  saved {out_file.name} ({qc.num_qubits}q)"
              f"{'' if method == 'direct' else ' [' + method + ']'}")

    # Report what was skipped so a low yield is visible, not silent.
    if skipped:
        print(f"\n  skipped {len(skipped)} (name,size) combos; first few:")
        for name, n, why in skipped[:8]:
            print(f"    skip {name} {n}q: {why}")

    if written == 0:
        if args.allow_synthetic:
            print("\nNo real mqt.bench programs built; falling back to synthetic (--allow-synthetic).")
            _generate_synthetic(out_dir, args.n)
        else:
            sys.exit("\nFATAL: 0 real mqt.bench programs were built (every get_benchmark call "
                     "failed). This is the all-skip footgun -- usually an API/version mismatch. "
                     "Fix the API or pass --allow-synthetic (degenerate) to proceed anyway.")
    elif written < args.n and args.allow_synthetic:
        print(f"\nTopping up {args.n - written} programs with synthetic circuits (--allow-synthetic).")
        _generate_synthetic(out_dir, args.n - written)

    total = len(list(out_dir.glob("*.py")))
    print(f"\nTotal: {total} programs in {out_dir} ({written} real mqt.bench"
          f"{f', {rescued} via decompose/transpile' if rescued else ''}"
          f"{', rest synthetic' if total > written else ''})")
    print("Next: audit rotation-site coverage in the campaign env:\n"
          "  source .venv_curation/bin/activate && python curation/audit_corpus.py "
          f"--corpus_dir {out_dir}")


# Last-resort rescue basis for circuits whose DIRECT qasm2.dumps raises (e.g. ae's
# StatePreparation/UnitaryGate). Every name round-trips into the qiskit 0.45 campaign
# env, and rx/ry/rz are rotation gates the Tier 3 sweep recognizes (PERIOD_PI), so a
# transpiled rescue still yields rotation sites. (Note: cp/crx/cry/crz/p DO resolve in
# 0.45's qasm2 qelib1 handling too, but transpiling to them is unnecessary for a rescue.)
_SAFE_BASIS = ["rx", "ry", "rz", "cx", "cz", "h", "x", "y", "z",
               "s", "sdg", "t", "tdg", "swap", "ccx", "id"]


def _to_qasm2(qc):
    """Return (qasm_str, method) or (None, None). Tries the cheapest faithful path
    first, then unrolls, then transpiles to a round-trip-safe basis as a last resort.

    `ae` (amplitude estimation) and similar fail direct dumps because ALG-level
    circuits embed StatePreparation / multi-controlled / UnitaryGate ops that QASM2
    cannot express; decompose/transpile lowers them to standard gates that can.
    """
    from qiskit import qasm2
    try:
        return qasm2.dumps(qc), "direct"
    except Exception:
        pass
    d = qc
    for _ in range(3):                       # unroll composite gates; keep native names
        try:
            d = d.decompose()
        except Exception:
            break
        try:
            return qasm2.dumps(d), "decompose"
        except Exception:
            continue
    try:                                     # force a QASM2-expressible basis
        from qiskit import transpile
        t = transpile(qc, basis_gates=_SAFE_BASIS, optimization_level=0)
        return qasm2.dumps(t), "transpile"
    except Exception:
        return None, None


def _save_qc_as_py(qc, path: Path, name: str):
    """Serialize qc to a QASM2-backed .py file. Returns the method str, or None.

    The loader tries plain qasm2.loads first, then falls back to
    LEGACY_CUSTOM_INSTRUCTIONS. Qiskit's QASM2 EXPORTER can emit gates (sx, csx, rzz,
    ...) as bare qelib1 calls that a STRICT importer does not define, so a circuit that
    dumps cleanly in the fetch env (Qiskit >=1.0) could raise QASM2ParseError on re-load
    in the campaign env (qiskit 0.45) and be silently dropped. The legacy instruction
    set restores those definitions. Plain-first avoids the redefinition conflicts that
    unconditionally forcing legacy builtins can cause for files that already carry their
    own `gate` definitions; the fallback only runs if the plain parse fails, so it can
    never make a currently-loadable file worse.
    """
    qasm_str, method = _to_qasm2(qc)
    if qasm_str is None:
        return None
    path.write_text(
        "from qiskit import qasm2\n"
        f"qasm_src = {qasm_str!r}\n"
        "try:\n"
        "    qc = qasm2.loads(qasm_src)\n"
        "except Exception:\n"
        "    qc = qasm2.loads(qasm_src, "
        "custom_instructions=getattr(qasm2, 'LEGACY_CUSTOM_INSTRUCTIONS', ()))\n"
    )
    return method


def _generate_synthetic(out_dir: Path, n: int) -> None:
    """Generate synthetic GHZ / QFT circuits as an explicit, opt-in fallback."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import QFT

    written = 0
    for k in range(2, 2 + n):
        num_q = (k % 8) + 2
        if k % 2 == 0:
            qc = QuantumCircuit(num_q, num_q, name=f"ghz_{num_q}")
            qc.h(0)
            for i in range(num_q - 1):
                qc.cx(i, i + 1)
            qc.measure_all(inplace=True, add_bits=False)
            name = f"ghz_{num_q}"
        else:
            qc = QFT(num_q).decompose()
            qc.measure_all()
            name = f"qft_{num_q}"

        if _save_qc_as_py(qc, out_dir / f"{name}_synth_{k}.py", name) is not None:
            written += 1
        if written >= n:
            break


if __name__ == "__main__":
    main()
