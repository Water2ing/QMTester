"""250-variant injected-fault generator (seed 20240519).

Generates controlled faults over the Bugs4Q source circuits, matching the
paper's evaluation (Table V: 250 mutator-generated variants, seed 20240519).

Fault operators (matching QMutPy-style categories in Table V):
  - gate_swap:       swap two adjacent single-qubit gates
  - qubit_index:     increment/decrement a qubit index by 1 (wraps)
  - gate_delete:     remove a single non-measurement gate
  - gate_replace:    replace a gate with a semantically different gate of same arity
  - phase_flip:      negate a rotation angle parameter
  - measurement_map: reorder which qubit maps to which classical bit
"""
from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from qiskit import QuantumCircuit

MASTER_SEED = 20240519  # matches qmtester.__init__.MASTER_SEED


def _to_plain_qc(qc: QuantumCircuit) -> QuantumCircuit:
    """Flatten any QuantumCircuit subclass (e.g. EfficientSU2) to a plain QuantumCircuit.

    Library circuit subclasses have a read-only .data property; assigning to it
    raises AttributeError. Normalizing to QuantumCircuit before mutation avoids this.
    """
    if type(qc) is QuantumCircuit:
        return qc
    out = QuantumCircuit(*qc.qregs, *qc.cregs, name=qc.name)
    for inst in qc.data:
        out.append(inst)
    return out


FAULT_OPS = [
    "gate_swap",
    "qubit_index",
    "gate_delete",
    "gate_replace",
    "phase_flip",
    "measurement_map",
]

_REPLACEMENT_MAP = {
    "h": "x", "x": "h", "y": "z", "z": "y",
    "s": "t", "t": "s", "cx": "cz", "cz": "cx",
    "rx": "ry", "ry": "rx", "rz": "rx",
    "sx": "x", "swap": "cx",
}


@dataclass
class MutantRecord:
    mutant_id: str
    source_id: str
    operator: str
    site: str
    circuit: QuantumCircuit
    effect_tvd: Optional[float] = None


def _ensure_measured(qc: QuantumCircuit) -> QuantumCircuit:
    plain = _to_plain_qc(qc)
    out = QuantumCircuit(*plain.qregs, *plain.cregs, name=plain.name)
    for inst in plain.data:
        name = inst.operation.name
        # Save/snapshot instructions are simulator artifacts, not program behavior.
        # They can collide after mutation and are irrelevant to count-vector TVD.
        if name.startswith("save_") or name.startswith("snapshot"):
            continue
        out.append(inst)
    if not any(inst.operation.name == "measure" for inst in out.data):
        out.measure_all(inplace=True)
    return out


def _coerce_counts(counts) -> Optional[dict]:
    if counts is None:
        return None
    if isinstance(counts, dict):
        return counts
    if isinstance(counts, list):
        merged: dict = {}
        for item in counts:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                merged[key] = merged.get(key, 0) + int(value)
        return merged if merged else None
    return None


def _counts(qc: QuantumCircuit, shots: int, seed: int) -> Optional[dict]:
    try:
        from qiskit_aer import AerSimulator
        backend = AerSimulator(seed_simulator=seed)
        job = backend.run(_ensure_measured(qc), shots=shots, seed_simulator=seed)
        return _coerce_counts(job.result().get_counts())
    except Exception:
        return None


