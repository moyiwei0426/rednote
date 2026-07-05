#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Print lightweight status for one distributed XHS device run."""

from __future__ import annotations

import argparse
import csv
import subprocess
from collections import Counter
from pathlib import Path


def normalize_device(value: str) -> str:
    return value.strip().lower().removeprefix("device_")


def count_jsonl_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


def print_processes() -> None:
    out = subprocess.check_output(["ps", "-axo", "pid,ppid,etime,state,command"], text=True)
    rows = [
        line
        for line in out.splitlines()
        if ("xhs_distributed_runner" in line or "main.py --platform xhs" in line)
        and "xhs_device_status.py" not in line
    ]
    print("processes:")
    print("\n".join(rows) if rows else "  NO_XHS_PROCESSES")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, default=Path("runs/xhs_core_events"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--device-id", default="A")
    args = parser.parse_args()

    device_root = args.run_root / args.run_id / f"device_{normalize_device(args.device_id)}"
    ledger = device_root / "batch_ledger.csv"

    print_processes()
    print(f"\ndevice_root: {device_root.resolve()}")
    if not ledger.exists():
        print("ledger: MISSING")
    else:
        rows = list(csv.DictReader(ledger.open(encoding="utf-8-sig", newline="")))
        print(f"ledger_rows: {len(rows)}")
        print(f"stage_status: {dict(Counter((row.get('stage'), row.get('status')) for row in rows))}")
        for row in rows[-8:]:
            print(
                "tail:",
                {
                    key: row.get(key, "")
                    for key in ("stage", "event_id", "keyword", "status", "started_at", "finished_at")
                },
            )

    contents = sum(count_jsonl_rows(path) for path in device_root.glob("**/xhs/jsonl/*contents*.jsonl"))
    comments = sum(count_jsonl_rows(path) for path in device_root.glob("**/xhs/jsonl/*comments*.jsonl"))
    print(f"raw_content_rows: {contents}")
    print(f"raw_comment_rows: {comments}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
