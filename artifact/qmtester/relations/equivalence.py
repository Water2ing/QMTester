"""Circuit-equivalence rewriting (Table II, row 4).

Replace a subcircuit with an algebraically equivalent decomposition over the same
ordered qubits and parameter domains. Examples: H = Rz(pi/2)·Rx(pi/2)·Rz(pi/2),
CNOT = H·CZ·H (on target), X = H·Z·H, etc.

Preconditions (admissibility):
  - Replacement subcircuit is algebraically equivalent over the parameter domain.
  - Same ordered qubits and gate domains; no approximation error outside valid bounds.
  - Source/replacement decompositions implement the same observable transformation.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from qiskit import QuantumCircuit

from ..circuit_io import NormalizedCircuit
from .base import Candidate, RelationFamily, register


# Equivalence rules: (name, match_gate_name, builder(qc, qubits))
# Each builder appends an equivalent decomposition to qc on given qubit indices.
def _rule_h_as_rz_sx_rz(qc, qubits):
    q = qubits[0]
    qc.rz(math.pi / 2, q)
    qc.sx(q)
    qc.rz(math.pi / 2, q)

def _rule_x_as_h_z_h(qc, qubits):
    q = qubits[0]
    qc.h(q)
    qc.z(q)
    qc.h(q)

def _rule_z_as_h_x_h(qc, qubits):
    q = qubits[0]
    qc.h(q)
    qc.x(q)
    qc.h(q)

def _rule_cx_as_h_cz_h(qc, qubits):
    ctrl, tgt = qubits
    qc.h(tgt)
    qc.cz(ctrl, tgt)
    qc.h(tgt)

def _rule_s_as_rz(qc, qubits):
    q = qubits[0]
    qc.rz(math.pi / 2, q)

def _rule_t_as_rz(qc, qubits):
    q = qubits[0]
    qc.rz(math.pi / 4, q)

def _rule_sdg_as_rz(qc, qubits):
    q = qubits[0]
    qc.rz(-math.pi / 2, q)

def _rule_tdg_as_rz(qc, qubits):
    q = qubits[0]
    qc.rz(-math.pi / 4, q)

_RULES = {
    "h":   ("eq_h_as_rz_sx_rz",  1, _rule_h_as_rz_sx_rz),
    "x":   ("eq_x_as_h_z_h",     1, _rule_x_as_h_z_h),
    "z":   ("eq_z_as_h_x_h",     1, _rule_z_as_h_x_h),
    "cx":  ("eq_cx_as_h_cz_h",   2, _rule_cx_as_h_cz_h),
    "s":   ("eq_s_as_rz_pi_2",   1, _rule_s_as_rz),
    "t":   ("eq_t_as_rz_pi_4",   1, _rule_t_as_rz),
    "sdg": ("eq_sdg_as_rz",      1, _rule_sdg_as_rz),
    "tdg": ("eq_tdg_as_rz",      1, _rule_tdg_as_rz),
}


@register
class EquivalenceRewriting(RelationFamily):
    name = "equivalence"

    def enumerate(self, norm: NormalizedCircuit, rng) -> List[Candidate]:
        """One candidate per (applicable rule, first-occurrence site)."""
        cands: List[Candidate] = []
        seen = set()
        for i, inst in enumerate(norm.qc.data):
            gate_name = inst.operation.name
            if gate_name not in _RULES:
                continue
            rule_name, arity, _ = _RULES[gate_name]
            qidx = tuple(norm.qc.find_bit(q).index for q in inst.qubits)
            key = (rule_name, qidx)
            if key in seen:
                continue
            seen.add(key)
            cands.append(Candidate(
                family=self.name,
                name=f"{rule_name}@inst{i}_q{qidx}",
                params={
                    "gate_name": gate_name,
                    "rule_name": rule_name,
                    "arity": arity,
                    "qubits": list(qidx),
                    "inst_idx": i,
                },
                canon_map=None,
            ))
        return cands

    def admissible(self, norm: NormalizedCircuit, cand: Candidate) -> Tuple[bool, str]:
        gate_name = cand.params["gate_name"]
        arity = cand.params["arity"]
        qidx = cand.params["qubits"]
        if norm.has_conditional:
            return False, "EQ:conditional_op_not_preserved_by_decomposition"
        # Check qubit order and arity match the rule.
        if len(qidx) != arity:
            return False, "EQ:qubit_arity_mismatch"
        if any(q >= norm.num_qubits for q in qidx):
            return False, "EQ:qubit_index_out_of_range"
        # Check same ordered qubits and gate domain.
        if gate_name not in _RULES:
            return False, "EQ:no_rule_for_gate"
        # Parameterized gates need parameter domain check — we only rewrite unparameterized.
        if norm.qc.data[cand.params["inst_idx"]].operation.params:
            return False, "EQ:parameterized_gate_outside_current_domain"
        return True, "OK"

    def apply(self, norm: NormalizedCircuit, cand: Candidate) -> QuantumCircuit:
        gate_name = cand.params["gate_name"]
        qidx = cand.params["qubits"]
        inst_idx = cand.params["inst_idx"]
        _, _, builder = _RULES[gate_name]

        src = norm.qc
        out = QuantumCircuit(*src.qregs, *src.cregs)
        for i, inst in enumerate(src.data):
            if i == inst_idx:
                builder(out, [out.qubits[q] for q in qidx])
            else:
                out.append(inst.operation, inst.qubits, inst.clbits)
        return out
