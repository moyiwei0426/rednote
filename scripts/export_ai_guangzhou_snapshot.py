#!/usr/bin/env python3
"""Export a sanitized, auditable Guangzhou international RedNote snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


LANES = {
    "device_international-cdp9342": "A",
    "device_international-cdp9343-b": "B",
}
PHASE_LANES = {
    "F001": "A",
    "F002": "A",
    "F004": "A",
    "F003": "B",
    "F005": "B",
    "F006": "B",
}
RESOLVED_STATUSES = {"ok", "skipped_unavailable"}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def text_hash(*values: Any) -> str:
    text = "\n".join(str(value or "").strip() for value in values).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def int_value(value: Any) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def chunk_context(path: Path) -> tuple[str, int]:
    phase = next((part for part in path.parts if re.fullmatch(r"F\d{3}", part)), "")
    chunk_part = next((part for part in path.parts if re.fullmatch(r"chunk_\d+", part)), "")
    chunk = int(chunk_part.split("_", 1)[1]) if chunk_part else 0
    return phase, chunk


def collect_notes(run_root: Path) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in run_root.rglob("detail_contents_*.jsonl"):
        phase, chunk = chunk_context(path)
        for row in read_jsonl(path):
            note_id = str(row.get("note_id", "")).strip()
            if not note_id:
                continue
            candidate = {
                "note_id": note_id,
                "phase_id": phase,
                "lane": PHASE_LANES.get(phase, ""),
                "chunk": chunk,
                "type": row.get("type", ""),
                "published_at_ms": int_value(row.get("time")),
                "platform_updated_at_ms": int_value(row.get("last_update_time")),
                "likes": int_value(row.get("liked_count")),
                "collections": int_value(row.get("collected_count")),
                "declared_comments": int_value(row.get("comment_count")),
                "shares": int_value(row.get("share_count")),
                "tag_count": len([item for item in str(row.get("tag_list", "")).split(",") if item.strip()]),
                "image_count": len([item for item in str(row.get("image_list", "")).split(",") if item.strip()]),
                "text_sha256": text_hash(row.get("title"), row.get("desc")),
                "record_modified_at_ms": int_value(row.get("last_modify_ts")),
            }
            current = latest.get(note_id)
            if current is None or candidate["record_modified_at_ms"] >= current["record_modified_at_ms"]:
                latest[note_id] = candidate
    return sorted(latest.values(), key=lambda row: (row["phase_id"], row["chunk"], row["note_id"]))


def collect_comments(run_root: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for path in run_root.rglob("detail_comments_*.jsonl"):
        phase, chunk = chunk_context(path)
        for row in read_jsonl(path):
            note_id = str(row.get("note_id", "")).strip()
            comment_id = str(row.get("comment_id", "")).strip()
            if not note_id or not comment_id:
                continue
            creator = str(row.get("creator_hash", "")).strip()
            candidate = {
                "note_id": note_id,
                "comment_id": comment_id,
                "parent_comment_id": str(row.get("parent_comment_id", "")).strip(),
                "phase_id": phase,
                "lane": PHASE_LANES.get(phase, ""),
                "chunk": chunk,
                "created_at_ms": int_value(row.get("create_time")),
                "likes": int_value(row.get("like_count")),
                "declared_subcomments": int_value(row.get("sub_comment_count")),
                "actor_sha256": hashlib.sha256(creator.encode("utf-8")).hexdigest() if creator else "",
                "content_sha256": text_hash(row.get("content")),
                "record_modified_at_ms": int_value(row.get("last_modify_ts")),
            }
            key = (note_id, comment_id)
            current = latest.get(key)
            if current is None or candidate["record_modified_at_ms"] >= current["record_modified_at_ms"]:
                latest[key] = candidate
    return sorted(latest.values(), key=lambda row: (row["phase_id"], row["chunk"], row["note_id"], row["created_at_ms"], row["comment_id"]))


def collect_pagination(run_root: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in run_root.rglob("comment_pagination_status.jsonl"):
        phase, chunk = chunk_context(path)
        for row in read_jsonl(path):
            note_id = str(row.get("note_id", "")).strip()
            kind = str(row.get("kind", "")).strip()
            root_comment_id = str(row.get("root_comment_id", "")).strip()
            if not note_id or not kind:
                continue
            candidate = {
                "note_id": note_id,
                "kind": kind,
                "root_comment_id": root_comment_id,
                "phase_id": phase,
                "lane": PHASE_LANES.get(phase, ""),
                "chunk": chunk,
                "status": row.get("status", ""),
                "stop_reason": row.get("stop_reason", ""),
                "pages": int_value(row.get("pages")),
                "observed_comments": int_value(row.get("observed_comments")),
                "declared_comments": int_value(row.get("declared_comments")),
                "reply_target_count": int_value(row.get("reply_target_count")),
                "has_more": bool(row.get("has_more", False)),
                "unlimited": bool(row.get("unlimited", False)),
                "recorded_at": row.get("recorded_at", ""),
            }
            key = (note_id, kind, root_comment_id)
            current = latest.get(key)
            if current is None or str(candidate["recorded_at"]) >= str(current["recorded_at"]):
                latest[key] = candidate
    return sorted(latest.values(), key=lambda row: (row["phase_id"], row["chunk"], row["note_id"], row["kind"], row["root_comment_id"]))


def collect_worklist(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            phase = source.get("phase_id") or source.get("event_id") or ""
            counters[phase] += 1
            rows.append(
                {
                    "phase_id": phase,
                    "phase_name": source.get("phase_name") or source.get("event_name") or "",
                    "lane": PHASE_LANES.get(phase, ""),
                    "phase_sequence": counters[phase],
                    "note_id": source.get("note_id", ""),
                    "representative_rank_in_phase": source.get("representative_rank_in_phase", ""),
                    "representative_score": source.get("representative_score", ""),
                    "source_keyword": source.get("source_keyword", ""),
                    "selection_reason": source.get("selection_reason", ""),
                }
            )
    return rows


def collect_progress(run_root: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for device, lane in LANES.items():
        ledger = run_root / device / "batch_ledger.csv"
        with ledger.open("r", encoding="utf-8-sig", newline="") as handle:
            for source in csv.DictReader(handle):
                phase = source.get("event_id", "")
                keyword = source.get("keyword", "")
                chunk_match = re.search(r"chunk_(\d+)", keyword)
                chunk = int(chunk_match.group(1)) if chunk_match else 0
                row = {
                    "phase_id": phase,
                    "phase_name": source.get("event_name", ""),
                    "lane": lane,
                    "chunk": chunk,
                    "started_at": source.get("started_at", ""),
                    "finished_at": source.get("finished_at", ""),
                    "status": source.get("status", ""),
                    "returncode": source.get("returncode", ""),
                    "captcha_detected": source.get("captcha_detected", ""),
                }
                latest[(lane, phase, keyword)] = row
    return sorted(latest.values(), key=lambda row: (row["phase_id"], row["chunk"], row["lane"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    worklist = collect_worklist(run_root / "worklists" / "guangzhou_international_selected_notes_2630.csv")
    progress = collect_progress(run_root)
    notes = collect_notes(run_root)
    comments = collect_comments(run_root)
    pagination = collect_pagination(run_root)

    counts = {
        "worklist": write_csv(output / "worklist_sanitized.csv", ["phase_id", "phase_name", "lane", "phase_sequence", "note_id", "representative_rank_in_phase", "representative_score", "source_keyword", "selection_reason"], worklist),
        "progress": write_csv(output / "batch_progress_sanitized.csv", ["phase_id", "phase_name", "lane", "chunk", "started_at", "finished_at", "status", "returncode", "captcha_detected"], progress),
        "notes": write_csv(output / "notes_sanitized.csv", ["note_id", "phase_id", "lane", "chunk", "type", "published_at_ms", "platform_updated_at_ms", "likes", "collections", "declared_comments", "shares", "tag_count", "image_count", "text_sha256", "record_modified_at_ms"], notes),
        "comments": write_csv(output / "comments_sanitized.csv", ["note_id", "comment_id", "parent_comment_id", "phase_id", "lane", "chunk", "created_at_ms", "likes", "declared_subcomments", "actor_sha256", "content_sha256", "record_modified_at_ms"], comments),
        "pagination": write_csv(output / "pagination_status_sanitized.csv", ["note_id", "kind", "root_comment_id", "phase_id", "lane", "chunk", "status", "stop_reason", "pages", "observed_comments", "declared_comments", "reply_target_count", "has_more", "unlimited", "recorded_at"], pagination),
    }

    statuses = Counter(row["status"] for row in progress)
    closed = statuses["ok"] + statuses["skipped_unavailable"]
    comment_ids = {(row["note_id"], row["comment_id"]) for row in comments}
    dangling_parents = sum(
        1 for row in comments
        if row["parent_comment_id"] and (row["note_id"], row["parent_comment_id"]) not in comment_ids
    )
    pagination_statuses = Counter(row["status"] for row in pagination)
    snapshot_at = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest = {
        "schema_version": "ai-keyword-followup-guangzhou-snapshot-v1",
        "dataset_id": "AIKF-INT-20260909-full-comments",
        "snapshot_at": snapshot_at,
        "scope": "Guangzhou international RedNote selected-note body plus first- and second-level comments; in-progress snapshot.",
        "target_notes": len(worklist),
        "resolved_notes": closed,
        "remaining_notes": len(worklist) - closed,
        "status_counts": dict(sorted(statuses.items())),
        "unique_landed_notes": len(notes),
        "unique_comments": len(comments),
        "pagination_records": len(pagination),
        "pagination_status_counts": dict(sorted(pagination_statuses.items())),
        "dangling_parent_comment_relationships": dangling_parents,
        "files": counts,
        "privacy_boundary": "No cookies, browser profiles, credentials, proxy or IP details, account/device identifiers, local paths, logs, xsec tokens, signed URLs, nicknames, locations, media URLs, or raw post/comment text. Text and actor values are SHA-256 digests.",
        "completion_claim": "Partial snapshot only; collection continues after this cutoff.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
