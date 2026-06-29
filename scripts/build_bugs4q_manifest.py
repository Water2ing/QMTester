"""Build the frozen Bugs4Q manifest from vendor/bugs4q/README.md.

The manifest is generated once on the login node and read by all Slurm shards.
No experiment shard should probe the whole benchmark or rewrite exclusions.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional


BUG_LINK_RE = re.compile(r"\[Buggy\]\((?P<path>[^)]+)\)")
FIX_LINK_RE = re.compile(r"\[Fixed\]\((?P<path>[^)]+)\)")


def _clean_link(link: str) -> str:
    link = link.strip()
    if link.startswith("./"):
        link = link[2:]
    return link.lstrip("/")


def _resolve_path(root: Path, link: str, candidates: Iterable[str]) -> Optional[Path]:
    rel = Path(_clean_link(link))
    direct = root / rel
    if direct.is_file():
        return direct
    if direct.is_dir():
        for name in candidates:
            p = direct / name
            if p.is_file():
                return p
    return None


def _section_name(line: str, current: str) -> str:
    if line.strip().startswith("## Q#"):
        return "qsharp"
    text = line.strip("# ").strip().lower()
    if "qiskit reproduceable bugs from github" in text:
        return "qiskit_github"
    if "qiskit reproduceable bugs from stackflow" in text:
        return "qiskit_stackoverflow"
    if "qiskit reproduceable bugs from stackexchange" in text:
        return "qiskit_stackexchange"
    if text == "cirq":
        return "cirq"
    return current


def _parse_readme(readme: Path) -> list[dict]:
    rows: list[dict] = []
    current_section = "unknown"
    for raw in readme.read_text(errors="replace").splitlines():
        if raw.startswith("#"):
            current_section = _section_name(raw, current_section)
        if "|" not in raw or "[Buggy]" not in raw:
            continue
        cols = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cols) < 4:
            continue
        bug_match = BUG_LINK_RE.search(raw)
        fix_match = FIX_LINK_RE.search(raw)
        if not bug_match:
            continue
        if current_section in {"qiskit_github", "qiskit_stackexchange"}:
            type_col = cols[7] if len(cols) > 7 else ""
        else:
            type_col = cols[6] if len(cols) > 6 else ""
        bug_id = re.sub(r"\[|\].*", "", cols[0]).strip() or f"row{len(rows) + 1}"
        rows.append({
            "section": current_section,
            "readme_bug_id": bug_id,
            "buggy_link": bug_match.group("path"),
            "fixed_link": fix_match.group("path") if fix_match else "",
            "category": type_col,
        })
    return rows


def build_manifest(root: Path, out_path: Path, excluded_path: Path) -> int:
    sys.path.insert(0, str(root / "artifact"))
    from qmtester.subject_adapter import probe_subject

    bugs4q_root = root / "vendor" / "bugs4q"
    readme = bugs4q_root / "README.md"
    rows = _parse_readme(readme)
    manifest_rows = []
    excluded_rows = []

    for row in rows:
        subject_id = f"{row['section']}_{row['readme_bug_id']}"
        buggy_path = _resolve_path(bugs4q_root, row["buggy_link"], ["buggy.py", "bug_version.py"])
        fixed_path = _resolve_path(bugs4q_root, row["fixed_link"], ["fixed.py", "Fixed.py", "fix.py", "Fix.py", "fixed_version.py"])

        runnable = False
        exclusion_reason = ""
        adapter = "qiskit_script"
        relation_scope = "circuit"

        if row["section"] in {"qsharp", "cirq"}:
            exclusion_reason = f"NON_QISKIT:{row['section']}"
            adapter = "unsupported"
        elif buggy_path is None:
            exclusion_reason = "MISSING_BUGGY_PATH"
            adapter = "missing"
        else:
            qc, reason = probe_subject(buggy_path)
            runnable = qc is not None
            if not runnable:
                exclusion_reason = reason
            elif fixed_path is None:
                exclusion_reason = "OK:fixed_path_missing"

        manifest_row = {
            "subject_id": subject_id,
            "readme_bug_id": row["readme_bug_id"],
            "section": row["section"],
            "buggy_path": str(buggy_path.relative_to(bugs4q_root)) if buggy_path else _clean_link(row["buggy_link"]),
            "fixed_path": str(fixed_path.relative_to(bugs4q_root)) if fixed_path else _clean_link(row["fixed_link"]),
            "category": row["category"],
            "runnable": "true" if runnable else "false",
            "adapter": adapter,
            "relation_scope": relation_scope,
            "exclusion_reason": exclusion_reason,
        }
        manifest_rows.append(manifest_row)
        if not runnable:
            excluded_rows.append({
                "subject_id": subject_id,
                "path": manifest_row["buggy_path"],
                "reason": exclusion_reason,
            })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "subject_id", "readme_bug_id", "section", "buggy_path", "fixed_path",
        "category", "runnable", "adapter", "relation_scope", "exclusion_reason",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    excluded_path.parent.mkdir(parents=True, exist_ok=True)
    with excluded_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["subject_id", "path", "reason"])
        writer.writeheader()
        writer.writerows(excluded_rows)

    runnable_count = sum(1 for r in manifest_rows if r["runnable"] == "true")
    print(f"Wrote {len(manifest_rows)} Bugs4Q manifest rows ({runnable_count} runnable) -> {out_path}")
    print(f"Wrote {len(excluded_rows)} exclusions -> {excluded_path}")
    return runnable_count


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--out", default="data/manifests/bugs4q_manifest.csv")
    p.add_argument("--excluded", default="data/manifests/excluded.csv")
    args = p.parse_args()
    root = Path(args.root).resolve()
    build_manifest(root, root / args.out, root / args.excluded)


if __name__ == "__main__":
    main()
