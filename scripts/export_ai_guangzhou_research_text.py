#!/usr/bin/env python3
"""Export a public-text-preserving Guangzhou RedNote research delivery."""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


LANES = {
    "device_international-cdp9342": "A",
    "device_international-cdp9343-b": "B",
}
PHASE_LANES = {
    "F001": "A",
    "F002": "A",
    "F003": "B",
    "F004": "A",
    "F005": "B",
    "F006": "B",
}
RESOLVED = {"ok", "skipped_unavailable"}
STRUCTURAL = "ok_structural_reuse"
BJ = ZoneInfo("Asia/Shanghai")

PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("url", re.compile(r"(?i)\b(?:https?://|www\.)\S+"), "[URL]"),
    ("email", re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[ID]"),
    ("bank_card", re.compile(r"(?<!\d)(?:\d[ -]?){16,19}(?!\d)"), "[BANK_CARD]"),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"), "[PHONE]"),
    (
        "contact",
        re.compile(r"(?i)(?:微信|微\s*信|vx|v信|wechat|qq)\s*(?:号|id)?\s*[:：]?\s*[A-Za-z0-9_-]{5,24}"),
        "[CONTACT]",
    ),
    ("mention", re.compile(r"(?<![\w@])@[A-Za-z0-9_\-\u4e00-\u9fff]{2,30}"), "[MENTION]"),
]


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


def clean(value: Any) -> str:
    return str(value or "").strip()


def int_or_blank(value: Any) -> int | str:
    text = clean(value).replace(",", "")
    if not text:
        return ""
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([万千wWkK]?)", text)
    if not match:
        return ""
    number = float(match.group(1))
    multiplier = {"万": 10000, "w": 10000, "W": 10000, "千": 1000, "k": 1000, "K": 1000}.get(match.group(2), 1)
    return int(number * multiplier)


def int_zero(value: Any) -> int:
    parsed = int_or_blank(value)
    return parsed if isinstance(parsed, int) else 0


def timestamp_bj(value: Any) -> tuple[str, str]:
    millis = int_zero(value)
    if not millis:
        return "", ""
    dt = datetime.fromtimestamp(millis / 1000, tz=BJ)
    return dt.isoformat(timespec="seconds"), dt.date().isoformat()


