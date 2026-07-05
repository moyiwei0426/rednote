#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight XHS author/profile capability probe.

The probe intentionally writes anonymized research rows only. It uses raw user ids
in memory to test public creator endpoints, but persists hashes instead of
profile URLs, raw user ids, avatar URLs, or raw nicknames.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MEDIA_CRAWLER_DIR = ROOT / "MediaCrawler"
sys.path.insert(0, str(MEDIA_CRAWLER_DIR))

import config  # noqa: E402
from media_platform.xhs.core import XiaoHongShuCrawler  # noqa: E402
from media_platform.xhs.help import parse_note_info_from_note_url  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402
from tools.user_hash import anonymize_user_id, mask_nickname  # noqa: E402


PIIISH_KEYS = {
    "user_id",
    "userid",
    "id",
    "nickname",
    "nick_name",
    "avatar",
    "image",
    "images",
    "url",
    "link",
    "qrcode",
    "qr_code",
    "token",
    "xsec",
    "desc",
    "description",
}


def _field_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _flatten_keys(obj: Any, prefix: str = "") -> dict[str, str]:
    fields: dict[str, str] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            fields[path] = _field_type(value)
            if isinstance(value, dict):
                fields.update(_flatten_keys(value, path))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                fields.update(_flatten_keys(value[0], f"{path}[]"))
    return fields


def _is_sensitive_path(path: str) -> bool:
    lower = path.lower()
    return any(key in lower for key in PIIISH_KEYS)


def _safe_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    text = str(value)
    if len(text) > 80:
        return text[:77] + "..."
    return text


def _pick_count_value(data: dict[str, Any], names: list[str]) -> str:
    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in names and not isinstance(value, (dict, list)):
                    return value
            for value in obj.values():
                found = walk(value)
                if found not in (None, ""):
                    return found
        return None

    return _safe_scalar(walk(data))


def _extract_profile_interactions(profile: dict[str, Any] | None) -> dict[str, str]:
    result = {
        "profile_following_count": "",
        "profile_follower_count": "",
        "profile_liked_collected_count": "",
    }
    if not isinstance(profile, dict):
        return result
    interactions = profile.get("interactions") or []
    if not isinstance(interactions, list):
        return result
    for item in interactions:
        if not isinstance(item, dict):
            continue
        label = str(item.get("name") or item.get("type") or "")
        count = _safe_scalar(item.get("count") or item.get("i18nCount"))
        if not count:
            continue
        if "关注" in label or "follows" in label.lower() or label.lower() in {"follow", "following"}:
            result["profile_following_count"] = count
        elif "粉丝" in label or "fans" in label.lower() or "follower" in label.lower():
            result["profile_follower_count"] = count
        elif "获赞" in label or "收藏" in label or "interaction" in label.lower() or "liked" in label.lower():
            result["profile_liked_collected_count"] = count
    return result


def _load_note_urls(path: Path, limit: int) -> list[str]:
    urls: list[str] = []
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                url = (row.get("note_url") or "").strip()
                if not url or url in urls:
                    continue
                urls.append(url)
                if len(urls) >= limit:
                    break
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                url = (row.get("note_url") or "").strip()
                if not url:
                    continue
                if url in urls:
                    continue
                urls.append(url)
                if len(urls) >= limit:
                    break
    return urls


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _get_note_detail(client: Any, note_url: str) -> dict[str, Any] | None:
    note_info = parse_note_info_from_note_url(note_url)
    note = None
    try:
        note = await client.get_note_by_id(
            note_info.note_id,
            note_info.xsec_source,
            note_info.xsec_token,
        )
    except Exception:
        note = None
    if not note:
        try:
            note = await client.get_note_by_id_from_html(
                note_info.note_id,
                note_info.xsec_source,
                note_info.xsec_token,
                enable_cookie=True,
            )
        except Exception:
            note = None
    if not note:
        return None
    note["xsec_token"] = note_info.xsec_token
    note["xsec_source"] = note_info.xsec_source
    return note


