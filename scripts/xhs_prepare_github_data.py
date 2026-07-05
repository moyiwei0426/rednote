#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare GitHub-ready XHS data exports.

Default mode copies only unified research CSVs and metadata into github_data/.
Raw crawl outputs can be archived for a private repository with --include-raw-zip.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_EXPORT_FILES = [
    "notes_unified.csv",
    "comments_unified.csv",
    "actor_commenter_seed.csv",
    "event_phase_summary.csv",
    "representative_notes.csv",
]


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return max(sum(1 for _ in fh) - 1, 0)


def count_jsonl_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for line in fh if line.strip())


def copy_exports(merged_dir: Path, output_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in DEFAULT_EXPORT_FILES:
        source = merged_dir / name
        if not source.exists():
            continue
        dest = output_dir / name
        shutil.copy2(source, dest)
        rows.append(
            {
                "file": name,
                "kind": "unified_csv",
                "rows": str(count_csv_rows(dest)),
                "bytes": str(dest.stat().st_size),
                "note": "GitHub-ready unified research table",
            }
        )
    return rows


def write_inventory(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["file", "kind", "rows", "bytes", "note"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_readme(path: Path, run_id: str, source_run_dir: Path, include_raw_zip: bool) -> None:
    mode = "private raw archive included" if include_raw_zip else "unified CSV only"
    path.write_text(
        f"""# XHS GitHub Data Export: {run_id}

Generated at: {datetime.now().isoformat(timespec="seconds")}

Source run directory:

```text
{source_run_dir}
```

Mode: {mode}

## Tables

- `notes_unified.csv`: note-level event/phase table.
- `comments_unified.csv`: comment-level behavior-event table.
- `actor_commenter_seed.csv`: anonymous commenter seed table for agent simulation.
- `event_phase_summary.csv`: phase-level quality and coverage summary.
- `representative_notes.csv`: selected representative notes.
- `data_inventory.csv`: file list, row counts, and notes.

## Privacy Boundary

This export is designed for research storage and downstream agent modeling.
It does not require raw user identity chains, follow lists, fan lists, like lists,
avatar URLs, or private/semi-private content.

If `raw_run_archive.zip` exists, store this repository as private only.
Raw crawler outputs can include logs and request-use URLs that should not be
published in a public repository.
""",
        encoding="utf-8",
    )


def archive_raw_run(run_dir: Path, archive_path: Path) -> tuple[int, int]:
    files = 0
    jsonl_rows = 0
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as zf:
        for path in run_dir.rglob("*"):
            if not path.is_file():
                continue
            files += 1
            if path.suffix == ".jsonl":
                jsonl_rows += count_jsonl_rows(path)
            zf.write(path, path.relative_to(run_dir.parent))
    return files, jsonl_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("github_data"))
    parser.add_argument("--export-name", default="")
    parser.add_argument("--include-raw-zip", action="store_true")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    merged_dir = run_dir / "merged"
    if not merged_dir.exists():
        raise SystemExit(f"merged directory not found: {merged_dir}")

    export_name = args.export_name or run_dir.name
    output_dir = args.output_root / export_name
    rows = copy_exports(merged_dir, output_dir)

    if args.include_raw_zip:
        archive_path = output_dir / "raw_run_archive.zip"
        file_count, jsonl_rows = archive_raw_run(run_dir, archive_path)
        rows.append(
            {
                "file": archive_path.name,
                "kind": "private_raw_archive",
                "rows": str(jsonl_rows),
                "bytes": str(archive_path.stat().st_size),
                "note": f"Private only; contains {file_count} raw run files",
            }
        )

    write_inventory(output_dir / "data_inventory.csv", rows)
    write_readme(output_dir / "README.md", export_name, run_dir, args.include_raw_zip)
    (output_dir / "export_meta.json").write_text(
        json.dumps(
            {
                "export_name": export_name,
                "source_run_dir": str(run_dir),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "include_raw_zip": args.include_raw_zip,
                "files": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