def _tvd(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    na = sum(a.values()) or 1
    nb = sum(b.values()) or 1
    return 0.5 * sum(abs(a.get(k, 0) / na - b.get(k, 0) / nb) for k in keys)


def estimate_effect_tvd(
    source: QuantumCircuit,
    mutant: QuantumCircuit,
    shots: int = 8192,
    seed: int = MASTER_SEED,
) -> Optional[float]:
    """Estimate source-vs-mutant total variation distance with high-shot counts."""
    src_counts = _counts(source, shots, seed)
    mut_counts = _counts(mutant, shots, seed + 17)
    if src_counts is None or mut_counts is None:
        return None
    return _tvd(src_counts, mut_counts)


def _mutant_gate_swap(qc: QuantumCircuit, rng: random.Random) -> Optional[QuantumCircuit]:
    """Swap two adjacent non-measurement operations."""
    ops = [(i, inst) for i, inst in enumerate(qc.data)
           if inst.operation.name not in ("measure", "barrier")]
    if len(ops) < 2:
        return None
    i = rng.randrange(len(ops) - 1)
    idx1, inst1 = ops[i]
    idx2, inst2 = ops[i + 1]
    new_data = list(qc.data)
    new_data[idx1], new_data[idx2] = new_data[idx2], new_data[idx1]
    out = qc.copy()
    out.data = new_data
    return out


def _mutant_qubit_index(qc: QuantumCircuit, rng: random.Random) -> Optional[QuantumCircuit]:
    """Increment a qubit argument by 1 (mod num_qubits)."""
    ops = [(i, inst) for i, inst in enumerate(qc.data)
           if inst.operation.name not in ("measure", "barrier") and len(inst.qubits) == 1]
    if not ops:
        return None
    idx, inst = rng.choice(ops)
    q_orig = qc.find_bit(inst.qubits[0]).index
    q_new = (q_orig + 1) % qc.num_qubits
    out = qc.copy()
    new_data = list(out.data)
    new_inst = new_data[idx]
    new_data[idx] = new_inst.replace(qubits=(out.qubits[q_new],))
    out.data = new_data
    return out


def _mutant_gate_delete(qc: QuantumCircuit, rng: random.Random) -> Optional[QuantumCircuit]:
    """Delete a single non-measurement gate."""
    ops = [(i, inst) for i, inst in enumerate(qc.data)
           if inst.operation.name not in ("measure", "barrier")]
    if not ops:
        return None
    idx, _ = rng.choice(ops)
    out = qc.copy()
    out.data = [inst for i, inst in enumerate(qc.data) if i != idx]
    return out


def _mutant_gate_replace(qc: QuantumCircuit, rng: random.Random) -> Optional[QuantumCircuit]:
    """Replace a gate with a semantically different gate of the same arity."""
    ops = [(i, inst) for i, inst in enumerate(qc.data)
           if inst.operation.name in _REPLACEMENT_MAP]
    if not ops:
        return None
    idx, inst = rng.choice(ops)
    new_name = _REPLACEMENT_MAP[inst.operation.name]
    out = qc.copy()
    new_data = list(out.data)
    try:
        new_gate = getattr(__import__("qiskit.circuit.library", fromlist=[new_name.upper() + "Gate"]),
                           new_name.upper() + "Gate")()
        new_data[idx] = new_data[idx].replace(operation=new_gate)
    except Exception:
        return None
    out.data = new_data
    return out


def _mutant_phase_flip(qc: QuantumCircuit, rng: random.Random) -> Optional[QuantumCircuit]:
    """Negate a rotation-angle parameter."""
    ops = [(i, inst) for i, inst in enumerate(qc.data)
           if inst.operation.params and isinstance(inst.operation.params[0], (int, float))]
    if not ops:
        return None
    idx, inst = rng.choice(ops)
    out = qc.copy()
    new_data = list(out.data)
    old_op = new_data[idx].operation
    new_params = [-p if isinstance(p, (int, float)) else p for p in old_op.params]
    try:
        new_op = old_op.__class__(*new_params)
        new_data[idx] = new_data[idx].replace(operation=new_op)
    except Exception:
        return None
    out.data = new_data
    return out


def _mutant_measurement_map(qc: QuantumCircuit, rng: random.Random) -> Optional[QuantumCircuit]:
    """Swap the classical bit targets of two measurements."""
    meas = [(i, inst) for i, inst in enumerate(qc.data)
            if inst.operation.name == "measure"]
    if len(meas) < 2:
        return None
    (i1, m1), (i2, m2) = rng.sample(meas, 2)
    out = qc.copy()
    new_data = list(out.data)
    new_data[i1] = m1.replace(clbits=(m2.clbits[0],))
    new_data[i2] = m2.replace(clbits=(m1.clbits[0],))
    out.data = new_data
    return out


_OPERATORS = {
    "gate_swap": _mutant_gate_swap,
    "qubit_index": _mutant_qubit_index,
    "gate_delete": _mutant_gate_delete,
    "gate_replace": _mutant_gate_replace,
    "phase_flip": _mutant_phase_flip,
    "measurement_map": _mutant_measurement_map,
}


def generate_mutants(
    source_qcs: Dict[str, QuantumCircuit],
    n_total: int = 250,
    seed: int = MASTER_SEED,
    max_per_source: Optional[int] = None,
    min_tvd: float = 0.0,
    effect_shots: int = 8192,
) -> List[MutantRecord]:
    """Generate n_total mutants across all source circuits, deterministically."""
    rng = random.Random(seed)
    # Normalize to plain QuantumCircuit so .data setter works in mutation operators.
    sources = [(sid, _to_plain_qc(qc)) for sid, qc in source_qcs.items()]
    mutants: List[MutantRecord] = []
    per_source: Dict[str, int] = {}
    attempts = 0
    m_id = 0
    while len(mutants) < n_total and attempts < n_total * 20:
        attempts += 1
        src_id, qc = rng.choice(sources)
        if max_per_source is not None and per_source.get(src_id, 0) >= max_per_source:
            continue
        op_name = rng.choice(FAULT_OPS)
        fn = _OPERATORS[op_name]
        result = fn(qc, rng)
        if result is None:
            continue
        effect_tvd = None
        if min_tvd > 0.0:
            effect_tvd = estimate_effect_tvd(qc, result, shots=effect_shots, seed=seed + attempts)
            if effect_tvd is None or effect_tvd < min_tvd:
                continue
        m_id += 1
        mutants.append(MutantRecord(
            mutant_id=f"m{m_id:04d}",
            source_id=src_id,
            operator=op_name,
            site=f"{op_name}_attempt{attempts}",
            circuit=result,
            effect_tvd=effect_tvd,
        ))
        per_source[src_id] = per_source.get(src_id, 0) + 1
    return mutants[:n_total]
