#!/usr/bin/env python3
"""Merge all available Device C E008/E009/E010 notes and first-level comments."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs" / "xhs_core_events"
OUTPUT = RUNS / "device_c_merged_20260715" / "exports" / "device_c_unified"
EVENT_NAMES = {"E008": "Qwen3.6", "E009": "豆包 Seed 2.0", "E010": "Kimi 新功能"}
EVENT_IDS = set(EVENT_NAMES)
TEXT_FIELDS = {"title", "desc", "content", "nickname", "tag_list", "public_ip_location"}

NOTE_FIELDS = [
    "event_id", "event_name", "note_id", "note_url", "title", "desc", "content_type",
    "publish_time", "publish_time_utc", "publish_time_shanghai", "creator_hash", "nickname",
    "public_ip_location", "liked_count", "collected_count", "comment_count", "share_count",
    "tag_list", "video_url", "source_run", "source_file",
]
COMMENT_FIELDS = [
    "event_id", "event_name", "note_id", "comment_id", "parent_comment_id", "content",
    "create_time", "create_time_utc", "create_time_shanghai", "creator_hash", "nickname",
    "sub_comment_count", "pictures", "last_modify_ts", "like_count", "public_ip_location",
    "source_run", "source_file",
]


def repair_text(value: object) -> str:
    text = "" if value is None else str(value)
    if not text:
        return text
    try:
        return text.encode("gb18030").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def iso_times(value: object) -> tuple[str, str]:
    try:
        moment = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return "", ""
    return moment.isoformat(), moment.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()


def event_from_path(path: Path) -> str | None:
    for part in path.parts:
        if part in EVENT_IDS:
            return part
    return None


def jsonl_rows(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    parsed = 0
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            parsed += 1
            yield line_number, data, "json"
        except json.JSONDecodeError:
            continue

    # Some crawler exports contain literal newlines inside a single note's
    # description. Recover that one-record file without weakening normal JSONL
    # parsing for multi-record files.
    if parsed == 0 and path.name.startswith("detail_contents_"):
        repaired = text.strip().replace("\r\n", "\\n").replace("\n", "\\n")
        try:
            yield 1, json.loads(repaired), "repaired-json"
        except json.JSONDecodeError:
            pass


def source_priority(run_name: str, path: Path) -> tuple[int, int]:
    mtime = int(path.stat().st_mtime)
    return (mtime, len(str(path)))


def normalize_note(event_id: str, data: dict, run_name: str, path: Path) -> dict[str, str]:
    published_utc, published_shanghai = iso_times(data.get("time"))
    row = {
        "event_id": event_id,
        "event_name": EVENT_NAMES[event_id],
        "note_id": str(data.get("note_id", "")),
        "note_url": str(data.get("note_url", "")),
        "title": repair_text(data.get("title")),
        "desc": repair_text(data.get("desc")),
        "content_type": str(data.get("type", "")),
        "publish_time": str(data.get("time", "")),
        "publish_time_utc": published_utc,
        "publish_time_shanghai": published_shanghai,
        "creator_hash": str(data.get("creator_hash", "")),
        "nickname": repair_text(data.get("nickname")),
        "public_ip_location": repair_text(data.get("public_ip_location")),
        "liked_count": str(data.get("liked_count", "")),
        "collected_count": str(data.get("collected_count", "")),
        "comment_count": str(data.get("comment_count", "")),
        "share_count": str(data.get("share_count", "")),
        "tag_list": repair_text(data.get("tag_list")),
        "video_url": str(data.get("video_url", "")),
        "source_run": run_name,
        "source_file": str(path.relative_to(ROOT)),
    }
    return row


def normalize_comment(event_id: str, data: dict, run_name: str, path: Path) -> dict[str, str]:
    created_utc, created_shanghai = iso_times(data.get("create_time"))
    return {
        "event_id": event_id,
        "event_name": EVENT_NAMES[event_id],
        "note_id": str(data.get("note_id", "")),
        "comment_id": str(data.get("comment_id", "")),
        "parent_comment_id": str(data.get("parent_comment_id", "")),
        "content": repair_text(data.get("content")),
        "create_time": str(data.get("create_time", "")),
        "create_time_utc": created_utc,
        "create_time_shanghai": created_shanghai,
        "creator_hash": str(data.get("creator_hash", "")),
        "nickname": repair_text(data.get("nickname")),
        "sub_comment_count": str(data.get("sub_comment_count", "")),
        "pictures": str(data.get("pictures", "")),
        "last_modify_ts": str(data.get("last_modify_ts", "")),
        "like_count": str(data.get("like_count", "")),
        "public_ip_location": repair_text(data.get("public_ip_location")),
        "source_run": run_name,
        "source_file": str(path.relative_to(ROOT)),
    }


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    note_candidates: dict[str, tuple[tuple[int, int], dict[str, str]]] = {}
    comment_candidates: dict[str, tuple[tuple[int, int], dict[str, str]]] = {}
    raw_notes = raw_comments = 0
    skipped_invalid = 0

    run_dirs = [path for path in RUNS.iterdir() if path.is_dir() and path.name.startswith("device_c_")]
    for run_dir in run_dirs:
        for path in run_dir.rglob("detail_contents_*.jsonl"):
            event_id = event_from_path(path)
            if not event_id:
                continue
            for _, data, _ in jsonl_rows(path):
                raw_notes += 1
                if not data.get("note_id"):
                    skipped_invalid += 1
                    continue
                row = normalize_note(event_id, data, run_dir.name, path)
                key = f"{event_id}:{row['note_id']}"
                rank = source_priority(run_dir.name, path)
                if key not in note_candidates or rank > note_candidates[key][0]:
                    note_candidates[key] = (rank, row)

        for path in run_dir.rglob("detail_comments_*.jsonl"):
            event_id = event_from_path(path)
            if not event_id:
                continue
            for _, data, _ in jsonl_rows(path):
                raw_comments += 1
                if not data.get("note_id") or not data.get("comment_id"):
                    skipped_invalid += 1
                    continue
                if str(data.get("parent_comment_id", "")):
                    continue
                row = normalize_comment(event_id, data, run_dir.name, path)
                key = f"{event_id}:{row['comment_id']}"
                rank = source_priority(run_dir.name, path)
                if key not in comment_candidates or rank > comment_candidates[key][0]:
                    comment_candidates[key] = (rank, row)

    notes = sorted((item[1] for item in note_candidates.values()), key=lambda row: (row["event_id"], row["note_id"]))
    comments = sorted((item[1] for item in comment_candidates.values()), key=lambda row: (row["event_id"], row["note_id"], row["create_time"], row["comment_id"]))
    write_csv(OUTPUT / "device_c_notes_unified.csv", NOTE_FIELDS, notes)
    write_csv(OUTPUT / "device_c_comments_unified.csv", COMMENT_FIELDS, comments)

    note_counts = Counter(row["event_id"] for row in notes)
    comment_counts = Counter(row["event_id"] for row in comments)
    ip_counts = Counter(row["event_id"] for row in comments if row["public_ip_location"])
    coverage = []
    for event_id in sorted(EVENT_IDS):
        coverage.append(
            {
                "event_id": event_id,
                "event_name": EVENT_NAMES[event_id],
                "unique_notes": note_counts[event_id],
                "unique_top_level_comments": comment_counts[event_id],
                "comments_with_public_ip_location": ip_counts[event_id],
            }
        )
    write_csv(OUTPUT / "device_c_event_coverage.csv", list(coverage[0]), coverage)

    summary = {
        "device_id": "C",
        "events": sorted(EVENT_IDS),
        "raw_note_rows_seen": raw_notes,
        "raw_comment_rows_seen": raw_comments,
        "unique_notes": len(notes),
        "unique_top_level_comments": len(comments),
        "comments_with_public_ip_location": sum(ip_counts.values()),
        "skipped_invalid_rows": skipped_invalid,
        "note_sources_scanned": len(run_dirs),
        "scope": "E008/E009/E010; first-level comments only",
    }
    (OUTPUT / "device_c_merge_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
