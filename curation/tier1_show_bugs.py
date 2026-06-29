"""Dump the before->after diff + metadata for a filtered subset of Platforms candidates,
so the builder-contract in/out call and the ProgramSubject reconstruction can be made from
the ACTUAL code change (not the keyword prefilter, which is near-useless on this dataset).

Default selection = qiskit-terra bugs with a python before/after pair (the promising set).

Usage (pure stdlib):
  python curation/tier1_show_bugs.py --candidates curation/datasets/platforms_candidates.csv
  python curation/tier1_show_bugs.py --framework '' --kind '' --grep quantumcircuit   # widen
"""
from __future__ import annotations

import argparse
import csv
import difflib
from pathlib import Path


def _read(p: str):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        return [f"<<unreadable: {e}>>"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", default="curation/datasets/platforms_candidates.csv")
    ap.add_argument("--framework", default="qiskit-terra", help="exact match filter ('' = any)")
    ap.add_argument("--kind", default="python", help="pair_kind filter ('' = any)")
    ap.add_argument("--grep", default="", help="only rows whose buggy_path basename contains this")
    ap.add_argument("--max_diff", type=int, default=45, help="cap diff lines per bug")
    ap.add_argument("--max_comment", type=int, default=400)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.candidates, encoding="utf-8")))
    sel = [r for r in rows
           if (not args.framework or r.get("framework") == args.framework)
           and (not args.kind or r.get("pair_kind") == args.kind)
           and (not args.grep or args.grep in Path(r.get("buggy_path", "")).name)]

    print(f"showing {len(sel)} candidates (framework={args.framework!r} kind={args.kind!r} "
          f"grep={args.grep!r}) of {len(rows)} total\n")
    for i, r in enumerate(sel, 1):
        bp, fp = r.get("buggy_path", ""), r.get("fixed_path", "")
        print("=" * 78)
        print(f"[{i}/{len(sel)}] {r.get('id')}   commit {r.get('commit_hash','')[:10]}")
        print(f"  pattern : {r.get('bug_pattern')}")
        print(f"  comp/sym: {r.get('component')} / {r.get('symptom')}   type={r.get('bug_type')}")
        print(f"  file    : {Path(bp).name}   ({r.get('n_changed_files')} changed file(s))")
        print(f"  url     : {r.get('localization','')[:160]}")
        c = (r.get("description") or "").split("|")[0].strip()
        if c:
            print(f"  comment : {c[:args.max_comment]}")
        if bp and fp:
            diff = list(difflib.unified_diff(_read(bp), _read(fp), "before", "after", lineterm=""))
            shown = [ln for ln in diff if ln.startswith(("+", "-", "@@"))]  # changed lines + hunk headers
            print("  --- diff (changed lines only) ---")
            for ln in shown[:args.max_diff]:
                print("    " + ln)
            if len(shown) > args.max_diff:
                print(f"    ... (+{len(shown) - args.max_diff} more changed lines)")
        print()
    print("DONE -- paste back; in/out + reconstruction call is made from these diffs.")


if __name__ == "__main__":
    main()
