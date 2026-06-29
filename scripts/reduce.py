"""Reduce step: concatenate all shard JSONL files into raw_runs.jsonl.

Run after all SLURM array tasks complete. Writes a single file to
data/results/raw_runs.jsonl (one inode on /fred).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--shard_dir", required=True, help="Directory containing shard JSONL files")
    p.add_argument("--out", default="data/results/raw_runs.jsonl")
    args = p.parse_args()

    root = Path(args.root)
    shard_dir = Path(args.shard_dir)
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    shards = sorted(shard_dir.glob("*.jsonl"))
    print(f"Concatenating {len(shards)} shards -> {out}")
    n = 0
    with out.open("w") as fout:
        for shard in shards:
            with shard.open() as fin:
                for line in fin:
                    line = line.strip()
                    if line:
                        fout.write(line + "\n")
                        n += 1
    print(f"Wrote {n} records to {out}")


if __name__ == "__main__":
    main()
