#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe public commenter profiles without persisting raw identity links.

The script temporarily uses comment payload user_id/xsec_token values in memory
to read public profile/post information, then writes only anonymized hashes and
research-safe aggregate/post-text fields.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MEDIA_CRAWLER_DIR = ROOT / "MediaCrawler"
sys.path.insert(0, str(MEDIA_CRAWLER_DIR))

import config  # noqa: E402
from media_platform.xhs.core import XiaoHongShuCrawler  # noqa: E402
from media_platform.xhs.help import parse_note_info_from_note_url  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402
from tools.user_hash import anonymize_user_id  # noqa: E402


BJ = timezone(timedelta(hours=8))
AI_KEYWORDS = (
    "AI", "AIGC", "Agent", "API", "ChatGPT", "GPT", "OpenAI", "Claude", "DeepSeek",
    "Qwen", "通义", "通义千问", "豆包", "Kimi", "大模型", "模型", "智能体", "编程",
    "测评", "教程", "提示词", "办公", "PPT", "论文", "写作",
)


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


def safe_text(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit]


def parse_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    multiplier = 1.0
    if text.endswith("万"):
        multiplier = 10000.0
        text = text[:-1]
    elif text.lower().endswith("k"):
        multiplier = 1000.0
        text = text[:-1]
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return int(float(match.group(0)) * multiplier) if match else 0


def bucket_count(value: int) -> str:
    if value <= 0:
        return "0"
    if value <= 10:
        return "1-10"
    if value <= 50:
        return "11-50"
    if value <= 100:
        return "51-100"
    if value <= 500:
        return "101-500"
    return "500+"


