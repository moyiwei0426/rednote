#!/usr/bin/env python3
"""Export a resumable Wuhan collection checkpoint without account credentials."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


NOTE_FIELDS = [
    "chunk_index", "collection_status", "event_id", "event_name", "phase_id",
    "phase_name", "note_id", "note_url", "type", "title", "desc", "time",
    "last_update_time", "creator_hash", "nickname", "liked_count",
    "collected_count", "comment_count", "share_count", "image_list", "tag_list",
    "source_keyword", "public_ip_location", "last_modify_ts",
]
COMMENT_FIELDS = [
    "chunk_index", "collection_status", "event_id", "note_id", "comment_id",
    "parent_comment_id", "create_time", "content", "creator_hash", "nickname",
    "like_count", "sub_comment_count", "pictures", "public_ip_location",
    "last_modify_ts",
]
WORKLIST_FIELDS = [
    "chunk_index", "collection_status", "event_id", "event_name", "phase_id",
    "phase_name", "note_id", "note_url", "source_regions", "source_keywords",
    "assignment_hash", "note_records", "comment_records", "top_level_comments",
    "reply_comments", "pagination_status", "resume_action",
]


def read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def find_jsonl(batch_dir: Path, stem: str) -> list[Path]:
    return sorted(batch_dir.glob(f"xhs/jsonl/{stem}_*.jsonl"))


def sanitize_url(note_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def json_cell(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def project(row: dict, fields: list[str]) -> dict:
    return {field: json_cell(row.get(field, "")) for field in fields}


def load_batch(batch_dir: Path, chunk: int, status: str, queue_row: dict):
    notes: OrderedDict[str, dict] = OrderedDict()
    comments: OrderedDict[str, dict] = OrderedDict()
    quality_rows = []
    common = {
        "chunk_index": chunk,
        "collection_status": status,
        "event_id": queue_row["event_id"],
    }
    for path in find_jsonl(batch_dir, "detail_contents"):
        for row in read_jsonl(path):
            note_id = str(row.get("note_id") or queue_row["note_id"])
            row.update(common)
            row.update({key: queue_row.get(key, "") for key in ("event_name", "phase_id", "phase_name")})
            row["note_id"] = note_id
            row["note_url"] = sanitize_url(note_id)
            row.pop("xsec_token", None)
            notes[note_id] = project(row, NOTE_FIELDS)
    for path in find_jsonl(batch_dir, "detail_comments"):
        for row in read_jsonl(path):
            comment_id = str(row.get("comment_id", ""))
            if not comment_id:
                continue
            row.update(common)
            comments[comment_id] = project(row, COMMENT_FIELDS)
    for path in sorted(batch_dir.glob("xhs/quality/comment_pagination_status.jsonl")):
        for row in read_jsonl(path):
            row.update(common)
            quality_rows.append(row)
    return list(notes.values()), list(comments.values()), quality_rows


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(OrderedDict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--completed-through", type=int, required=True)
    parser.add_argument("--partial-chunk", type=int)
    args = parser.parse_args()

    with args.queue.open("r", encoding="utf-8-sig", newline="") as handle:
        queue = list(csv.DictReader(handle))
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    full_notes: OrderedDict[str, dict] = OrderedDict()
    full_comments: OrderedDict[str, dict] = OrderedDict()
    partial_notes: OrderedDict[str, dict] = OrderedDict()
    partial_comments: OrderedDict[str, dict] = OrderedDict()
    quality = []
    worklist = []

    for chunk, queue_row in enumerate(queue, start=1):
        if chunk <= args.completed_through:
            status = "complete"
            batch_dir = args.run_dir / "device_wuhan/selected-sub-comments/GK2026D1" / f"chunk_{chunk:03d}"
        elif chunk == args.partial_chunk:
            status = "partial"
            batch_dir = args.run_dir / "stopped_partial_20260823_154508/selected-sub-comments/GK2026D1" / f"chunk_{chunk:03d}"
        else:
            status = "pending"
            batch_dir = None

        notes = comments = batch_quality = []
        if batch_dir and batch_dir.exists():
            notes, comments, batch_quality = load_batch(batch_dir, chunk, status, queue_row)
            quality.extend(batch_quality)
            target_notes = full_notes if status == "complete" else partial_notes
            target_comments = full_comments if status == "complete" else partial_comments
            for row in notes:
                target_notes[row["note_id"]] = row
            for row in comments:
                target_comments[row["comment_id"]] = row

        pagination = ";".join(sorted({str(row.get("status", "")) for row in batch_quality if row.get("status")}))
        worklist.append({
            **{key: queue_row.get(key, "") for key in WORKLIST_FIELDS},
            "chunk_index": chunk,
            "collection_status": status,
            "note_url": sanitize_url(queue_row["note_id"]),
            "note_records": len(notes),
            "comment_records": len(comments),
            "top_level_comments": sum(not row.get("parent_comment_id") for row in comments),
            "reply_comments": sum(bool(row.get("parent_comment_id")) for row in comments),
            "pagination_status": pagination,
            "resume_action": (
                "none" if status == "complete" else
                "restart_from_first_comment_page_then_deduplicate_by_comment_id" if status == "partial" else
                "collect_normally"
            ),
        })

    write_csv(output / "notes_public_full.csv", list(full_notes.values()), NOTE_FIELDS)
    write_csv(output / "comments_public_full.csv", list(full_comments.values()), COMMENT_FIELDS)
    write_csv(output / "partial_notes_public_full.csv", list(partial_notes.values()), NOTE_FIELDS)
    write_csv(output / "partial_comments_public_full.csv", list(partial_comments.values()), COMMENT_FIELDS)
    write_csv(output / "collection_worklist_status.csv", worklist, WORKLIST_FIELDS)
    write_csv(output / "comment_pagination_status.csv", quality)

    files = [
        "notes_public_full.csv", "comments_public_full.csv", "partial_notes_public_full.csv",
        "partial_comments_public_full.csv", "collection_worklist_status.csv",
        "comment_pagination_status.csv",
    ]
    manifest = {
        "schema_version": "GK2026D1-wuhan-checkpoint-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "device": "wuhan",
        "event_id": "GK2026D1",
        "queue_items": len(queue),
        "complete_items": args.completed_through,
        "partial_items": 1 if args.partial_chunk else 0,
        "pending_items": len(queue) - args.completed_through - (1 if args.partial_chunk else 0),
        "complete_unique_notes": len(full_notes),
        "complete_unique_comments": len(full_comments),
        "complete_top_level_comments": sum(not row.get("parent_comment_id") for row in full_comments.values()),
        "complete_reply_comments": sum(bool(row.get("parent_comment_id")) for row in full_comments.values()),
        "partial_unique_notes": len(partial_notes),
        "partial_unique_comments": len(partial_comments),
        "privacy_boundary": "Public research fields retained; cookies, browser profiles, logs, and xsec_token excluded.",
        "files": {},
    }
    for name in files:
        manifest["files"][name] = {"sha256": sha256(output / name), "bytes": (output / name).stat().st_size}
    (output / "checkpoint_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