def redact_text(value: Any) -> tuple[str, bool, int, str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    # Preserve line structure while dropping non-semantic end-of-line padding,
    # which otherwise makes Git treat public text as whitespace errors.
    text = "\n".join(line.rstrip(" \t") for line in text.split("\n"))
    counts: Counter[str] = Counter()
    for name, pattern, replacement in PII_PATTERNS:
        text, count = pattern.subn(replacement, text)
        if count:
            counts[name] += count
    return text, bool(counts), sum(counts.values()), ";".join(sorted(counts))


def merge_redaction(*items: tuple[str, bool, int, str]) -> tuple[bool, int, str]:
    types: set[str] = set()
    count = 0
    for _, _, item_count, item_types in items:
        count += item_count
        types.update(filter(None, item_types.split(";")))
    return bool(count), count, ";".join(sorted(types))


def anon_id(secret: bytes, value: Any) -> str:
    raw = clean(value)
    return hmac.new(secret, raw.encode("utf-8"), hashlib.sha256).hexdigest() if raw else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def chunk_context(path: Path) -> tuple[str, int]:
    phase = next((part for part in path.parts if re.fullmatch(r"F\d{3}", part)), "")
    chunk_part = next((part for part in path.parts if re.fullmatch(r"chunk_\d+", part)), "")
    return phase, int(chunk_part.split("_", 1)[1]) if chunk_part else 0


def pagination_complete(output_dir: Path) -> bool:
    pagination_path = output_dir / "xhs" / "quality" / "comment_pagination_status.jsonl"
    rows = list(read_jsonl(pagination_path)) if pagination_path.exists() else []
    if not rows:
        return False
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (clean(row.get("kind")), clean(row.get("note_id")), clean(row.get("root_comment_id")))
        latest[key] = row
    top = [row for key, row in latest.items() if key[0] == "top_level"]
    replies = [row for key, row in latest.items() if key[0] == "reply"]
    if not top or any(row.get("status") != "complete" for row in top + replies):
        return False
    target_path = output_dir / "xhs" / "quality" / "subcomment_parent_targets.jsonl"
    targets = list(read_jsonl(target_path)) if target_path.exists() else []
    expected = {
        (clean(row.get("note_id")), clean(row.get("root_comment_id")))
        for row in targets
        if clean(row.get("root_comment_id"))
    }
    completed = {
        (key[1], key[2])
        for key, row in latest.items()
        if key[0] == "reply" and row.get("status") == "complete"
    }
    return not expected or expected.issubset(completed)


def collect_worklist(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            phase = source.get("phase_id") or source.get("event_id") or ""
            name = source.get("phase_name") or source.get("event_name") or ""
            counters[phase] += 1
            note_id = clean(source.get("note_id"))
            rows.append(
                {
                    "event_id": phase,
                    "event_name": name,
                    "phase_id": phase,
                    "phase_name": name,
                    "event_type": "ai_keyword_followup_international",
                    "source_keyword": source.get("source_keyword", ""),
                    "region": "Guangzhou",
                    "lane": PHASE_LANES.get(phase, ""),
                    "target_sequence": counters[phase],
                    "note_id": note_id,
                    "note_url_public": f"https://www.rednote.com/explore/{note_id}",
                    "representative_rank_in_phase": source.get("representative_rank_in_phase", ""),
                    "representative_score": source.get("representative_score", ""),
                    "selection_reason": source.get("selection_reason", ""),
                }
            )
    return rows


def collect_progress(run_root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for device, lane in LANES.items():
        ledger = run_root / device / "batch_ledger.csv"
        with ledger.open("r", encoding="utf-8-sig", newline="") as handle:
            for source in csv.DictReader(handle):
                phase = clean(source.get("event_id"))
                chunk_match = re.search(r"chunk_(\d+)", clean(source.get("keyword")))
                chunk = int(chunk_match.group(1)) if chunk_match else 0
                if not phase or not chunk:
                    continue
                status = clean(source.get("status"))
                output_dir = run_root / device / "selected-sub-comments" / phase / f"chunk_{chunk:03d}"
                if status not in RESOLVED and pagination_complete(output_dir):
                    status = STRUCTURAL
                row = {
                    "phase_id": phase,
                    "phase_name": source.get("event_name", ""),
                    "lane": lane,
                    "chunk": chunk,
                    "started_at": source.get("started_at", ""),
                    "finished_at": source.get("finished_at", ""),
                    "raw_status": status,
                }
                key = (phase, chunk)
                current = latest.get(key)
                row_resolved = status in RESOLVED | {STRUCTURAL}
                current_resolved = bool(current and current["raw_status"] in RESOLVED | {STRUCTURAL})
                if current is None or (row_resolved and not current_resolved) or (
                    row_resolved == current_resolved and row["finished_at"] >= current["finished_at"]
                ):
                    latest[key] = row
    return latest


def collect_notes(run_root: Path, work_by_note: dict[str, dict[str, Any]], secret: bytes) -> list[dict[str, Any]]:
    latest: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    for path in run_root.rglob("detail_contents_*.jsonl"):
        for source in read_jsonl(path):
            note_id = clean(source.get("note_id"))
            work = work_by_note.get(note_id)
            if not work:
                continue
            title = redact_text(source.get("title"))
            desc = redact_text(source.get("desc"))
            tags = redact_text(source.get("tag_list"))
            redacted, redaction_count, pii_types = merge_redaction(title, desc, tags)
            published_at, publish_date = timestamp_bj(source.get("time"))
            row = {
                "event_id": work["event_id"],
                "event_name": work["event_name"],
                "phase_id": work["phase_id"],
                "phase_name": work["phase_name"],
                "event_type": work["event_type"],
                "source_keyword": work["source_keyword"],
                "region": work["region"],
                "note_id": note_id,
                "note_url_public": work["note_url_public"],
                "title": title[0],
                "desc": desc[0],
                "tag_list": tags[0],
                "publish_time_bj": published_at,
                "publish_date_bj": publish_date,
                "public_ip_location": clean(source.get("public_ip_location")),
                "liked_count_num": int_or_blank(source.get("liked_count")),
                "collected_count_num": int_or_blank(source.get("collected_count")),
                "comment_count_num": int_or_blank(source.get("comment_count")),
                "share_count_num": int_or_blank(source.get("share_count")),
                "representative_score": work["representative_score"],
                "representative_rank_in_phase": work["representative_rank_in_phase"],
                "is_representative_sample": "true",
                "is_marketing": "",
                "content_type": clean(source.get("type")) or "unknown",
                "author_id_anon": anon_id(secret, source.get("creator_hash")),
                "text_redacted": str(redacted).lower(),
                "pii_redaction_count": redaction_count,
                "pii_types": pii_types,
            }
            modified = int_zero(source.get("last_modify_ts"))
            completeness = len(title[0]) + len(desc[0]) + len(tags[0])
            score = (modified, completeness)
            current = latest.get(note_id)
            if current is None or score >= current[0]:
                latest[note_id] = (score, row)
    return sorted((value[1] for value in latest.values()), key=lambda row: (row["phase_id"], row["representative_rank_in_phase"], row["note_id"]))


def collect_comments(
    run_root: Path,
    work_by_note: dict[str, dict[str, Any]],
    note_ids: set[str],
    secret: bytes,
) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], tuple[tuple[int, int], dict[str, Any]]] = {}
    for path in run_root.rglob("detail_comments_*.jsonl"):
        for source in read_jsonl(path):
            note_id = clean(source.get("note_id"))
            comment_id = clean(source.get("comment_id"))
            work = work_by_note.get(note_id)
            if not work or note_id not in note_ids or not comment_id:
                continue
            content = redact_text(source.get("content"))
            comment_time, comment_date = timestamp_bj(source.get("create_time"))
            parent = clean(source.get("parent_comment_id"))
            has_picture = bool(clean(source.get("pictures")))
            content_type = "text_and_image" if content[0] and has_picture else "text" if content[0] else "image_only" if has_picture else "empty"
            row = {
                "event_id": work["event_id"],
                "phase_id": work["phase_id"],
                "note_id": note_id,
                "comment_id": comment_id,
                "parent_comment_id": parent,
                "comment_text": content[0],
                "comment_time_bj": comment_time,
                "comment_date_bj": comment_date,
                "comment_like_count": int_or_blank(source.get("like_count")),
                "commenter_region": clean(source.get("public_ip_location")),
                "is_reply": str(bool(parent)).lower(),
                "sub_comment_count": int_or_blank(source.get("sub_comment_count")),
                "note_is_representative_sample": "true",
                "commenter_id_anon": anon_id(secret, source.get("creator_hash")),
                "content_type": content_type,
                "text_redacted": str(content[1]).lower(),
                "pii_redaction_count": content[2],
                "pii_types": content[3],
            }
            modified = int_zero(source.get("last_modify_ts"))
            completeness = len(content[0]) + (1 if has_picture else 0)
            score = (modified, completeness)
            key = (note_id, comment_id)
            current = latest.get(key)
            if current is None or score >= current[0]:
                latest[key] = (score, row)
    rows = [value[1] for value in latest.values()]
    ids = {(row["note_id"], row["comment_id"]) for row in rows}
    for row in rows:
        row["dangling_parent"] = str(bool(row["parent_comment_id"] and (row["note_id"], row["parent_comment_id"]) not in ids)).lower()
    return sorted(rows, key=lambda row: (row["phase_id"], row["note_id"], row["comment_time_bj"], row["comment_id"]))


def collect_pagination(run_root: Path, work_by_note: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    for path in run_root.rglob("comment_pagination_status.jsonl"):
        phase, chunk = chunk_context(path)
        for source in read_jsonl(path):
            note_id = clean(source.get("note_id"))
            kind = clean(source.get("kind"))
            root_comment_id = clean(source.get("root_comment_id"))
            work = work_by_note.get(note_id)
            if not work or not kind:
                continue
            row = {
                "event_id": work["event_id"],
                "phase_id": work["phase_id"],
                "target_sequence": work["target_sequence"],
                "note_id": note_id,
                "kind": kind,
                "root_comment_id": root_comment_id,
                "status": clean(source.get("status")),
                "stop_reason": clean(source.get("stop_reason")),
                "pages": int_or_blank(source.get("pages")),
                "observed_comments": int_or_blank(source.get("observed_comments")),
                "declared_comments": int_or_blank(source.get("declared_comments")),
                "reply_target_count": int_or_blank(source.get("reply_target_count")),
                "has_more": str(bool(source.get("has_more", False))).lower(),
                "unlimited": str(bool(source.get("unlimited", False))).lower(),
                "recorded_at": clean(source.get("recorded_at")),
            }
            key = (note_id, kind, root_comment_id)
            current = latest.get(key)
            if current is None or row["recorded_at"] >= current[0]:
                latest[key] = (row["recorded_at"], row)
    return sorted((value[1] for value in latest.values()), key=lambda row: (row["phase_id"], row["target_sequence"], row["note_id"], row["kind"], row["root_comment_id"]))


def make_completion(worklist: list[dict[str, Any]], progress: dict[tuple[str, int], dict[str, Any]], note_ids: set[str]) -> list[dict[str, Any]]:
    status_map = {
        "ok": "content_collected",
        STRUCTURAL: "structurally_complete_reuse",
        "skipped_unavailable": "completed_without_accessible_content",
    }
    rows: list[dict[str, Any]] = []
    for work in worklist:
        progress_row = progress.get((work["phase_id"], work["target_sequence"]), {})
        raw_status = clean(progress_row.get("raw_status"))
        effective = status_map.get(raw_status, raw_status or "missing_terminal_status")
        rows.append(
            {
                "event_id": work["event_id"],
                "event_name": work["event_name"],
                "phase_id": work["phase_id"],
                "phase_name": work["phase_name"],
                "region": work["region"],
                "lane": progress_row.get("lane") or work["lane"],
                "target_sequence": work["target_sequence"],
                "note_id": work["note_id"],
                "effective_status": effective,
                "content_available": str(work["note_id"] in note_ids).lower(),
                "started_at": progress_row.get("started_at", ""),
                "finished_at": progress_row.get("finished_at", ""),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hmac-key-file", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    output = args.output_dir.resolve()
    secret = args.hmac_key_file.read_bytes().strip()
    if len(secret) < 32:
        raise SystemExit("HMAC key must contain at least 32 bytes and remain outside the repository")
    output.mkdir(parents=True, exist_ok=True)

    worklist = collect_worklist(run_root / "worklists" / "guangzhou_international_selected_notes_2630.csv")
    work_by_note = {row["note_id"]: row for row in worklist}
    progress = collect_progress(run_root)
    notes = collect_notes(run_root, work_by_note, secret)
    note_ids = {row["note_id"] for row in notes}
    comments = collect_comments(run_root, work_by_note, note_ids, secret)
    pagination = collect_pagination(run_root, work_by_note)
    completion = make_completion(worklist, progress, note_ids)

    fields = {
        "worklist.csv": ["event_id", "event_name", "phase_id", "phase_name", "event_type", "source_keyword", "region", "lane", "target_sequence", "note_id", "note_url_public", "representative_rank_in_phase", "representative_score", "selection_reason"],
        "collection_completion.csv": ["event_id", "event_name", "phase_id", "phase_name", "region", "lane", "target_sequence", "note_id", "effective_status", "content_available", "started_at", "finished_at"],
        "notes_unified.csv": ["event_id", "event_name", "phase_id", "phase_name", "event_type", "source_keyword", "region", "note_id", "note_url_public", "title", "desc", "tag_list", "publish_time_bj", "publish_date_bj", "public_ip_location", "liked_count_num", "collected_count_num", "comment_count_num", "share_count_num", "representative_score", "representative_rank_in_phase", "is_representative_sample", "is_marketing", "content_type", "author_id_anon", "text_redacted", "pii_redaction_count", "pii_types"],
        "comments_unified.csv": ["event_id", "phase_id", "note_id", "comment_id", "parent_comment_id", "comment_text", "comment_time_bj", "comment_date_bj", "comment_like_count", "commenter_region", "is_reply", "sub_comment_count", "note_is_representative_sample", "commenter_id_anon", "content_type", "text_redacted", "pii_redaction_count", "pii_types", "dangling_parent"],
        "pagination_status.csv": ["event_id", "phase_id", "target_sequence", "note_id", "kind", "root_comment_id", "status", "stop_reason", "pages", "observed_comments", "declared_comments", "reply_target_count", "has_more", "unlimited", "recorded_at"],
    }
    data_rows = {
        "worklist.csv": worklist,
        "collection_completion.csv": completion,
        "notes_unified.csv": notes,
        "comments_unified.csv": comments,
        "pagination_status.csv": pagination,
    }
    row_counts = {name: write_csv(output / name, fields[name], rows) for name, rows in data_rows.items()}

    phase_summary: list[dict[str, Any]] = []
    for phase in sorted({row["phase_id"] for row in worklist}):
        phase_targets = [row for row in worklist if row["phase_id"] == phase]
        phase_completion = [row for row in completion if row["phase_id"] == phase]
        phase_notes = [row for row in notes if row["phase_id"] == phase]
        phase_comments = [row for row in comments if row["phase_id"] == phase]
        phase_pages = [row for row in pagination if row["phase_id"] == phase]
        status_counts = Counter(row["effective_status"] for row in phase_completion)
        phase_summary.append(
            {
                "phase_id": phase,
                "phase_name": phase_targets[0]["phase_name"],
                "target_notes": len(phase_targets),
                "content_collected": status_counts["content_collected"],
                "structurally_complete_reuse": status_counts["structurally_complete_reuse"],
                "completed_without_accessible_content": status_counts["completed_without_accessible_content"],
                "landed_notes": len(phase_notes),
                "comments": len(phase_comments),
                "top_level_comments": sum(row["is_reply"] == "false" for row in phase_comments),
                "reply_comments": sum(row["is_reply"] == "true" for row in phase_comments),
                "pagination_records": len(phase_pages),
            }
        )
    row_counts["event_phase_summary.csv"] = write_csv(
        output / "event_phase_summary.csv",
        ["phase_id", "phase_name", "target_notes", "content_collected", "structurally_complete_reuse", "completed_without_accessible_content", "landed_notes", "comments", "top_level_comments", "reply_comments", "pagination_records"],
        phase_summary,
    )

    statuses = Counter(row["effective_status"] for row in completion)
    pagination_statuses = Counter(row["status"] for row in pagination)
    comment_types = Counter(row["content_type"] for row in comments)
    quality = {
        "target_notes": len(worklist),
        "unique_worklist_note_ids": len(work_by_note),
        "completion_rows": len(completion),
        "terminal_status_counts": dict(sorted(statuses.items())),
        "landed_notes": len(notes),
        "notes_with_title": sum(bool(row["title"].strip()) for row in notes),
        "notes_with_desc": sum(bool(row["desc"].strip()) for row in notes),
        "notes_with_tags": sum(bool(row["tag_list"].strip()) for row in notes),
        "note_rows_with_pii_redaction": sum(row["text_redacted"] == "true" for row in notes),
        "note_pii_fragments_redacted": sum(int(row["pii_redaction_count"]) for row in notes),
        "comments": len(comments),
        "top_level_comments": sum(row["is_reply"] == "false" for row in comments),
        "reply_comments": sum(row["is_reply"] == "true" for row in comments),
        "comments_with_text": sum(bool(row["comment_text"].strip()) for row in comments),
        "comment_content_types": dict(sorted(comment_types.items())),
        "comment_rows_with_pii_redaction": sum(row["text_redacted"] == "true" for row in comments),
        "comment_pii_fragments_redacted": sum(int(row["pii_redaction_count"]) for row in comments),
        "dangling_parent_relationships": sum(row["dangling_parent"] == "true" for row in comments),
        "pagination_records": len(pagination),
        "pagination_status_counts": dict(sorted(pagination_statuses.items())),
        "orphan_comment_note_ids": len({row["note_id"] for row in comments} - note_ids),
        "duplicate_note_ids": len(notes) - len(note_ids),
        "duplicate_comment_keys": len(comments) - len({(row["note_id"], row["comment_id"]) for row in comments}),
    }
    (output / "quality_summary.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inventory_rows = []
    for name in [*data_rows, "event_phase_summary.csv", "quality_summary.json"]:
        path = output / name
        rows = row_counts.get(name, 1)
        inventory_rows.append({"file": name, "rows": rows, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    row_counts["data_inventory.csv"] = write_csv(output / "data_inventory.csv", ["file", "rows", "bytes", "sha256"], inventory_rows)

    snapshot_at = datetime.now(BJ).isoformat(timespec="seconds")
    manifest = {
        "schema_version": "ai-keyword-followup-research-text-v1",
        "dataset_id": "AIKF-INT-20260909-full-comments-guangzhou-public-text",
        "snapshot_at": snapshot_at,
        "region": "Guangzhou",
        "collection_platform": "RedNote international",
        "continuation_boundary": "International follow-up dataset; separate from the earlier domestic baseline.",
        "target_notes": len(worklist),
        "content_collected_notes": statuses["content_collected"],
        "structurally_complete_reuse": statuses["structurally_complete_reuse"],
        "completed_without_accessible_content": statuses["completed_without_accessible_content"],
        "landed_notes": len(notes),
        "comment_rows": len(comments),
        "top_level_comment_rows": quality["top_level_comments"],
        "reply_comment_rows": quality["reply_comments"],
        "pagination_records": len(pagination),
        "privacy": {
            "included": "public post titles, descriptions, tags, comment text, public engagement counts, province/country public location, canonical note URLs, relationship and pagination evidence",
            "excluded": "cookies, browser/session state, signed access URLs, xsec tokens, media URLs, crawler logs, proxy/egress details, device/account identifiers, nicknames and raw author/commenter identifiers",
            "identity_method": "HMAC-SHA256 stable anonymous identifiers; key stored outside repository",
            "text_method": "public text retained; detected PII fragments replaced in place and counted",
        },
        "deduplication": {
            "notes": "note_id; latest last_modify_ts with text completeness tie-break",
            "comments": "(note_id, comment_id); latest last_modify_ts with content completeness tie-break",
            "pagination": "(note_id, kind, root_comment_id); latest recorded_at",
            "progress": "(phase_id, chunk); terminal result preferred, latest finished_at tie-break",
        },
        "files": row_counts,
        "completion_claim": "All 2,630 frozen targets have one effective terminal outcome. Public text is present for all accessible landed records; inaccessible targets remain explicit rows.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readme = f"""# Guangzhou AI keyword collection — research-text delivery

- Cutoff: `{snapshot_at}`
- Run: `AIKF-INT-20260909-full-comments`
- Platform/region: RedNote international / Guangzhou

This directory replaces the earlier hash-only Guangzhou snapshot as the analysis-ready delivery. It retains public post titles, descriptions, tags, top-level comments and replies, while removing access credentials and direct identity fields. It remains a continuation dataset and is kept separate from the earlier domestic baseline.

## Inventory

- Frozen targets: **{len(worklist):,}**
- Content collected: **{statuses['content_collected']:,}**
- Structurally complete reuse: **{statuses['structurally_complete_reuse']:,}**
- Completed without accessible content: **{statuses['completed_without_accessible_content']:,}**
- Deduplicated landed notes: **{len(notes):,}**
- Deduplicated comments: **{len(comments):,}** = {quality['top_level_comments']:,} top-level + {quality['reply_comments']:,} replies
- Latest pagination records: **{len(pagination):,}**, all `complete`
- Dangling observed parent relationships: **{quality['dangling_parent_relationships']:,}**; retained and flagged, never invented

`notes_unified.csv` and `comments_unified.csv` contain the public text required for downstream text analysis. Blank comment text is retained: image-only rows are labeled `image_only`, while truly empty rows are labeled `empty`.

## Privacy boundary

The export excludes cookies, session/browser state, signed URLs and `xsec_token`, media CDN URLs, proxy and egress details, device/account identifiers, crawler logs, nicknames and raw creator identifiers. Stable author/commenter linkage uses HMAC-SHA256; its private key is not in this repository. Detected phone numbers, email addresses, ID/bank-card numbers, contact handles, URLs and @mentions are replaced only at the fragment level and counted in `quality_summary.json`.

## Counting rules and known limitations

- Notes are unique by `note_id`; comments by `(note_id, comment_id)`; pagination by `(note_id, kind, root_comment_id)`.
- The 108 inaccessible targets remain in `worklist.csv` and `collection_completion.csv`; no text is invented for them.
- A dangling parent means a reply named a parent that was absent from the landed rows. The observed reply is retained with `dangling_parent=true`.
- Public location is already province/country-level in the source and is retained at that granularity.
- See `docs/RESEARCH_TEXT_PRESERVING_SANITIZATION_PROMPT_ZH.md` for the reusable export standard.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
