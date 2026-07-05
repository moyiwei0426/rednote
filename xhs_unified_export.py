#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge MediaCrawler XHS outputs into unified research CSVs.

The exporter keeps the same schema for AI events and baseline events, computes a
representative interaction score, and marks high-interaction representative
notes per event/phase.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


BJ = timezone(timedelta(hours=8))
MARKETING_PATTERNS = (
    "私信",
    "领取",
    "资料包",
    "课程",
    "训练营",
    "一对一",
    "咨询",
    "规划师",
    "报考机构",
    "志愿卡",
    "加群",
    "扫码",
    "代理",
)


def parse_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if math.isnan(value) if isinstance(value, float) else False:
            return 0
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    multiplier = 1.0
    if text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    elif text.lower().endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0
    return int(float(match.group(0)) * multiplier)


def bj_time(ms_or_s: Any) -> tuple[str, str]:
    try:
        value = float(ms_or_s)
    except Exception:
        return "", ""
    if value <= 0:
        return "", ""
    if value > 10_000_000_000:
        value = value / 1000.0
    dt = datetime.fromtimestamp(value, BJ)
    return dt.strftime("%Y-%m-%d %H:%M:%S"), dt.strftime("%Y-%m-%d")


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def in_manifest_window(publish_date: str, manifest_row: dict[str, str]) -> bool:
    start = parse_date(manifest_row.get("analysis_window_start"))
    end = parse_date(manifest_row.get("analysis_window_end"))
    if not start and not end:
        return True
    current = parse_date(publish_date)
    if not current:
        return False
    if start and current < start:
        return False
    if end and current > end:
        return False
    return True


