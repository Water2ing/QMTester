"""Swap-based rewriting (Table II, row 2).

Permute logical qubits and restore the original output order via canonicalization.
The follow-up relabels every gate's qubit args by a permutation pi; the terminal
measurement still writes qubit i -> clbit i, so follow-up clbit positions are a
permutation of the source ones. ``canon_map`` records the inverse permutation that
restores the source bit order.
"""
from __future__ import annotations

from typing import List, Tuple

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister

from ..circuit_io import NormalizedCircuit
from .base import Candidate, RelationFamily, register


def _random_permutations(n: int, rng, count: int) -> List[List[int]]:
    perms = []
    # all adjacent transpositions (structured, cheap; covers every qubit pair boundary) ...
    for i in range(n - 1):
        p = list(range(n))
        p[i], p[i + 1] = p[i + 1], p[i]
        perms.append(p)
    # ... plus several seeded full permutations for broader coverage.
    for _ in range(8):
        p = list(range(n))
        rng.shuffle(p)
        if p != list(range(n)):
            perms.append(p)
    # de-duplicate
    uniq = []
    for p in perms:
        if p not in uniq:
            uniq.append(p)
    return uniq[:count]


@register
class SwapRewriting(RelationFamily):
    name = "swap"

    def enumerate(self, norm: NormalizedCircuit, rng) -> List[Candidate]:
        n = norm.num_qubits
        cands: List[Candidate] = []
        if n < 2:
            return cands
        for perm in _random_permutations(n, rng, count=16):
            # canon_map for clbits: follow-up writes qubit q -> clbit q, but logical
            # qubit q now lives at physical position perm[q]. Restoring requires mapping
            # follow-up clbit position perm[q] back to source clbit position meas_map[q].
            cands.append(Candidate(
                family=self.name,
                name="perm[" + ",".join(map(str, perm)) + "]",
                params={"perm": perm},
                canon_map=None,  # computed in apply once meas layout is known
            ))
        return cands

    def admissible(self, norm: NormalizedCircuit, cand: Candidate) -> Tuple[bool, str]:
        # Precondition: bijective logical->physical permutation; output bits restorable.
        perm = cand.params["perm"]
        if sorted(perm) != list(range(norm.num_qubits)):
            return False, "INV:non_bijective_permutation"
        if norm.has_conditional:
            return False, "INV:untracked_classical_side_effect"
        if norm.has_midcircuit_measure:
            return False, "INV:midcircuit_measure_breaks_relabel"
        if norm.has_nonterminal_measure:
            return False, "INV:nonterminal_measure_breaks_relabel"
        if norm.has_reset:
            return False, "INV:reset_boundary_breaks_relabel"
        if norm.has_delay:
            return False, "INV:timing_delay_boundary_breaks_relabel"
        if norm.has_custom_opaque:
            return False, "INV:opaque_operation_boundary"
        if not norm.meas_map:
            return False, "INV:no_terminal_measurement_to_restore"
        if len(set(norm.meas_map.values())) != len(norm.meas_map):
            return False, "INV:non_bijective_classical_measure_map"
        return True, "OK"

    def apply(self, norm: NormalizedCircuit, cand: Candidate) -> QuantumCircuit:
        perm = cand.params["perm"]
        src = norm.qc
        # Build a fresh circuit with identically-sized registers.
        qregs = [QuantumRegister(r.size, r.name) for r in src.qregs]
        cregs = [ClassicalRegister(r.size, r.name) for r in src.cregs]
        out = QuantumCircuit(*qregs, *cregs)

        def map_qubit(idx: int) -> int:
            return perm[idx]

        # Relabel GATE qubits through perm; measurement qubits are kept unchanged.
        # This means: after relabeling, physical qubit i in the follow-up holds the
        # content that logical qubit inv_perm[i] would produce in the source.
        # Terminal measurements still read physical qubit i → clbit meas_map[i],
        # so follow-up clbit c = meas_map[i] has logical value of qubit inv_perm[i].
        # canon_map restores source order: follow-up clbit c → source clbit meas_map[inv_perm[i]].
        for inst in src.data:
            qidx = [src.find_bit(q).index for q in inst.qubits]
            cidx = [src.find_bit(c).index for c in inst.clbits]
            if inst.operation.name in ("measure", "barrier"):
                # Keep measurements in original order so canon_map can restore source order.
                new_q = [out.qubits[i] for i in qidx]
            else:
                new_q = [out.qubits[map_qubit(i)] for i in qidx]
            new_c = [out.clbits[i] for i in cidx]
            out.append(inst.operation, new_q, new_c)

        # Compute canon_map: follow-up clbit c → source clbit.
        # follow-up clbit c = meas_map[i] measures physical qubit i which holds
        # logical qubit inv_perm[i]. Source clbit for logical qubit inv_perm[i]
        # is meas_map[inv_perm[i]].
        ncl = norm.num_clbits
        canon = list(range(ncl))
        inv = [0] * norm.num_qubits
        for i, p in enumerate(perm):
            inv[p] = i
        for phys_q, clbit_c in norm.meas_map.items():
            # follow-up clbit clbit_c holds logical qubit inv_perm[phys_q]
            logical_q = inv[phys_q]
            src_clbit = norm.meas_map.get(logical_q, clbit_c)
            canon[clbit_c] = src_clbit
        cand.canon_map = canon
        return out