def stable_hash(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def extract_text(item: dict[str, Any]) -> str:
    return safe_text(
        item.get("display_title")
        or item.get("title")
        or item.get("desc")
        or item.get("content")
        or ""
    )


def extract_keywords(text: str) -> list[str]:
    found: list[str] = []
    for tag in re.findall(r"#([^#\s\[\]]{1,30})", text):
        if tag not in found:
            found.append(tag)
    lowered = text.lower()
    for keyword in AI_KEYWORDS:
        if keyword.lower() in lowered and keyword not in found:
            found.append(keyword)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{1,30}", text):
        if token not in found:
            found.append(token)
    return found[:30]


def is_ai_related(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in AI_KEYWORDS)


def post_type(item: dict[str, Any]) -> str:
    return safe_text(item.get("type") or item.get("note_type") or item.get("model_type") or "unknown", 40)


def load_note_rows(path: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                item = json.loads(line)
                note_url = str(item.get("note_url") or item.get("note_url_public") or "").strip()
                if not note_url or note_url in seen:
                    continue
                seen.add(note_url)
                rows.append({
                    "event_id": str(item.get("event_id") or "").strip(),
                    "phase_id": str(item.get("phase_id") or "").strip(),
                    "note_id": str(item.get("note_id") or "").strip(),
                    "note_url": note_url,
                })
                if limit and len(rows) >= limit:
                    break
        return rows

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            note_url = str(row.get("note_url") or row.get("note_url_access") or row.get("note_url_public") or "").strip()
            if not note_url or note_url in seen:
                continue
            seen.add(note_url)
            rows.append({
                "event_id": str(row.get("event_id") or "").strip(),
                "phase_id": str(row.get("phase_id") or "").strip(),
                "note_id": str(row.get("note_id") or "").strip(),
                "note_url": note_url,
            })
            if limit and len(rows) >= limit:
                break
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_probe(args: argparse.Namespace) -> int:
    config.PLATFORM = "xhs"
    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = True
    config.CDP_HEADLESS = False
    config.HEADLESS = False
    config.AUTO_CLOSE_BROWSER = False
    config.BROWSER_LAUNCH_TIMEOUT = args.browser_timeout
    config.CRAWLER_MAX_SLEEP_SEC = args.sleep
    config.CRAWLER_MAX_NOTES_COUNT = args.public_post_limit
    config.MAX_CONCURRENCY_NUM = 1
    config.ENABLE_GET_COMMENTS = True
    config.ENABLE_GET_SUB_COMMENTS = False

    output_dir = args.output_dir
    csv_dir = output_dir / "csv"
    notes = load_note_rows(args.notes_file, args.limit_notes)
    if not notes:
        raise RuntimeError(f"No note URLs found in {args.notes_file}")

    commenter_sources: dict[str, dict[str, Any]] = {}
    commenter_comments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profile_rows: list[dict[str, Any]] = []
    post_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    crawler = XiaoHongShuCrawler()
    async with async_playwright() as playwright:
        crawler.browser_context = await crawler.launch_browser_with_cdp(
            playwright,
            playwright_proxy=None,
            user_agent=crawler.user_agent,
            headless=False,
        )
        pages = crawler.browser_context.pages
        crawler.context_page = pages[0] if pages else await crawler.browser_context.new_page()
        try:
            await crawler.context_page.goto(crawler.index_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            errors.append(f"index_goto_warning:{type(exc).__name__}:{exc}")

        crawler.xhs_client = await crawler.create_xhs_client(httpx_proxy=None)
        if not await crawler.xhs_client.pong():
            write_json(output_dir / "commenter_profile_report.json", {
                "generated_at": int(time.time()),
                "login_ok": False,
                "errors": errors,
            })
            return 2

        for note in notes:
            note_info = parse_note_info_from_note_url(note["note_url"])
            event_id = note.get("event_id") or ""
            phase_id = note.get("phase_id") or ""
            try:
                comments = await crawler.xhs_client.get_note_all_comments(
                    note_id=note_info.note_id,
                    xsec_token=note_info.xsec_token,
                    crawl_interval=args.sleep,
                    max_count=args.comments_per_note,
                )
            except Exception as exc:
                errors.append(f"comments_failed:{note_info.note_id}:{type(exc).__name__}:{exc}")
                await asyncio.sleep(args.sleep)
                continue

            for comment in comments:
                if not isinstance(comment, dict):
                    continue
                user = comment.get("user_info") or {}
                if not isinstance(user, dict):
                    continue
                user_id = user.get("user_id") or user.get("id")
                if not user_id:
                    continue
                actor_hash = anonymize_user_id(user_id)
                comment_time, _ = bj_time(comment.get("create_time"))
                commenter_comments[actor_hash].append({
                    "event_id": event_id,
                    "phase_id": phase_id,
                    "note_id": note_info.note_id,
                    "comment_id": comment.get("id") or "",
                    "comment_time": comment_time,
                    "comment_like_count": parse_count(comment.get("like_count")),
                    "commenter_region": comment.get("ip_location") or user.get("ip_location") or "",
                })
                if actor_hash not in commenter_sources:
                    commenter_sources[actor_hash] = {
                        "user_id": str(user_id),
                        "xsec_token": str(user.get("xsec_token") or ""),
                        "xsec_source": str(user.get("xsec_source") or "pc_search"),
                    }
                if args.commenter_limit and len(commenter_sources) >= args.commenter_limit:
                    break
            if args.commenter_limit and len(commenter_sources) >= args.commenter_limit:
                break

        for index, (actor_hash, source) in enumerate(commenter_sources.items(), start=1):
            comments = commenter_comments.get(actor_hash, [])
            event_ids = sorted({row["event_id"] for row in comments if row.get("event_id")})
            phase_ids = sorted({row["phase_id"] for row in comments if row.get("phase_id")})
            regions = sorted({row["commenter_region"] for row in comments if row.get("commenter_region")})
            first_seen = sorted(row["comment_time"] for row in comments if row.get("comment_time"))
            profile_available = False
            creator_notes: list[dict[str, Any]] = []
            try:
                profile = await crawler.xhs_client.get_creator_info(
                    user_id=source["user_id"],
                    xsec_token=source["xsec_token"],
                    xsec_source=source["xsec_source"],
                )
                profile_available = bool(profile)
            except Exception as exc:
                errors.append(f"profile_failed:{actor_hash}:{type(exc).__name__}:{exc}")
            try:
                res = await crawler.xhs_client.get_notes_by_creator(
                    creator=source["user_id"],
                    cursor="",
                    page_size=args.public_post_limit,
                    xsec_token=source["xsec_token"],
                    xsec_source=source["xsec_source"] or "pc_search",
                )
                if isinstance(res, dict):
                    raw_notes = res.get("notes") or []
                    if isinstance(raw_notes, list):
                        creator_notes = [item for item in raw_notes if isinstance(item, dict)]
            except Exception as exc:
                errors.append(f"posts_failed:{actor_hash}:{type(exc).__name__}:{exc}")

            type_counts: Counter[str] = Counter()
            keyword_counts: Counter[str] = Counter()
            ai_count = 0
            for item in creator_notes[: args.public_post_limit]:
                text = extract_text(item)
                keywords = extract_keywords(text)
                ai_related = is_ai_related(text)
                ai_count += int(ai_related)
                ptype = post_type(item)
                type_counts[ptype] += 1
                keyword_counts.update(keywords)
                publish_time, publish_date = bj_time(item.get("time"))
                interact = item.get("interact_info") or {}
                post_rows.append({
                    "commenter_anonymous_hash": actor_hash,
                    "event_id": "|".join(event_ids),
                    "phase_id": "|".join(phase_ids),
                    "public_post_hash": stable_hash(item.get("note_id") or item.get("id")),
                    "post_type": ptype,
                    "post_text": text,
                    "post_keywords": "|".join(keywords),
                    "post_publish_time_bj": publish_time,
                    "post_publish_date_bj": publish_date,
                    "post_like_count_num": parse_count(interact.get("liked_count") or item.get("liked_count")),
                    "post_comment_count_num": parse_count(interact.get("comment_count") or item.get("comment_count")),
                    "post_collect_count_num": parse_count(interact.get("collected_count") or item.get("collected_count")),
                    "is_ai_related": ai_related,
                    "collected_at_bj": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
                })

            profile_rows.append({
                "commenter_anonymous_hash": actor_hash,
                "event_id": "|".join(event_ids),
                "phase_id": "|".join(phase_ids),
                "source_comment_count": len(comments),
                "source_note_count": len({row["note_id"] for row in comments if row.get("note_id")}),
                "first_comment_time_bj": first_seen[0] if first_seen else "",
                "regions_observed": "|".join(regions),
                "profile_accessible": profile_available,
                "public_post_count": len(creator_notes),
                "public_post_count_bucket": bucket_count(len(creator_notes)),
                "sampled_public_posts_count": min(len(creator_notes), args.public_post_limit),
                "post_type_distribution": "|".join(f"{key}:{value}" for key, value in type_counts.items()),
                "top_profile_keywords": "|".join(key for key, _ in keyword_counts.most_common(30)),
                "ai_related_post_ratio": round(ai_count / len(creator_notes), 4) if creator_notes else 0,
                "profile_collected_device": args.device_id,
                "profile_collected_account": args.account_id,
                "profile_collected_at_bj": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
            })
            if index < len(commenter_sources):
                await asyncio.sleep(args.sleep)

    write_csv(csv_dir / "commenter_profile_summary.csv", profile_rows, COMMENTER_PROFILE_FIELDS)
    write_csv(csv_dir / "commenter_public_posts_sample.csv", post_rows, COMMENTER_POST_FIELDS)
    write_json(output_dir / "commenter_profile_report.json", {
        "generated_at": int(time.time()),
        "login_ok": True,
        "notes_scanned": len(notes),
        "commenters_found": len(commenter_sources),
        "commenter_profiles_written": len(profile_rows),
        "public_post_rows_written": len(post_rows),
        "errors": errors[:200],
    })
    return 0


COMMENTER_PROFILE_FIELDS = [
    "commenter_anonymous_hash", "event_id", "phase_id", "source_comment_count",
    "source_note_count", "first_comment_time_bj", "regions_observed", "profile_accessible",
    "public_post_count", "public_post_count_bucket", "sampled_public_posts_count",
    "post_type_distribution", "top_profile_keywords", "ai_related_post_ratio",
    "profile_collected_device", "profile_collected_account", "profile_collected_at_bj",
]

COMMENTER_POST_FIELDS = [
    "commenter_anonymous_hash", "event_id", "phase_id", "public_post_hash", "post_type",
    "post_text", "post_keywords", "post_publish_time_bj", "post_publish_date_bj",
    "post_like_count_num", "post_comment_count_num", "post_collect_count_num",
    "is_ai_related", "collected_at_bj",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe public XHS commenter profiles safely.")
    parser.add_argument("--notes-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device-id", default="")
    parser.add_argument("--account-id", default="")
    parser.add_argument("--limit-notes", type=int, default=0)
    parser.add_argument("--comments-per-note", type=int, default=10000)
    parser.add_argument("--commenter-limit", type=int, default=0)
    parser.add_argument("--public-post-limit", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--browser-timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    return asyncio.run(run_probe(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
