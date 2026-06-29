"""Stage 4: matched paired execution (Algorithm 1 lines 11-12).

Source and follow-up are executed under the identical backend, shot budget, seed
policy, and wall-clock timeout.  We use Qiskit Aer's AerSimulator.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

from . import DEFAULT_SHOTS, DEFAULT_TIMEOUT


def _build_backend(noise_model=None, method: str = "statevector") -> AerSimulator:
    if noise_model is not None:
        return AerSimulator(noise_model=noise_model, method="density_matrix")
    return AerSimulator(method=method)


def _strip_simulator_artifacts(qc: QuantumCircuit) -> QuantumCircuit:
    """Remove simulator save/snapshot ops before count-vector execution."""
    out = QuantumCircuit(*qc.qregs, *qc.cregs, name=qc.name)
    for inst in qc.data:
        name = inst.operation.name
        if name.startswith("save_") or name.startswith("snapshot"):
            continue
        out.append(inst)
    return out


def execute_circuit(
    qc: QuantumCircuit,
    shots: int = DEFAULT_SHOTS,
    seed: int = 0,
    noise_model=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[Dict[str, int]]:
    """Run a single circuit and return a counts dict, or None on timeout/error."""
    backend = _build_backend(noise_model=noise_model)
    try:
        t0 = time.monotonic()
        tqc = transpile(_strip_simulator_artifacts(qc), backend, optimization_level=0)
        job = backend.run(tqc, shots=shots, seed_simulator=seed)
        result = job.result()
        if time.monotonic() - t0 > timeout:
            return None
        counts = result.get_counts()
        if isinstance(counts, list):
            merged: Dict[str, int] = {}
            for item in counts:
                if isinstance(item, dict):
                    for key, value in item.items():
                        merged[key] = merged.get(key, 0) + int(value)
            counts = merged
        counts = dict(counts)
        return counts if counts else None
    except Exception:
        return None


def execute_pair(
    source: QuantumCircuit,
    followup: QuantumCircuit,
    shots: int = DEFAULT_SHOTS,
    seed: int = 0,
    noise_model=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[Optional[Dict[str, int]], Optional[Dict[str, int]]]:
    """Execute source and follow-up under identical settings."""
    src_counts = execute_circuit(source, shots=shots, seed=seed,
                                 noise_model=noise_model, timeout=timeout)
    if src_counts is None:
        return None, None
    fu_counts = execute_circuit(followup, shots=shots, seed=seed,
                                noise_model=noise_model, timeout=timeout)
    return src_counts, fu_counts
