"""Stage 5: output canonicalization.

We rewrite follow-up count-vector keys into source bit order before statistical
comparison. Swap-based rewrites shift which physical qubit writes which clbit;
the ``canon_map`` from the relation family records the inverse permutation.

Canonicalization is also where non-bijective or structure-changing transformations
are caught late: if the follow-up count vector keys have a different support size
or key length than the source, the pair is rejected as a coverage loss.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple


Counts = Dict[str, int]


def _flatten(key: str) -> str:
    """Remove spaces from multi-register Qiskit bitstring keys (e.g. '01 00' -> '0100')."""
    return key.replace(" ", "")


def _flatten_counts(counts: Counts) -> Counts:
    """Flatten all keys in a counts dict; merge counts if flattening creates duplicates."""
    out: Counts = {}
    for k, v in counts.items():
        flat = _flatten(k)
        out[flat] = out.get(flat, 0) + v
    return out


def _validate_key_length(source_counts: Counts, followup_counts: Counts) -> Tuple[bool, str]:
    src_lens = {len(k) for k in source_counts}
    fu_lens = {len(k) for k in followup_counts}
    if len(src_lens) > 1:
        return False, f"CANON:source_key_length_not_uniform lengths={sorted(src_lens)}"
    if len(fu_lens) > 1:
        return False, f"CANON:followup_key_length_not_uniform lengths={sorted(fu_lens)}"
    src_len = next(iter(src_lens), 0)
    fu_len = next(iter(fu_lens), 0)
    if src_len != fu_len:
        return False, f"CANON:key_length_mismatch src={src_len} fu={fu_len}"
    return True, "OK"


def _validate_canon_map(canon_map: List[int], n: int) -> Tuple[bool, str]:
    """Validate a follow-up clbit -> source clbit map for an n-bit count key."""
    if len(canon_map) != n:
        return False, f"CANON:map_length_mismatch map={len(canon_map)} bits={n}"
    if any(not isinstance(i, int) for i in canon_map):
        return False, "CANON:map_contains_non_integer_index"
    if any(i < 0 or i >= n for i in canon_map):
        return False, f"CANON:map_index_out_of_range map={canon_map} bits={n}"
    if len(set(canon_map)) != n:
        return False, f"CANON:non_bijective_map map={canon_map}"
    return True, "OK"


def canonicalize(
    source_counts: Counts,
    followup_counts: Counts,
    canon_map: Optional[List[int]],
) -> Tuple[bool, str, Counts, Counts]:
    """Align follow-up counts to source bit order.

    Parameters
    ----------
    source_counts:  raw counts dict from source execution (clbit order = Qiskit default).
    followup_counts: raw counts dict from follow-up execution.
    canon_map:      ``canon_map[i]`` = source clbit index that follow-up clbit i maps to.
                    ``None`` means the identity map (no remap needed).

    Returns
    -------
    (ok, reason, aligned_source, aligned_followup)
    aligned_source and aligned_followup have the same key set.
    """
    # Flatten multi-register keys ("01 00" -> "0100") before any processing.
    source_counts = _flatten_counts(source_counts)
    followup_counts = _flatten_counts(followup_counts)

    ok, reason = _validate_key_length(source_counts, followup_counts)
    if not ok:
        return False, reason, {}, {}

    if canon_map is None:
        # Identity: just align support.
        src, fu = _align_support(source_counts, followup_counts)
        return True, "OK", src, fu

    n = len(next(iter(source_counts), ""))  # length after flattening
    if n == 0:
        return True, "OK", {}, {}

    ok, reason = _validate_canon_map(canon_map, n)
    if not ok:
        return False, reason, {}, {}

    # Apply inverse permutation: follow-up bitstring b -> source bitstring b'.
    # Qiskit bitstrings are right-to-left: b[0] is MSB, b[-1] is clbit 0.
    # canon_map[i] = source clbit index for follow-up clbit i.
    def remap(bitstring: str) -> str:
        # bitstring[n-1-i] = value of clbit i (right-to-left encoding)
        fu_bits = [int(bitstring[n - 1 - i]) for i in range(n)]
        src_bits = [0] * n
        for fu_i, src_i in enumerate(canon_map):
            src_bits[src_i] = fu_bits[fu_i]
        return "".join(str(b) for b in reversed(src_bits))

    remapped: Counts = {}
    for key, cnt in followup_counts.items():
        new_key = remap(key)
        if len(new_key) != n:
            return False, "CANON:remap_produced_wrong_length", {}, {}
        remapped[new_key] = remapped.get(new_key, 0) + cnt

    src, fu = _align_support(source_counts, remapped)
    return True, "OK", src, fu


def _align_support(a: Counts, b: Counts) -> Tuple[Counts, Counts]:
    """Pad both dicts to the union of their keys (unseen keys get count 0)."""
    all_keys = set(a) | set(b)
    return (
        {k: a.get(k, 0) for k in sorted(all_keys)},
        {k: b.get(k, 0) for k in sorted(all_keys)},
    )