async def run_probe(args: argparse.Namespace) -> int:
    config.PLATFORM = "xhs"
    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = True
    config.CDP_HEADLESS = False
    config.HEADLESS = False
    config.AUTO_CLOSE_BROWSER = False
    config.BROWSER_LAUNCH_TIMEOUT = args.browser_timeout
    config.CRAWLER_MAX_SLEEP_SEC = args.sleep
    config.CRAWLER_MAX_NOTES_COUNT = args.creator_note_limit
    config.MAX_CONCURRENCY_NUM = 1
    config.ENABLE_GET_COMMENTS = False

    output_dir = Path(args.output_dir)
    csv_dir = output_dir / "csv"
    raw_dir = output_dir / "raw_redacted"
    csv_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    note_urls = _load_note_urls(Path(args.notes_csv), args.limit_notes)
    if not note_urls:
        raise RuntimeError(f"No note_url found in {args.notes_csv}")

    field_counter: dict[str, Counter[str]] = defaultdict(Counter)
    author_rows: list[dict[str, Any]] = []
    post_rows: list[dict[str, Any]] = []
    comment_user_rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "generated_at": int(time.time()),
        "notes_csv": args.notes_csv,
        "limit_notes": args.limit_notes,
        "creator_note_limit": args.creator_note_limit,
        "comment_probe_limit": args.comment_probe_limit,
        "login_ok": False,
        "errors": [],
    }

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
        except Exception as exc:  # page navigation can fail while cookies are still usable
            report["errors"].append(f"index_goto_warning:{type(exc).__name__}:{exc}")

        crawler.xhs_client = await crawler.create_xhs_client(httpx_proxy=None)
        report["login_ok"] = bool(await crawler.xhs_client.pong())
        if not report["login_ok"]:
            _write_json(output_dir / "author_probe_report.json", report)
            return 2

        seen_author_hashes: set[str] = set()
        for note_url in note_urls:
            try:
                note = await _get_note_detail(crawler.xhs_client, note_url)
            except Exception as exc:
                report["errors"].append(f"note_detail_failed:{note_url}:{type(exc).__name__}:{exc}")
                await asyncio.sleep(args.sleep)
                continue

            if not note:
                continue

            for path, typ in _flatten_keys(note).items():
                field_counter[f"note_detail.{path}"][typ] += 1

            user = note.get("user") or note.get("user_info") or {}
            if not isinstance(user, dict):
                user = {}
            for path, typ in _flatten_keys(user).items():
                field_counter[f"note_author_user.{path}"][typ] += 1

            user_id = user.get("user_id") or user.get("id")
            author_hash = anonymize_user_id(user_id)
            if not user_id or author_hash in seen_author_hashes:
                continue
            seen_author_hashes.add(author_hash)

            creator_profile: dict[str, Any] | None = None
            try:
                creator_profile = await crawler.xhs_client.get_creator_info(
                    user_id=str(user_id),
                    xsec_token=str(user.get("xsec_token") or ""),
                    xsec_source=str(user.get("xsec_source") or "pc_search"),
                )
            except Exception as exc:
                report["errors"].append(f"creator_profile_failed:{author_hash}:{type(exc).__name__}:{exc}")
            if isinstance(creator_profile, dict):
                for path, typ in _flatten_keys(creator_profile).items():
                    field_counter[f"creator_profile.{path}"][typ] += 1
                _write_json(raw_dir / f"creator_profile_fields_{author_hash}.json", {
                    key: _field_type(value) for key, value in creator_profile.items()
                })

            creator_notes_res: dict[str, Any] | None = None
            try:
                creator_notes_res = await crawler.xhs_client.get_notes_by_creator(
                    creator=str(user_id),
                    cursor="",
                    page_size=args.creator_note_limit,
                    xsec_token=str(user.get("xsec_token") or ""),
                    xsec_source=str(user.get("xsec_source") or "pc_search"),
                )
            except Exception as exc:
                report["errors"].append(f"creator_notes_failed:{author_hash}:{type(exc).__name__}:{exc}")

            creator_notes = []
            if isinstance(creator_notes_res, dict):
                for path, typ in _flatten_keys(creator_notes_res).items():
                    field_counter[f"creator_notes_page.{path}"][typ] += 1
                creator_notes = creator_notes_res.get("notes") or []
                if not isinstance(creator_notes, list):
                    creator_notes = []

            profile_interactions = _extract_profile_interactions(creator_profile)
            author_rows.append({
                "author_hash": author_hash,
                "source_note_id": note.get("note_id", ""),
                "source_note_title": _safe_scalar(note.get("title") or note.get("desc", "")),
                "source_note_time": _safe_scalar(note.get("time")),
                "source_note_like_count": _safe_scalar((note.get("interact_info") or {}).get("liked_count")),
                "source_note_comment_count": _safe_scalar((note.get("interact_info") or {}).get("comment_count")),
                "masked_nickname": mask_nickname(user.get("nickname")),
                "note_author_public_location": _safe_scalar(
                    user.get("ip_location") or user.get("location") or note.get("ip_location") or ""
                ),
                "profile_available": bool(creator_profile),
                "profile_fans": profile_interactions["profile_follower_count"]
                or _pick_count_value(creator_profile or {}, ["fans", "fans_count", "followers", "follower_count"]),
                "profile_follows": profile_interactions["profile_following_count"]
                or _pick_count_value(creator_profile or {}, ["follows", "follow_count", "following_count"]),
                "profile_interaction": profile_interactions["profile_liked_collected_count"]
                or _pick_count_value(creator_profile or {}, ["interaction", "interaction_count", "liked_count"]),
                "profile_notes_count": _pick_count_value(creator_profile or {}, ["notes", "note_count", "posted_count"]),
                "creator_notes_page_available": bool(creator_notes_res),
                "creator_notes_returned": len(creator_notes),
                "creator_notes_has_more": _safe_scalar((creator_notes_res or {}).get("has_more")),
            })

            for item in creator_notes[: args.creator_note_limit]:
                if not isinstance(item, dict):
                    continue
                for path, typ in _flatten_keys(item).items():
                    field_counter[f"creator_note_item.{path}"][typ] += 1
                post_rows.append({
                    "author_hash": author_hash,
                    "note_id": item.get("note_id") or item.get("id") or "",
                    "display_title": _safe_scalar(item.get("display_title") or item.get("title") or item.get("desc") or ""),
                    "type": _safe_scalar(item.get("type")),
                    "liked_count": _safe_scalar((item.get("interact_info") or {}).get("liked_count") or item.get("liked_count")),
                    "time": _safe_scalar(item.get("time")),
                    "xsec_token_available": bool(item.get("xsec_token")),
                })

            if args.comment_probe_limit > 0:
                try:
                    comments_res = await crawler.xhs_client.get_note_comments(
                        note_id=str(note.get("note_id")),
                        xsec_token=str(note.get("xsec_token")),
                    )
                    comments = (comments_res or {}).get("comments") or []
                    for comment in comments[: args.comment_probe_limit]:
                        if not isinstance(comment, dict):
                            continue
                        for path, typ in _flatten_keys(comment).items():
                            field_counter[f"comment_item.{path}"][typ] += 1
                        c_user = comment.get("user_info") or {}
                        if isinstance(c_user, dict):
                            for path, typ in _flatten_keys(c_user).items():
                                field_counter[f"comment_user_info.{path}"][typ] += 1
                        comment_user_rows.append({
                            "source_note_id": note.get("note_id", ""),
                            "comment_id": comment.get("id", ""),
                            "commenter_hash": anonymize_user_id(c_user.get("user_id") if isinstance(c_user, dict) else ""),
                            "masked_nickname": mask_nickname(c_user.get("nickname") if isinstance(c_user, dict) else ""),
                            "comment_like_count": _safe_scalar(comment.get("like_count")),
                            "comment_time": _safe_scalar(comment.get("create_time")),
                            "comment_public_location": _safe_scalar(
                                comment.get("ip_location") or (c_user.get("ip_location") if isinstance(c_user, dict) else "") or ""
                            ),
                            "comment_text_len": len(str(comment.get("content") or "")),
                            "commenter_profile_id_available_in_payload": bool(
                                isinstance(c_user, dict) and (c_user.get("user_id") or c_user.get("id"))
                            ),
                            "commenter_xsec_token_available_in_payload": bool(
                                isinstance(c_user, dict) and c_user.get("xsec_token")
                            ),
                        })
                except Exception as exc:
                    report["errors"].append(f"comments_probe_failed:{author_hash}:{type(exc).__name__}:{exc}")

            await asyncio.sleep(args.sleep)

    field_rows = []
    for path, counter in sorted(field_counter.items()):
        field_rows.append({
            "field_path": path,
            "observed_count": sum(counter.values()),
            "types": "|".join(f"{typ}:{count}" for typ, count in counter.items()),
            "sensitive_or_identifier_like": _is_sensitive_path(path),
            "recommended_for_agent_sim": not _is_sensitive_path(path),
        })

    _write_csv(csv_dir / "author_probe_summary.csv", author_rows)
    _write_csv(csv_dir / "author_public_posts_sample.csv", post_rows)
    _write_csv(csv_dir / "comment_user_payload_sample.csv", comment_user_rows)
    _write_csv(csv_dir / "field_catalog.csv", field_rows)

    report.update({
        "authors_probed": len(author_rows),
        "creator_posts_sample_rows": len(post_rows),
        "comment_user_sample_rows": len(comment_user_rows),
        "field_paths_observed": len(field_rows),
        "outputs": {
            "author_summary": str(csv_dir / "author_probe_summary.csv"),
            "author_public_posts": str(csv_dir / "author_public_posts_sample.csv"),
            "comment_user_payload": str(csv_dir / "comment_user_payload_sample.csv"),
            "field_catalog": str(csv_dir / "field_catalog.csv"),
        },
    })
    _write_json(output_dir / "author_probe_report.json", report)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe XHS author/profile/public-post fields.")
    parser.add_argument(
        "--notes-csv",
        default="runs/xhs_ai_hot_30_20260424_20260703/csv/ai_hot_30_notes_merged.csv",
    )
    parser.add_argument("--output-dir", default="runs/xhs_author_probe_20260704")
    parser.add_argument("--limit-notes", type=int, default=3)
    parser.add_argument("--creator-note-limit", type=int, default=5)
    parser.add_argument("--comment-probe-limit", type=int, default=5)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--browser-timeout", type=int, default=20)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_probe(parse_args())))
