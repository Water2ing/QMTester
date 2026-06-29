"""Tier 2 (b) - pre-registered, EXHAUSTIVE Stack Exchange / Stack Overflow mining.

Pulls qiskit-tagged questions that have an ACCEPTED answer (a fix exists), over a frozen
window, paging through the whole population (no sampling). Emits a candidates CSV for
curation/tier1_screen.py. Uses the public Stack Exchange API (no key needed for low volume;
set SE_KEY env var to raise the quota).

Usage:
  python curation/tier2_mine_stackexchange.py --site stackoverflow --from 2019-01-01 \
      --to 2025-01-01 --out curation/datasets/se_candidates.csv
"""
from __future__ import annotations

import argparse
import csv
import html
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


def _epoch(d):
    return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def main():
    import requests
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="stackoverflow", help="stackoverflow or quantumcomputing")
    ap.add_argument("--tag", default="qiskit")
    ap.add_argument("--from", dest="frm", default="2019-01-01")
    ap.add_argument("--to", dest="to", default="2025-01-01")
    ap.add_argument("--out", default="curation/datasets/se_candidates.csv")
    ap.add_argument("--max_pages", type=int, default=200)
    args = ap.parse_args()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    base = "https://api.stackexchange.com/2.3/search/advanced"
    params = {"site": args.site, "tagged": args.tag, "accepted": "True",
              "fromdate": _epoch(args.frm), "todate": _epoch(args.to),
              "sort": "creation", "order": "asc", "pagesize": 100, "filter": "withbody"}
    if os.environ.get("SE_KEY"):
        params["key"] = os.environ["SE_KEY"]

    rows, page = [], 1
    while page <= args.max_pages:
        params["page"] = page
        r = requests.get(base, params=params, timeout=30).json()
        for it in r.get("items", []):
            body = re.sub("<[^>]+>", " ", html.unescape(it.get("body", "")))[:400].replace("\n", " ")
            rows.append({"id": f"se_{args.site}_{it['question_id']}", "source": f"se:{args.site}",
                         "title": html.unescape(it.get("title", "")).replace(",", ";"),
                         "description": body.replace(",", ";"), "buggy_path": "", "fixed_path": "",
                         "url": it.get("link", "")})
        if not r.get("has_more"):
            break
        if r.get("backoff"):
            time.sleep(r["backoff"])
        page += 1
        time.sleep(0.3)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "source", "title", "description", "buggy_path", "fixed_path", "url"])
        w.writeheader(); w.writerows(rows)
    print(f"Wrote {len(rows)} accepted-answer candidates -> {args.out}")
    print(f"Next: python curation/tier1_screen.py --candidates {args.out} --out curation/triage/se_triage.csv")


if __name__ == "__main__":
    main()
