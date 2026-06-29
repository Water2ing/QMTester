"""Tier 1 extractor: Bugs in Quantum Computing Platforms (OOPSLA'22) -> candidates CSV.

Reads the real on-disk artifacts (verified 2026-06-28):
  * artifacts/annotation_bugs.csv  columns: id,real,type,repo,commit_hash,component,
    symptom,bug_pattern,comment,localization
  * artifacts/minimal_bugfixes/<framework>/<framework>#<N>/ with: <commit_hash>.txt,
    before/<changed files>, after/<changed files>, metadata.json, bug_*_comment.md

Joins each annotation row to its bugfix folder by commit_hash, and records the before/after
file pair for human diff inspection. Emits the columns tier1_screen.py expects
(id,title,description,buggy_path,fixed_path) + provenance.

IMPORTANT: before/after are PATCHES to library source (often C++ .hpp for qiskit-aer, or
non-circuit .py), NOT standalone runnable circuit scripts -- so do NOT use --run_pairs here.
This dataset is a curated REAL-BUG source: the builder-contract ones (almost all in
qiskit-terra, circuit construction) become RECONSTRUCTED ProgramSubjects (same way the
Bugs4Q subjects were built). The `pair_kind` column flags python-vs-native so the audit can
prioritise: qiskit-terra + python pair = most promising; qiskit-aer C++ = out (simulator
internals, not a Qiskit builder contract).

Usage (pure stdlib):
  python curation/tier1_extract_platforms.py \
      --platforms_dir curation/datasets/platforms_oopsla22 \
      --out curation/datasets/platforms_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

_HEX = re.compile(r"^[0-9a-f]{7,40}$")


def _commit_keys(bugdir: Path):
    """Possible commit hashes for a bug folder: the <hash>.txt stem and metadata.json fields."""
    keys = set()
    for p in bugdir.glob("*.txt"):
        if _HEX.match(p.stem):
            keys.add(p.stem)
    meta = bugdir / "metadata.json"
    if meta.is_file():
        try:
            d = json.loads(meta.read_text(encoding="utf-8"))
            for k, v in (d.items() if isinstance(d, dict) else []):
                if isinstance(v, str) and _HEX.match(v.strip()):
                    keys.add(v.strip())
        except Exception:
            pass
    return keys


def _index_bugfixes(mbf_dir: Path):
    """commit_hash -> bug folder (full and 7-char prefixes both indexed for loose matching)."""
    idx = {}
    if not mbf_dir.is_dir():
        return idx
    for fw in sorted(p for p in mbf_dir.iterdir() if p.is_dir()):
        for bug in sorted(p for p in fw.iterdir() if p.is_dir()):
            for key in _commit_keys(bug):
                idx[key] = bug
                idx[key[:7]] = bug
    return idx


def _pick_pair(bugdir: Path):
    """Return (buggy_path, fixed_path, kind, n_files). Prefer a .py file common to before/after."""
    before, after = bugdir / "before", bugdir / "after"
    if not (before.is_dir() and after.is_dir()):
        return "", "", "missing", 0
    bset = {p.name: p for p in before.rglob("*") if p.is_file()}
    aset = {p.name: p for p in after.rglob("*") if p.is_file()}
    common = sorted(set(bset) & set(aset))
    if not common:
        return "", "", "no_common_file", 0
    py = [n for n in common if n.endswith(".py")]
    chosen = py[0] if py else common[0]
    ext = Path(chosen).suffix.lower()
    kind = "python" if ext == ".py" else ("native" if ext in (".hpp", ".cpp", ".cc", ".h", ".cs") else "other")
    return str(bset[chosen]), str(aset[chosen]), kind, len(common)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--platforms_dir", default="curation/datasets/platforms_oopsla22")
    ap.add_argument("--out", default="curation/datasets/platforms_candidates.csv")
    ap.add_argument("--repo_prefix", default="Qiskit/",
                    help="only keep annotation rows whose repo starts with this (set '' for all platforms)")
    args = ap.parse_args()

    art = Path(args.platforms_dir) / "artifacts"
    csv_path = art / "annotation_bugs.csv"
    if not csv_path.is_file():
        raise SystemExit(f"not found: {csv_path} (re-upload the MattePalte clone)")

    idx = _index_bugfixes(art / "minimal_bugfixes")
    rows_in = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    out_rows, no_folder = [], 0
    for r in rows_in:
        repo = (r.get("repo") or "").strip()
        if args.repo_prefix and not repo.startswith(args.repo_prefix):
            continue
        framework = repo.split("/")[-1] if "/" in repo else repo
        commit = (r.get("commit_hash") or "").strip()
        bugdir = idx.get(commit) or idx.get(commit[:7]) if commit else None
        if bugdir is None:
            no_folder += 1
            buggy = fixed = ""
            kind, nfiles = "no_folder", 0
        else:
            buggy, fixed, kind, nfiles = _pick_pair(bugdir)
        comp = (r.get("component") or "").strip()
        symp = (r.get("symptom") or "").strip()
        patt = (r.get("bug_pattern") or "").strip()
        out_rows.append({
            "id": f"platforms_{framework}_{r.get('id','')}",
            "title": f"{comp} / {symp}" if comp or symp else patt,
            "description": f"{r.get('comment','')} | pattern={patt} component={comp} symptom={symp} type={r.get('type','')}",
            "buggy_path": buggy,
            "fixed_path": fixed,
            "repo": repo,
            "framework": framework,
            "commit_hash": commit,
            "bug_type": (r.get("type") or "").strip(),
            "component": comp,
            "symptom": symp,
            "bug_pattern": patt,
            "pair_kind": kind,
            "n_changed_files": nfiles,
            "localization": (r.get("localization") or "").strip(),
        })

    if not out_rows:
        raise SystemExit(f"no rows matched repo_prefix={args.repo_prefix!r}; check the CSV 'repo' column.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys())); w.writeheader(); w.writerows(out_rows)

    print(f"wrote {len(out_rows)} candidates -> {out}  (repo_prefix={args.repo_prefix!r})")
    print("by framework:", dict(Counter(r["framework"] for r in out_rows)))
    print("by pair_kind:", dict(Counter(r["pair_kind"] for r in out_rows)))
    print("by bug_type :", dict(Counter(r["bug_type"] for r in out_rows)))
    print("top bug_pattern:", dict(Counter(r["bug_pattern"] for r in out_rows).most_common(12)))
    print(f"unmatched to a bugfix folder: {no_folder}")
    terra_py = [r for r in out_rows if r["framework"] == "qiskit-terra" and r["pair_kind"] == "python"]
    print(f"\n** qiskit-terra with a python before/after pair (most promising): {len(terra_py)} **")
    for r in terra_py[:20]:
        print(f"   {r['commit_hash'][:8]}  {r['bug_pattern']:<32} {Path(r['buggy_path']).name}")
    print("\nNEXT: python curation/tier1_screen.py --candidates", out,
          "--out curation/triage/platforms_triage.csv     (NO --run_pairs: before/after are library patches)")


if __name__ == "__main__":
    main()