def canonical_note_url(note_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""


def read_manifest(path: Path | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            event_id = (row.get("event_id") or "").strip()
            if event_id:
                rows[event_id] = row
    return rows


def find_batch_dirs(run_dir: Path) -> list[Path]:
    return sorted(path.parent for path in run_dir.glob("**/batch_meta.json"))


def load_batch_meta(batch_dir: Path) -> dict[str, Any]:
    meta_path = batch_dir / "batch_meta.json"
    return json.loads(meta_path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def infer_event_ids(event_id: str) -> tuple[str, str]:
    if re.match(r"^B\d+_P\d+$", event_id):
        return event_id.split("_", 1)[0], event_id
    return event_id, ""


def infer_event_type(event_id: str, country_group: str) -> str:
    if event_id.startswith("B"):
        return "baseline_national_life_event"
    if country_group.lower() == "application":
        return "application_reference"
    return "ai_model_event"


def infer_content_type(text: str) -> str:
    t = text.lower()
    if any(word in text for word in ("祝福", "加油", "倒计时", "上岸")):
        return "blessing"
    if any(word in text for word in ("陪考", "考场", "开考", "第一天", "结束")):
        return "exam_scene"
    if any(word in text for word in ("作文", "数学", "语文", "考题", "吐槽")):
        return "exam_topic_discussion"
    if any(word in text for word in ("查分", "成绩", "分数线", "晒分", "录取线")):
        return "score_result"
    if any(word in text for word in ("志愿", "专业", "报考", "大学")):
        return "volunteer_decision"
    if any(word in text for word in ("教程", "测评", "怎么用", "编程", "api", "agent")) or "ai" in t:
        return "ai_usage_discussion"
    if any(word in text for word in ("私信", "课程", "训练营", "咨询", "领取")):
        return "marketing"
    return "general_discussion"


def is_marketing_text(text: str) -> bool:
    return any(pattern in text for pattern in MARKETING_PATTERNS)


def representative_score(row: dict[str, Any]) -> int:
    return (
        parse_count(row.get("liked_count"))
        + 3 * parse_count(row.get("comment_count"))
        + 2 * parse_count(row.get("collected_count"))
        + 2 * parse_count(row.get("share_count"))
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def merge_notes(run_dir: Path, manifest: dict[str, dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    notes_by_id: dict[str, dict[str, Any]] = {}
    for batch_dir in find_batch_dirs(run_dir):
        meta = load_batch_meta(batch_dir)
        event = meta.get("event") or {}
        raw_event_id = event.get("event_id") or ""
        event_id, phase_id = infer_event_ids(raw_event_id)
        event_manifest = manifest.get(raw_event_id, {})
        event_name = event_manifest.get("event_name") or event.get("event_name") or ""
        phase_name = event_name if phase_id else ""
        event_type = infer_event_type(raw_event_id, event.get("country_group") or "")
        source_keyword = meta.get("keyword") or ""
        device = meta.get("device_id") or ""
        account = meta.get("account_id") or ""
        collected_at = meta.get("started_at") or ""
        for contents_path in sorted(batch_dir.glob("xhs/jsonl/*contents*.jsonl")):
            for row in iter_jsonl(contents_path):
                note_id = str(row.get("note_id") or "").strip()
                if not note_id:
                    continue
                publish_time, publish_date = bj_time(row.get("time"))
                if not in_manifest_window(publish_date, event_manifest):
                    continue
                title = str(row.get("title") or "")
                desc = str(row.get("desc") or "")
                text = f"{title}\n{desc}\n{row.get('tag_list') or ''}"
                score = representative_score(row)
                local = {
                    "event_id": event_id,
                    "event_name": "2026高考" if event_id == "B001" else event_name,
                    "phase_id": phase_id,
                    "phase_name": phase_name,
                    "event_type": event_type,
                    "source_keyword": source_keyword or row.get("source_keyword") or "",
                    "note_id": note_id,
                    "note_url_public": canonical_note_url(note_id),
                    "note_url_access": row.get("note_url") or "",
                    "title": title,
                    "desc": desc,
                    "tag_list": row.get("tag_list") or "",
                    "publish_time_bj": publish_time,
                    "publish_date_bj": publish_date,
                    "creator_hash": row.get("creator_hash") or "",
                    "nickname": row.get("nickname") or "",
                    "public_ip_location": row.get("public_ip_location") or "",
                    "liked_count_num": parse_count(row.get("liked_count")),
                    "collected_count_num": parse_count(row.get("collected_count")),
                    "comment_count_num": parse_count(row.get("comment_count")),
                    "share_count_num": parse_count(row.get("share_count")),
                    "representative_score": score,
                    "representative_rank_in_phase": "",
                    "is_representative_sample": False,
                    "is_marketing": is_marketing_text(text),
                    "content_type": infer_content_type(text),
                    "collected_device": device,
                    "collected_account": account,
                    "collected_at_bj": collected_at,
                }
                old = notes_by_id.get(note_id)
                if not old or score > int(old.get("representative_score") or 0):
                    notes_by_id[note_id] = local
    rows = list(notes_by_id.values())
    return rows, notes_by_id


def mark_representative_notes(notes: list[dict[str, Any]], per_phase: int) -> None:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in notes:
        key = note.get("phase_id") or note.get("event_id") or "unknown"
        groups[key].append(note)
    for group_rows in groups.values():
        group_rows.sort(key=lambda row: int(row.get("representative_score") or 0), reverse=True)
        for idx, row in enumerate(group_rows, start=1):
            row["representative_rank_in_phase"] = idx
            row["is_representative_sample"] = idx <= per_phase


def merge_comments(run_dir: Path, notes_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    comments_by_id: dict[str, dict[str, Any]] = {}
    for batch_dir in find_batch_dirs(run_dir):
        meta = load_batch_meta(batch_dir)
        device = meta.get("device_id") or ""
        account = meta.get("account_id") or ""
        collected_at = meta.get("started_at") or ""
        raw_event = (meta.get("event") or {}).get("event_id") or ""
        fallback_event_id, fallback_phase_id = infer_event_ids(raw_event)
        for comments_path in sorted(batch_dir.glob("xhs/jsonl/*comments*.jsonl")):
            for row in iter_jsonl(comments_path):
                comment_id = str(row.get("comment_id") or "").strip()
                note_id = str(row.get("note_id") or "").strip()
                if not comment_id:
                    continue
                note = notes_by_id.get(note_id, {})
                comment_time, comment_date = bj_time(row.get("create_time"))
                local = {
                    "event_id": note.get("event_id") or fallback_event_id,
                    "phase_id": note.get("phase_id") or fallback_phase_id,
                    "note_id": note_id,
                    "comment_id": comment_id,
                    "parent_comment_id": row.get("parent_comment_id") or "",
                    "comment_text": row.get("content") or "",
                    "comment_time": comment_time,
                    "comment_date_bj": comment_date,
                    "comment_like_count": parse_count(row.get("like_count")),
                    "commenter_region": row.get("public_ip_location") or "",
                    "commenter_anonymous_hash": row.get("creator_hash") or "",
                    "is_reply": bool(row.get("parent_comment_id")),
                    "sub_comment_count": parse_count(row.get("sub_comment_count")),
                    "note_is_representative_sample": bool(note.get("is_representative_sample")),
                    "collected_device": device,
                    "collected_account": account,
                    "collected_at_bj": collected_at,
                }
                old = comments_by_id.get(comment_id)
                if not old or local["comment_like_count"] > int(old.get("comment_like_count") or 0):
                    comments_by_id[comment_id] = local
    return list(comments_by_id.values())


def build_actor_seed(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in comments:
        actor = row.get("commenter_anonymous_hash") or ""
        if not actor:
            continue
        grouped[(actor, row.get("event_id") or "", row.get("phase_id") or "")].append(row)
    output = []
    for (actor, event_id, phase_id), rows in grouped.items():
        regions = sorted({row.get("commenter_region") for row in rows if row.get("commenter_region")})
        likes = [int(row.get("comment_like_count") or 0) for row in rows]
        first_seen = sorted(row.get("comment_time") or "" for row in rows if row.get("comment_time"))
        sample_reason = []
        if likes and max(likes) >= 10:
            sample_reason.append("high_like_commenter")
        if len(rows) >= 2:
            sample_reason.append("repeat_commenter")
        output.append({
            "actor_hash": actor,
            "event_id": event_id,
            "phase_id": phase_id,
            "actor_role": "commenter",
            "comment_count_in_phase": len(rows),
            "first_seen_time_bj": first_seen[0] if first_seen else "",
            "regions_observed": "|".join(regions),
            "avg_comment_like": round(sum(likes) / len(likes), 2) if likes else 0,
            "max_comment_like": max(likes) if likes else 0,
            "dominant_comment_type": "",
            "sentiment_tendency": "",
            "knowledge_behavior_type": "",
            "sample_reason": "|".join(sample_reason) or "ordinary_commenter",
        })
    return output


def build_representative_collection_urls(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in notes:
        if not row.get("is_representative_sample"):
            continue
        note_url = row.get("note_url_access") or ""
        if not note_url:
            continue
        rows.append({
            "event_id": row.get("event_id") or "",
            "event_name": row.get("event_name") or "",
            "phase_id": row.get("phase_id") or "",
            "phase_name": row.get("phase_name") or "",
            "note_id": row.get("note_id") or "",
            "note_url": note_url,
            "representative_rank_in_phase": row.get("representative_rank_in_phase") or "",
            "representative_score": row.get("representative_score") or "",
        })
    return rows


def build_summary(notes: list[dict[str, Any]], comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    note_groups = defaultdict(list)
    comment_groups = defaultdict(list)
    for row in notes:
        note_groups[row.get("phase_id") or row.get("event_id")].append(row)
    for row in comments:
        comment_groups[row.get("phase_id") or row.get("event_id")].append(row)
    keys = sorted(set(note_groups) | set(comment_groups))
    summary = []
    for key in keys:
        nrows = note_groups.get(key, [])
        crows = comment_groups.get(key, [])
        regions = {row.get("commenter_region") for row in crows if row.get("commenter_region")}
        types = Counter(row.get("content_type") or "" for row in nrows)
        summary.append({
            "phase_or_event_id": key,
            "notes": len(nrows),
            "representative_notes": sum(1 for row in nrows if row.get("is_representative_sample")),
            "comments": len(crows),
            "comments_with_region": sum(1 for row in crows if row.get("commenter_region")),
            "regions_count": len(regions),
            "marketing_notes": sum(1 for row in nrows if row.get("is_marketing")),
            "top_content_type": types.most_common(1)[0][0] if types else "",
        })
    return summary


NOTE_FIELDS = [
    "event_id", "event_name", "phase_id", "phase_name", "event_type", "source_keyword",
    "note_id", "note_url_public", "title", "desc", "tag_list", "publish_time_bj",
    "publish_date_bj", "creator_hash", "nickname", "public_ip_location",
    "liked_count_num", "collected_count_num", "comment_count_num", "share_count_num",
    "representative_score", "representative_rank_in_phase", "is_representative_sample",
    "is_marketing", "content_type", "collected_device", "collected_account", "collected_at_bj",
]

COMMENT_FIELDS = [
    "event_id", "phase_id", "note_id", "comment_id", "parent_comment_id",
    "comment_text", "comment_time", "comment_date_bj", "comment_like_count",
    "commenter_region", "commenter_anonymous_hash", "is_reply", "sub_comment_count",
    "note_is_representative_sample", "collected_device", "collected_account", "collected_at_bj",
]

ACTOR_FIELDS = [
    "actor_hash", "event_id", "phase_id", "actor_role", "comment_count_in_phase",
    "first_seen_time_bj", "regions_observed", "avg_comment_like", "max_comment_like",
    "dominant_comment_type", "sentiment_tendency", "knowledge_behavior_type", "sample_reason",
]

SUMMARY_FIELDS = [
    "phase_or_event_id", "notes", "representative_notes", "comments", "comments_with_region",
    "regions_count", "marketing_notes", "top_content_type",
]

COLLECTION_URL_FIELDS = [
    "event_id", "event_name", "phase_id", "phase_name", "note_id", "note_url",
    "representative_rank_in_phase", "representative_score",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export unified XHS research CSVs.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--representative-notes-per-phase", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = read_manifest(args.manifest)
    notes, notes_by_id = merge_notes(args.run_dir, manifest)
    mark_representative_notes(notes, args.representative_notes_per_phase)
    comments = merge_comments(args.run_dir, notes_by_id)
    actors = build_actor_seed(comments)
    summary = build_summary(notes, comments)
    collection_urls = build_representative_collection_urls(notes)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "notes_unified.csv", notes, NOTE_FIELDS)
    write_csv(args.output_dir / "comments_unified.csv", comments, COMMENT_FIELDS)
    write_csv(
        args.output_dir / "representative_notes.csv",
        [row for row in notes if row.get("is_representative_sample")],
        NOTE_FIELDS,
    )
    write_csv(args.output_dir / "actor_commenter_seed.csv", actors, ACTOR_FIELDS)
    write_csv(args.output_dir / "event_phase_summary.csv", summary, SUMMARY_FIELDS)
    write_csv(args.output_dir / "representative_note_urls_for_collection.csv", collection_urls, COLLECTION_URL_FIELDS)
    print(f"notes={len(notes)} comments={len(comments)} actors={len(actors)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
