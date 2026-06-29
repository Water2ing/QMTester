"""Stack Exchange miner for Qiskit builder-contract defects.

Searches Stack Overflow and Quantum Computing SE (tagged [qiskit]) for user-program
builder bugs: a question reporting wrong measurement results plus an accepted answer
that supplies the fix forms a buggy/fixed pair. Queries cover the five defect families'
bug signatures and require an accepted answer. Output is a triage list (a human confirms
each is a genuine builder-contract defect and reconstructs it as a QMTester subject).
api.stackexchange.com needs no key for low volume.

Usage:
  python scripts/mine_stackexchange_defects.py --out data/mining/se_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

QUERIES = {
    # cast a WIDE net at the two families that still have no/few real subjects
    "parameter_periodicity": [
        "rz period", "rotation period wrong", "2 pi rotation identity", "controlled rotation period",
        "crz wrong phase", "rx 2pi", "u1 period", "phase kickback wrong", "rzz period",
        "parametrized rotation wrong result", "global phase observable controlled",
    ],
    "ancilla_uncompute": [
        "ancilla uncompute", "ancilla not reset", "garbage qubit entangled", "mcx ancilla wrong",
        "auxiliary qubit wrong result", "ancilla measurement entangled", "reset qubit wrong",
        "scratch qubit wrong", "uncompute wrong result",
    ],
    "qft_round_trip": ["qft wrong", "inverse qft", "qft swap order"],
    "input_permutation": ["wrong qubit order", "ccx wrong", "control target swapped"],
    "classical_remap": ["measurement reversed", "endianness", "measurement order wrong"],
    "register_shape": ["measure_all bits"],
    "general_builder": ["wrong measurement result", "unexpected counts circuit", "incorrect probabilities qiskit"],
}
SITES = ["quantumcomputing", "stackoverflow"]


def se_search(q, site, since=1640995200):  # since ~2022-01-01
    params = {"order": "desc", "sort": "relevance", "q": q, "tagged": "qiskit",
              "accepted": "True", "site": site, "filter": "!nNPvSNVZJS", "pagesize": 12}
    url = "https://api.stackexchange.com/2.3/search/advanced?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "qmtester-miner"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/mining/se_candidates.csv")
    ap.add_argument("--since_year", type=int, default=2022)
    ap.add_argument("--spacing", type=float, default=1.5)
    args = ap.parse_args()

    out = Path(args.root) / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = {}
    quota = None
    for family, queries in QUERIES.items():
        for q in queries:
            for site in SITES:
                try:
                    data = se_search(q, site)
                except Exception as e:
                    print(f"[{family}/{site}] failed: {type(e).__name__}", flush=True)
                    time.sleep(3); continue
                quota = data.get("quota_remaining", quota)
                items = data.get("items", [])
                kept = 0
                for it in items:
                    year = time.gmtime(it.get("creation_date", 0)).tm_year
                    if year < args.since_year:
                        continue
                    link = it.get("link", "")
                    if link in seen:
                        seen[link]["families"].add(family); continue
                    seen[link] = {
                        "link": link, "site": site, "year": year,
                        "title": (it.get("title") or "")[:140],
                        "score": it.get("score", 0), "answers": it.get("answer_count", 0),
                        "is_answered": it.get("is_answered", False),
                        "families": {family},
                    }
                    kept += 1
                print(f"[{family}/{site}] '{q[:35]}' -> {len(items)} hits, {kept} kept (quota {quota})", flush=True)
                time.sleep(args.spacing)

    rows = list(seen.values())
    def rank(r):
        return (len(r["families"]) * 2 + min(r["score"], 10) * 0.3 + (r["year"] - 2022)
                + (2 if r["site"] == "quantumcomputing" else 0))
    rows.sort(key=rank, reverse=True)
    for r in rows:
        r["families"] = ",".join(sorted(r["families"]))

    with out.open("w", newline="", encoding="utf-8") as f:
        cols = ["link", "site", "year", "title", "score", "answers", "is_answered", "families"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    print("\n" + "=" * 80)
    print(f"{len(rows)} unique SE candidates -> {out}")
    print("=" * 80)
    for r in rows[:25]:
        print(f"[{r['families']:22}] {r['year']} {r['site'][:14]:14} s={r['score']:>3} {r['title'][:55]}")
        print(f"    {r['link']}")


if __name__ == "__main__":
    main()
