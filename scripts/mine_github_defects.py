"""First-pass GitHub miner for recent Qiskit builder-contract defects.

Searches GitHub issues/PRs across the Qiskit ecosystem for the five relation families'
bug signatures, scoped to recent activity (Qiskit 1.x/2.x era). Output is a TRIAGE list:
candidates a human must confirm are genuine builder-contract defects with a real fix. The
goal is to grow the real-defect base past n=7, and especially to find a real
parameter_periodicity defect (the family with no real subject).

Unauthenticated GitHub search is rate-limited (10 req/min); we space queries by 7s.
Set GITHUB_TOKEN in the environment for higher limits and code/commit search.

Usage:
  python scripts/mine_github_defects.py --out data/mining/github_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

# family -> list of search queries (issue/PR text). Scoped to qiskit + the bug signature.
QUERIES = {
    "parameter_periodicity": [
        "qiskit rotation period wrong",
        "qiskit rz phase incorrect",
    ],
    "qft_round_trip": [
        "qiskit qft wrong",
        "qiskit inverse qft incorrect",
    ],
    "input_permutation": [
        "qiskit wrong qubit order",
        "qiskit ccx wrong",
    ],
    "classical_remap": [
        "qiskit measurement reversed",
        "qiskit endianness wrong",
    ],
    "ancilla_uncompute": [
        "qiskit ancilla uncompute",
        "qiskit ancilla wrong result",
    ],
    "register_shape": [
        "qiskit measure_all wrong",
    ],
    "general_builder": [
        "qiskit incorrect measurement result",
        "qiskit unexpected output circuit",
    ],
}


def gh_search(query, token=None, kind="issues"):
    url = f"https://api.github.com/search/{kind}?" + urllib.parse.urlencode(
        {"q": query, "sort": "updated", "order": "desc", "per_page": 15})
    headers = {"User-Agent": "qmtester-miner", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        remaining = r.headers.get("X-RateLimit-Remaining")
        return json.loads(r.read()), remaining


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/mining/github_candidates.csv")
    ap.add_argument("--since_year", type=int, default=2023)
    ap.add_argument("--spacing", type=float, default=7.0)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    out = Path(args.root) / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    seen = {}
    nq = 0
    for family, queries in QUERIES.items():
        for q in queries:
            nq += 1
            try:
                data, remaining = gh_search(q, token)
            except Exception as e:
                print(f"[{family}] query failed ({type(e).__name__}: {str(e)[:60]}); backing off", flush=True)
                time.sleep(max(args.spacing, 15))
                continue
            items = data.get("items", [])
            kept = 0
            for it in items:
                url = it.get("html_url", "")
                year = (it.get("created_at") or "0000")[:4]
                if int(year) < args.since_year:
                    continue
                if url in seen:
                    seen[url]["families"].add(family)
                    continue
                repo = "/".join(url.split("/")[3:5]) if url else "?"
                seen[url] = {
                    "url": url, "repo": repo, "title": (it.get("title") or "")[:140],
                    "state": it.get("state", ""), "created": year,
                    "is_pr": "pull" in url, "comments": it.get("comments", 0),
                    "families": {family},
                    "body_snippet": (it.get("body") or "").replace("\n", " ")[:200],
                }
                kept += 1
            print(f"[{family}] '{q[:45]}...' -> {len(items)} hits, {kept} kept (rate left: {remaining})", flush=True)
            time.sleep(args.spacing)

    rows = list(seen.values())
    # rank: qiskit-relevant repo, recent, has discussion
    def score(r):
        s = 0
        if "qiskit" in r["repo"].lower(): s += 2
        s += int(r["created"]) - 2023
        s += min(r["comments"], 5) * 0.3
        s += len(r["families"]) * 1.5
        return s
    rows.sort(key=score, reverse=True)
    for r in rows:
        r["families"] = ",".join(sorted(r["families"]))

    with out.open("w", newline="", encoding="utf-8") as f:
        cols = ["url", "repo", "title", "state", "created", "is_pr", "comments", "families", "body_snippet"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    print("\n" + "=" * 80)
    print(f"{len(rows)} unique candidates from {nq} queries -> {out}")
    print("=" * 80)
    for r in rows[:25]:
        print(f"[{r['families']:22}] {r['created']} {r['repo'][:30]:30} {r['title'][:60]}")
        print(f"    {r['url']}")


if __name__ == "__main__":
    main()
