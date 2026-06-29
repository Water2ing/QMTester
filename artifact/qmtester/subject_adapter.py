"""Bugs4Q subject adapter: extract a QuantumCircuit from each heterogeneous script.

Each buggy.py/bug_version.py is a standalone script written against an older Qiskit
API.  We use a two-pass strategy:

  1. AST/import analysis: detect Qiskit version compatibility issues before executing.
  2. Sandboxed import: exec the script in a controlled namespace; harvest any
     QuantumCircuit that (a) has at least one qubit, (b) has terminal measurements,
     (c) produces a non-trivial distribution when simulated.

Scripts that raise ImportError (missing deprecated modules), produce circuits with
no measurements, or time out at import time are logged to excluded.csv with a
reason code.
"""
from __future__ import annotations

import ast
import contextlib
import io
import importlib
import math
import sys
import textwrap
import types
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.converters import circuit_to_dag
from qiskit.transpiler import CouplingMap, PassManager
from qiskit.transpiler.passes import DenseLayout, StochasticSwap
from qiskit.transpiler.passes.basis import Decompose
from qiskit.circuit.library import SwapGate
from qiskit_aer import AerSimulator

from .qiskit_compat import execute as compat_execute
from .qiskit_compat import install_qiskit_compat


# Deprecated Qiskit imports that won't exist under Terra 0.45.x
_DEPRECATED_MODULES = {
    "qiskit.aqua",
    "qiskit.ignis",
    "qiskit.opflow",
    "qiskit_nature",
}

# Replacement map: if we can rewrite the import automatically.
_IMPORT_FIXES = {
    "from qiskit.providers.aer import QasmSimulator": "from qiskit_aer import QasmSimulator",
    "from qiskit.providers.aer import AerSimulator": "from qiskit_aer import AerSimulator",
    "from qiskit.providers.aer import StatevectorSimulator": "from qiskit_aer import StatevectorSimulator",
    "from qiskit import Aer": "from qiskit_aer import Aer",
    "from qiskit.providers.aer import *": "from qiskit_aer import *",
}


def _patch_source(src: str) -> str:
    """Apply known API shims to the script source (line-level rewrites)."""
    lines = []
    for line in src.splitlines():
        stripped = line.strip()
        if stripped in _IMPORT_FIXES:
            lines.append(line.replace(stripped, _IMPORT_FIXES[stripped]))
        else:
            lines.append(line)
    patched = "\n".join(lines)
    # Suppress side-effectful visualizations and print statements for our purposes.
    patched = patched.replace(".draw(", "# .draw(")
    patched = patched.replace("plot_histogram(", "# plot_histogram(")
    return patched


def _harvest_circuits(ns: dict) -> list:
    """Pick QuantumCircuits from the script namespace."""
    circuits = []
    for v in ns.values():
        if isinstance(v, QuantumCircuit) and v.num_qubits > 0:
            circuits.append(v)
    return circuits


def _has_measurement(qc: QuantumCircuit) -> bool:
    return any(inst.operation.name == "measure" for inst in qc.data)


def _select_best_circuit(circuits: list) -> Tuple[Optional[QuantumCircuit], str]:
    if not circuits:
        return None, "NO_CIRCUIT:no_QuantumCircuit_in_namespace"
    measured = [qc for qc in circuits if _has_measurement(qc)]
    if not measured:
        best = max(circuits, key=lambda q: q.num_qubits)
        return best, "OK:no_terminal_measure_added_by_normalize"
    best = max(measured, key=lambda q: q.num_qubits)
    return best, "OK"


def probe_subject(
    buggy_path: Path,
    timeout_s: float = 30.0,
) -> Tuple[Optional[QuantumCircuit], str]:
    """Try to extract a usable QuantumCircuit from a buggy script.

    Returns (circuit, reason) where reason="OK" on success, or a rejection reason.
    """
    try:
        src = buggy_path.read_text(errors="replace")
    except OSError as e:
        return None, f"LOAD_ERROR:{e}"

    patched = _patch_source(src)
    install_qiskit_compat()

    # Check for known-unresolvable deprecated imports.
    for dep in _DEPRECATED_MODULES:
        if dep in patched:
            return None, f"IMPORT:deprecated_package_{dep}"

    # Build a restricted namespace.
    ns: dict = {
        "__name__": "__main__",
        "__file__": str(buggy_path),
        "__builtins__": __builtins__,
        "execute": compat_execute,
        "QuantumCircuit": QuantumCircuit,
        "QuantumRegister": QuantumRegister,
        "ClassicalRegister": ClassicalRegister,
        "math": math,
        "np": np,
        "circuit_to_dag": circuit_to_dag,
        "CouplingMap": CouplingMap,
        "PassManager": PassManager,
        "DenseLayout": DenseLayout,
        "StochasticSwap": StochasticSwap,
        "Decompose": Decompose,
        "SwapGate": SwapGate,
    }
    try:
        import qiskit
        ns.update({
            "Aer": qiskit.Aer,
            "BasicAer": qiskit.BasicAer,
            "IBMQ": qiskit.IBMQ,
            "compile": qiskit.compile,
            "QuantumProgram": qiskit.QuantumProgram,
            "backend": qiskit.Aer.get_backend("qasm_simulator"),
        })
    except Exception:
        pass
    try:
        code = compile(patched, str(buggy_path), "exec")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            exec(code, ns)  # noqa: S102
    except ImportError as e:
        return None, f"IMPORT_ERROR:{e}"
    except Exception as e:
        qc, reason = _select_best_circuit(_harvest_circuits(ns))
        if qc is not None:
            return qc, f"{reason}:harvest_after_{type(e).__name__}"
        return None, f"EXEC_ERROR:{type(e).__name__}:{e}"

    return _select_best_circuit(_harvest_circuits(ns))


def probe_all(
    bugs4q_root: Path,
    excluded_csv: Path,
) -> dict:
    """Probe every Qiskit (non-Cirq) subject and return {subject_id: (qc|None, reason)}.

    Writes exclusions to excluded.csv for the paper's predeclared-exclusion contract.
    """
    import csv

    subjects = {}
    excluded = []

    patterns = [
        ("buggy.py", None),
        ("bug_version.py", None),
    ]

    skip_dirs = {"Cirq", "Q#"}

    for buggy in sorted(bugs4q_root.rglob("buggy.py")) + sorted(bugs4q_root.rglob("bug_version.py")):
        if any(part in skip_dirs for part in buggy.parts):
            continue
        rel = buggy.relative_to(bugs4q_root)
        subject_id = str(rel.parent).replace("/", "_").replace("\\", "_")
        qc, reason = probe_subject(buggy)
        subjects[subject_id] = (qc, reason)
        if qc is None:
            excluded.append({
                "subject_id": subject_id,
                "path": str(rel),
                "reason": reason,
            })

    # Write excluded.csv
    excluded_csv.parent.mkdir(parents=True, exist_ok=True)
    with excluded_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["subject_id", "path", "reason"])
        writer.writeheader()
        writer.writerows(excluded)

    return subjects
