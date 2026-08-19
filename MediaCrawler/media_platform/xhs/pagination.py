from __future__ import annotations

import json
import os
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import config


BJ = timezone(timedelta(hours=8))


def collection_context() -> dict[str, str]:
    mappings = {
        "collection_egress_region": "XHS_COLLECTION_EGRESS_REGION",
        "collection_egress_id": "XHS_COLLECTION_EGRESS_ID",
        "collection_account_id": "XHS_COLLECTION_ACCOUNT_ID",
        "collection_cdp_port": "XHS_CDP_DEBUG_PORT",
    }
    return {
        field: value
        for field, env_name in mappings.items()
        if (value := os.getenv(env_name, "").strip())
    }


def parse_boundary_ms(value: str, *, end_of_day: bool = False) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.strptime(text, "%Y-%m-%d").date()
    boundary = datetime.combine(
        parsed,
        time.max if end_of_day else time.min,
        tzinfo=BJ,
    )
    return int(boundary.timestamp() * 1000)


def timestamp_ms(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number < 10_000_000_000:
        number *= 1000
    return int(number)


def search_item_publish_time_ms(
    item: dict[str, Any],
    *,
    reference: datetime | None = None,
) -> int | None:
    """Parse the coarse publish-time label exposed on an XHS search card."""
    card = item.get("note_card") if isinstance(item.get("note_card"), dict) else {}
    tags = card.get("corner_tag_info") if isinstance(card.get("corner_tag_info"), list) else []
    label = ""
    for tag in tags:
        if isinstance(tag, dict) and tag.get("type") == "publish_time":
            label = str(tag.get("text") or "").strip()
            break
    if not label:
        return None

    now = reference or datetime.now(BJ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BJ)
    else:
        now = now.astimezone(BJ)

    if label == "刚刚":
        return int(now.timestamp() * 1000)

    relative_patterns = (
        (r"^(\d+)分钟前$", "minutes"),
        (r"^(\d+)小时前$", "hours"),
        (r"^(\d+)天前$", "days"),
    )
    for pattern, unit in relative_patterns:
        match = re.match(pattern, label)
        if match:
            value = int(match.group(1))
            return int((now - timedelta(**{unit: value})).timestamp() * 1000)

    day_match = re.match(r"^(昨天|前天)(?:\s+(\d{1,2}):(\d{2}))?$", label)
    if day_match:
        days = 1 if day_match.group(1) == "昨天" else 2
        hour = int(day_match.group(2) or 0)
        minute = int(day_match.group(3) or 0)
        parsed = datetime.combine(
            (now - timedelta(days=days)).date(),
            time(hour=hour, minute=minute),
            tzinfo=BJ,
        )
        return int(parsed.timestamp() * 1000)

    absolute_match = re.match(
        r"^(?:(\d{4})[-/])?(\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?$",
        label,
    )
    if absolute_match:
        year = int(absolute_match.group(1) or now.year)
        month = int(absolute_match.group(2))
        day = int(absolute_match.group(3))
        hour = int(absolute_match.group(4) or 0)
        minute = int(absolute_match.group(5) or 0)
        try:
            parsed = datetime(year, month, day, hour, minute, tzinfo=BJ)
        except ValueError:
            return None
        if absolute_match.group(1) is None and parsed > now + timedelta(days=1):
            parsed = parsed.replace(year=year - 1)
        return int(parsed.timestamp() * 1000)
    return None


def classify_page_times(
    note_details: list[dict[str, Any]],
    window_start_ms: int | None,
    window_end_ms: int | None,
) -> dict[str, int | bool]:
    times = [timestamp_ms(row.get("time")) for row in note_details]
    known = [value for value in times if value is not None]
    older = sum(1 for value in known if window_start_ms is not None and value < window_start_ms)
    newer = sum(1 for value in known if window_end_ms is not None and value > window_end_ms)
    in_window = sum(
        1
        for value in known
        if (window_start_ms is None or value >= window_start_ms)
        and (window_end_ms is None or value <= window_end_ms)
    )
    return {
        "known_time_rows": len(known),
        "missing_time_rows": len(times) - len(known),
        "older_rows": older,
        "newer_rows": newer,
        "in_window_rows": in_window,
        "all_known_rows_older": bool(known) and older == len(known),
    }


def append_quality_status(filename: str, payload: dict[str, Any]) -> Path:
    base = Path(config.SAVE_DATA_PATH or ".") / "xhs" / "quality"
    base.mkdir(parents=True, exist_ok=True)
    path = base / filename
    enriched = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
        **collection_context(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(enriched, ensure_ascii=False) + "\n")
    return path


def append_raw_search_result(payload: dict[str, Any]) -> Path:
    base = Path(config.SAVE_DATA_PATH or ".") / "xhs" / "raw"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "search_results.jsonl"
    enriched = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
        **collection_context(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(enriched, ensure_ascii=False) + "\n")
    return path


def load_existing_content_note_ids() -> set[str]:
    """Return note ids already persisted in the current search output."""
    base = Path(config.SAVE_DATA_PATH or ".") / "xhs" / "jsonl"
    note_ids: set[str] = set()
    for path in sorted(base.glob("*contents*.jsonl")):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    note_id = str(row.get("note_id") or row.get("id") or "").strip()
                    if note_id:
                        note_ids.add(note_id)
        except OSError:
            continue
    return note_ids


def take_detail_budget(
    items: list[dict[str, Any]],
    used: int,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split detail candidates into this session's work and deferred work."""
    if limit <= 0:
        return items, []
    remaining = max(0, limit - used)
    return items[:remaining], items[remaining:]


def cursor_stop_reason(current_cursor: str, next_cursor: str, has_more: bool, seen: set[str]) -> str:
    if not has_more:
        return "endpoint_exhausted"
    if not next_cursor:
        return "missing_next_cursor"
    if next_cursor == current_cursor or next_cursor in seen:
        return "repeated_cursor"
    return ""


def search_stop_decision(
    *,
    has_more: bool,
    all_results: bool,
    consecutive_old_pages: int,
    old_page_stop_count: int,
    page: int,
    max_pages: int,
) -> tuple[str, bool]:
    if not has_more:
        return "endpoint_exhausted", True
    if all_results and consecutive_old_pages >= old_page_stop_count:
        return "window_exhausted", True
    if all_results and page >= max_pages:
        return "max_pages_guard", False
    return "", False


def search_page_checkpoint_decision(
    *,
    page: int,
    start_page: int,
    session_limit: int,
    terminal_stop_reason: str,
    overlap_pages: int = 0,
) -> tuple[str, int]:
    """Return a resumable checkpoint only when no terminal condition won."""
    if terminal_stop_reason or session_limit <= 0:
        return "", 0
    successful_pages = page - start_page + 1
    if successful_pages >= session_limit:
        resume_page = max(start_page, page + 1 - max(0, overlap_pages))
        return "session_page_limit", resume_page
    return "", 0
