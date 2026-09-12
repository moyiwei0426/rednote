#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run XHS core-event collection batches on multiple devices.

This runner standardizes event selection, output paths, batch metadata, and the
low-frequency collection strategy for the Xiaohongshu/MediaCrawler workflow.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
MEDIA_CRAWLER_DIR = ROOT / "MediaCrawler"
DEFAULT_MANIFEST = ROOT / "configs" / "xhs_core_events_manifest.csv"
DEFAULT_RUN_ROOT = ROOT / "runs" / "xhs_core_events"
CAPTCHA_MARKERS = (
    "CAPTCHA appeared",
    "Verifytype",
    "验证码",
    "滑块验证",
    "请完成验证",
)
LOGIN_FAILURE_MARKERS = (
    "Login state result: False",
    "登录已过期",
    "登录失效",
)
LOGIN_SUCCESS_MARKERS = (
    "Login state result: True",
    "Login status confirmed",
    "Login successful",
)
TRANSIENT_FAILURE_MARKERS = (
    "httpx.ConnectError",
    "httpx.ConnectTimeout",
    "httpx.RemoteProtocolError",
    "RemoteProtocolError",
    "Server disconnected without sending a response",
    "Page.goto: Timeout",
    "net::ERR_",
    "Connection reset by peer",
    "Command timeout after",
)
UNAVAILABLE_NOTE_MARKERS = (
    "Note not found or abnormal, code: -510000",
    "Note not found:",
)
DATA_LOG_MARKERS = (
    "[store.xhs.update_xhs_note]",
    "[store.xhs.update_xhs_note_comment]",
)


@dataclass
class EventRow:
    event_id: str
    event_name: str
    event_date: str
    country_group: str
    brand: str
    assigned_device: str
    priority: int
    collection_group: str
    enabled: bool
    keywords: list[str]
    analysis_window_start: str
    analysis_window_end: str
    notes_limit_recon: int
    notes_limit_deep: int
    comments_per_note_pilot: int
    comments_per_note_deep: int
    author_post_limit: int
    notes: str


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_device(value: str) -> str:
    value = value.strip().lower()
    value = value.removeprefix("device_")
    return value


def parse_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def load_manifest(path: Path) -> list[EventRow]:
    events: list[EventRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            keywords = [item.strip() for item in (row.get("keywords") or "").split("|") if item.strip()]
            enabled = (row.get("enabled") or "yes").strip().lower() in {"yes", "true", "1", "y"}
            events.append(
                EventRow(
                    event_id=(row.get("event_id") or "").strip(),
                    event_name=(row.get("event_name") or "").strip(),
                    event_date=(row.get("event_date") or "").strip(),
                    country_group=(row.get("country_group") or "").strip(),
                    brand=(row.get("brand") or "").strip(),
                    assigned_device=(row.get("assigned_device") or "").strip(),
                    priority=parse_int(row.get("priority") or "", 999),
                    collection_group=(row.get("collection_group") or "").strip(),
                    enabled=enabled,
                    keywords=keywords,
                    analysis_window_start=(row.get("analysis_window_start") or "").strip(),
                    analysis_window_end=(row.get("analysis_window_end") or "").strip(),
                    notes_limit_recon=parse_int(row.get("notes_limit_recon") or "", 20),
                    notes_limit_deep=parse_int(row.get("notes_limit_deep") or "", 80),
                    comments_per_note_pilot=parse_int(row.get("comments_per_note_pilot") or "", 30),
                    comments_per_note_deep=parse_int(row.get("comments_per_note_deep") or "", 80),
                    author_post_limit=parse_int(row.get("author_post_limit") or "", 20),
                    notes=(row.get("notes") or "").strip(),
                )
            )
    return sorted(events, key=lambda item: item.priority)


def slug_text(text: str) -> str:
    ascii_part = text.encode("ascii", "ignore").decode("ascii").lower()
    ascii_part = re.sub(r"[^a-z0-9]+", "_", ascii_part).strip("_")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{ascii_part or 'kw'}_{digest}"


def get_media_python_cmd() -> tuple[list[str], Path]:
    venv_python = MEDIA_CRAWLER_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return [str(venv_python)], MEDIA_CRAWLER_DIR
    if shutil.which("uv"):
        return ["uv", "run", "python"], MEDIA_CRAWLER_DIR
    return [sys.executable], ROOT


def build_media_command(
    event: EventRow,
    keyword: str,
    stage: str,
    output_dir: Path,
    args: argparse.Namespace,
    search_start_page: int = 1,
) -> tuple[list[str], Path]:
    python_cmd, python_cwd = get_media_python_cmd()
    if python_cwd == MEDIA_CRAWLER_DIR:
        main_path = "main.py"
        cwd = MEDIA_CRAWLER_DIR
    else:
        main_path = str(MEDIA_CRAWLER_DIR / "main.py")
        cwd = ROOT

    if stage == "recon":
        get_comment = "false"
        note_limit = args.notes_per_keyword or event.notes_limit_recon
        comments_limit = 0
    elif stage == "full-recon-comments":
        get_comment = "true"
        note_limit = args.notes_per_keyword or event.notes_limit_recon
        comments_limit = args.comments_per_note if args.comments_per_note is not None else 10000
    elif stage == "pilot-comments":
        get_comment = "true"
        note_limit = args.notes_per_keyword or event.notes_limit_recon
        comments_limit = args.comments_per_note if args.comments_per_note is not None else event.comments_per_note_pilot
    elif stage == "deep-comments":
        get_comment = "true"
        note_limit = args.notes_per_keyword or event.notes_limit_deep
        comments_limit = args.comments_per_note if args.comments_per_note is not None else event.comments_per_note_deep
    else:
        raise ValueError(f"Unsupported MediaCrawler stage: {stage}")

    cmd = [
        *python_cmd,
        main_path,
        "--platform",
        "xhs",
        "--lt",
        args.login_type,
        "--type",
        "search",
        "--keywords",
        keyword,
        "--start",
        str(max(1, search_start_page)),
        "--get_comment",
        get_comment,
        "--get_sub_comment",
        "false",
        "--headless",
        "false",
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(output_dir),
        "--crawler_max_notes_count",
        str(note_limit),
        "--max_comments_count_singlenotes",
        str(comments_limit),
        "--max_concurrency_num",
        str(args.max_concurrency),
        "--crawler_sleep_sec",
        str(args.page_sleep),
    ]
    if args.all_search_results:
        sort_value = "time_descending" if args.search_sort == "latest" else args.search_sort
        cmd.extend(
            [
                "--xhs_search_all_results",
                "true",
                "--xhs_search_sort",
                sort_value,
                "--xhs_search_window_start",
                args.window_start or event.analysis_window_start,
                "--xhs_search_window_end",
                args.window_end or event.analysis_window_end,
                "--xhs_search_max_pages",
                str(args.max_search_pages),
                "--xhs_search_page_cooldown_sec",
                str(args.search_page_cooldown),
                "--xhs_search_page_cooldown_every",
                str(args.search_page_cooldown_every),
                "--xhs_search_detail_session_limit",
                str(args.search_detail_session_limit),
                "--xhs_search_page_session_limit",
                str(args.search_page_session_limit),
            ]
        )
        if getattr(args, "search_card_only", False):
            cmd.extend(["--xhs_search_card_only", "true"])
    if getattr(args, "static_proxy_url", ""):
        cmd.extend(
            [
                "--enable_ip_proxy",
                "true",
                "--ip_proxy_provider_name",
                "static",
            ]
        )
    if getattr(args, "international_rednote", False):
        cmd.extend(["--xhs_international", "true"])
    return cmd, cwd


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_ledger(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "started_at",
        "finished_at",
        "device_id",
        "account_id",
        "stage",
        "event_id",
        "event_name",
        "keyword",
        "output_dir",
        "log_path",
        "returncode",
        "captcha_detected",
        "status",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def completed_output_dirs_from_ledger(path: Path, stage: str) -> set[str]:
    if not path.exists():
        return set()
    latest_rows: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            output_dir = row.get("output_dir")
            if row.get("stage") == stage and output_dir:
                latest_rows[output_dir] = row
    completed: set[str] = set()
    for output_dir, row in latest_rows.items():
        has_required_output = False
        output_path = Path(output_dir)
        if stage in {"selected-sub-comments", "selected-comments"}:
            has_required_output = comment_pagination_complete(output_path, stage)
            if not (output_path / "xhs" / "quality" / "comment_pagination_status.jsonl").exists():
                has_required_output = (
                    output_has_sub_comment_rows(output_path)
                    if stage == "selected-sub-comments"
                    else output_has_comment_rows(output_path)
                )
        elif stage == "selected-details":
            has_required_output = selected_detail_output_complete(output_path)
        else:
            has_required_output = output_has_jsonl_rows(output_path)
        if row.get("status") == "skipped_unavailable":
            # The platform confirmed that this note is no longer available.
            # Keep its log and ledger row as provenance, but never retry it on
            # a resumed queue.
            completed.add(output_dir)
        elif row.get("status") == "ok" and has_required_output:
            completed.add(output_dir)
    return completed


def completed_search_keys_from_ledger(path: Path, stage: str) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    completed: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            output_dir = row.get("output_dir")
            if (
                row.get("stage") == stage
                and row.get("status") == "ok"
                and output_dir
                and (
                    output_has_jsonl_rows(Path(output_dir))
                    or latest_search_pagination_status(Path(output_dir)).get("complete") is True
                )
            ):
                event_id = (row.get("event_id") or "").strip()
                keyword = (row.get("keyword") or "").strip()
                if event_id and keyword:
                    completed.add((event_id, keyword))
    return completed


def output_has_jsonl_rows(output_dir: Path) -> bool:
    for path in output_dir.glob("xhs/jsonl/*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                if any(line.strip() for line in fh):
                    return True
        except OSError:
            continue
    return False


def output_content_note_ids(output_dir: Path) -> set[str]:
    note_ids: set[str] = set()
    for path in output_dir.glob("xhs/jsonl/*contents*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    note_id = str(row.get("note_id") or "").strip()
                    if note_id:
                        note_ids.add(note_id)
        except OSError:
            continue
    return note_ids


def selected_detail_output_complete(output_dir: Path) -> bool:
    meta_path = output_dir / "batch_meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    expected = {
        str(row.get("note_id") or "").strip()
        for row in meta.get("selected_notes", [])
        if str(row.get("note_id") or "").strip()
    }
    return bool(expected) and expected.issubset(output_content_note_ids(output_dir))


def output_has_search_rows(output_dir: Path) -> bool:
    """Accept either detail JSONL or the raw search-card stream as search output."""
    if output_has_jsonl_rows(output_dir):
        return True
    path = output_dir / "xhs" / "raw" / "search_results.jsonl"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return any(line.strip() for line in fh)
    except OSError:
        return False


def output_has_any_jsonl_rows(output_dir: Path) -> bool:
    for path in output_dir.glob("xhs/**/*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                if any(line.strip() for line in fh):
                    return True
        except OSError:
            continue
    return False


def output_has_comment_rows(output_dir: Path) -> bool:
    for path in output_dir.glob("xhs/jsonl/*comments*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                return any(line.strip() for line in fh)
        except OSError:
            continue
    return False


def output_has_sub_comment_rows(output_dir: Path) -> bool:
    for path in output_dir.glob("xhs/jsonl/*comments*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(row.get("parent_comment_id") or "").strip():
                        return True
        except OSError:
            continue
    return False


def read_jsonl_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def latest_search_pagination_status(output_dir: Path) -> dict:
    rows = read_jsonl_rows(output_dir / "xhs" / "quality" / "search_pagination_status.jsonl")
    return rows[-1] if rows else {}


def promote_pilot_page_limit(
    output_dir: Path,
    *,
    keyword: str,
    context: dict[str, str | int] | None = None,
) -> bool:
    """Mark an intentional page-capped pilot as complete for its declared scope."""
    latest = latest_search_pagination_status(output_dir)
    if latest.get("stop_reason") != "max_pages_guard" or not output_has_search_rows(output_dir):
        return False
    path = output_dir / "xhs" / "quality" / "search_pagination_status.jsonl"
    payload = {
        **latest,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "keyword": keyword,
        "status": "complete",
        "stop_reason": "pilot_page_limit",
        "complete": True,
        "pilot_scope": True,
        "source": "xhs_distributed_runner",
        **(context or {}),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return True


def pilot_search_output_complete(output_dir: Path) -> bool:
    latest = latest_search_pagination_status(output_dir)
    return (
        latest.get("complete") is True
        and latest.get("stop_reason") == "pilot_page_limit"
        and output_has_search_rows(output_dir)
    )


def search_resume_page(output_dir: Path) -> int:
    status = latest_search_pagination_status(output_dir)
    if not status or status.get("complete") is True:
        return 1
    stop_reason = str(status.get("stop_reason") or "")
    try:
        page = max(1, int(status.get("page") or 1))
        recorded_resume_page = int(status.get("resume_page") or 0)
    except (TypeError, ValueError):
        return 1
    if recorded_resume_page > 0:
        return recorded_resume_page
    if stop_reason in {"empty_response", "data_fetch_error"}:
        return page
    if not stop_reason and status.get("status") == "running":
        return page + 1
    return 1


def append_search_failure_checkpoint(
    output_dir: Path,
    *,
    keyword: str,
    page: int,
    failure_kind: str,
    context: dict[str, str | int] | None = None,
) -> Path:
    """Record subprocess-level failures that bypass MediaCrawler pagination hooks."""
    path = output_dir / "xhs" / "quality" / "search_pagination_status.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "keyword": keyword,
        "page": max(1, page),
        "status": "incomplete",
        "stop_reason": failure_kind,
        "complete": False,
        "resume_page": max(1, page),
        "source": "xhs_distributed_runner",
        **(context or {}),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def latest_search_page_from_log(log_path: Path) -> int | None:
    """Recover the last attempted search page after an abrupt crawler exit."""
    pattern = re.compile(r"search Xiaohongshu keyword: .*?, page: (\d+)")
    latest: int | None = None
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                match = pattern.search(line)
                if match:
                    latest = int(match.group(1))
    except OSError:
        return None
    return latest


def comment_pagination_complete(output_dir: Path, stage: str) -> bool:
    rows = read_jsonl_rows(output_dir / "xhs" / "quality" / "comment_pagination_status.jsonl")
    if not rows:
        return False
    latest: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (
            str(row.get("kind") or ""),
            str(row.get("note_id") or ""),
            str(row.get("root_comment_id") or ""),
        )
        latest[key] = row
    top_rows = [row for key, row in latest.items() if key[0] == "top_level"]
    if not top_rows or any(row.get("status") != "complete" for row in top_rows):
        return False
    if stage == "selected-sub-comments":
        reply_rows = [row for key, row in latest.items() if key[0] == "reply"]
        if any(row.get("status") != "complete" for row in reply_rows):
            return False
        target_rows = read_jsonl_rows(
            output_dir / "xhs" / "quality" / "subcomment_parent_targets.jsonl"
        )
        expected_parents = {
            (str(row.get("note_id") or ""), str(row.get("root_comment_id") or ""))
            for row in target_rows
            if str(row.get("root_comment_id") or "")
        }
        completed_parents = {
            (key[1], key[2])
            for key, row in latest.items()
            if key[0] == "reply" and row.get("status") == "complete"
        }
        if expected_parents and not expected_parents.issubset(completed_parents):
            return False
    return True


def subcomment_resume_checkpoint_available(output_dir: Path) -> bool:
    targets = read_jsonl_rows(
        output_dir / "xhs" / "quality" / "subcomment_parent_targets.jsonl"
    )
    if targets:
        return True
    statuses = read_jsonl_rows(
        output_dir / "xhs" / "quality" / "comment_pagination_status.jsonl"
    )
    return any(
        row.get("kind") == "reply"
        and (
            str(row.get("resume_cursor") or "")
            or row.get("status") in {"running", "incomplete"}
        )
        for row in statuses
    )


def observed_top_level_comments(output_dir: Path) -> int:
    rows = read_jsonl_rows(output_dir / "xhs" / "quality" / "comment_pagination_status.jsonl")
    values = [
        int(row.get("observed_comments") or 0)
        for row in rows
        if row.get("kind") == "top_level" and row.get("status") == "complete"
    ]
    return values[-1] if values else 0


def command_to_text(cmd: list[str]) -> str:
    return " ".join(json.dumps(part, ensure_ascii=False) if " " in part else part for part in cmd)


def build_crawler_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("UV_DEFAULT_INDEX", "https://pypi.org/simple")
    context = {
        "XHS_COLLECTION_PLATFORM": "rednote_international" if getattr(args, "international_rednote", False) else "xiaohongshu_domestic",
        "XHS_COLLECTION_EGRESS_REGION": getattr(args, "collection_egress_region", ""),
        "XHS_COLLECTION_EGRESS_ID": getattr(args, "collection_egress_id", ""),
        "XHS_COLLECTION_ACCOUNT_ID": getattr(args, "account_id", ""),
        "XHS_CDP_DEBUG_PORT": str(getattr(args, "cdp_debug_port", 9222)),
    }
    for name, value in context.items():
        if str(value).strip():
            env[name] = str(value).strip()

    static_proxy_url = str(getattr(args, "static_proxy_url", "") or "").strip()
    if static_proxy_url:
        env["XHS_STATIC_PROXY_URL"] = static_proxy_url
        env["XHS_DISABLE_GEOLOCATION"] = "1"
        for name in ("NO_PROXY", "no_proxy"):
            values = [
                value.strip()
                for value in env.get(name, "").split(",")
                if value.strip()
                and "xiaohongshu.com" not in value.lower()
                and "rednote.com" not in value.lower()
            ]
            env[name] = ",".join(values)
    return env


def collection_context_from_args(args: argparse.Namespace) -> dict[str, str | int]:
    return {
        "collection_platform": "rednote_international" if getattr(args, "international_rednote", False) else "xiaohongshu_domestic",
        "collection_egress_region": getattr(args, "collection_egress_region", ""),
        "collection_egress_id": getattr(args, "collection_egress_id", ""),
        "collection_account_id": getattr(args, "account_id", ""),
        "collection_cdp_port": getattr(args, "cdp_debug_port", 9222),
    }


def log_has_captcha(path: Path) -> bool:
    """Detect platform verification prompts without matching collected text."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if any(marker in line for marker in DATA_LOG_MARKERS):
                    continue
                if any(marker in line for marker in CAPTCHA_MARKERS):
                    return True
    except OSError:
        return False
    return False


def classify_failure(log_path: Path, returncode: int, captcha: bool) -> str:
    """Classify a failed crawler subprocess without treating collected text as an error."""
    if captcha:
        return "captcha"
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "command_failed" if returncode else "empty_output"
    latest_login_failure = max((text.rfind(marker) for marker in LOGIN_FAILURE_MARKERS), default=-1)
    latest_login_success = max((text.rfind(marker) for marker in LOGIN_SUCCESS_MARKERS), default=-1)
    if latest_login_failure > latest_login_success:
        return "login_expired"
    if any(marker in text for marker in UNAVAILABLE_NOTE_MARKERS):
        return "unavailable_note"
    if any(marker in text for marker in TRANSIENT_FAILURE_MARKERS):
        return "transient_network"
    return "command_failed" if returncode else "empty_output"


def quarantine_incomplete_output(output_dir: Path, run_root: Path, attempt: int) -> Path | None:
    """Preserve a failed selected-comment attempt so its rows cannot be reused."""
    if not output_dir.exists():
        return None
    try:
        relative = output_dir.relative_to(run_root)
    except ValueError:
        relative = Path(output_dir.name)
    quarantine = run_root.parent / f"incomplete_attempts_{now_stamp()}_retry{attempt}" / relative
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(output_dir), str(quarantine))
    return quarantine


def latest_quarantined_search_checkpoint(output_dir: Path, run_root: Path) -> Path | None:
    """Find the newest auditable partial search batch for this exact job."""
    try:
        relative = output_dir.relative_to(run_root)
    except ValueError:
        return None
    for attempt_root in sorted(run_root.parent.glob("incomplete_attempts_*"), reverse=True):
        candidate = attempt_root / relative
        if not candidate.is_dir() or not output_has_any_jsonl_rows(candidate):
            continue
        if latest_search_pagination_status(candidate).get("complete") is True:
            continue
        return candidate
    return None


def restore_search_checkpoint(output_dir: Path, run_root: Path) -> Path | None:
    """Restore a quarantined partial search batch without deleting its audit copy."""
    if output_has_any_jsonl_rows(output_dir):
        return None
    checkpoint = latest_quarantined_search_checkpoint(output_dir, run_root)
    if checkpoint is None:
        return None
    shutil.copytree(checkpoint, output_dir, dirs_exist_ok=True)
    write_json(
        output_dir / "checkpoint_restore.json",
        {
            "restored_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(checkpoint),
            "resume_page": search_resume_page(output_dir),
        },
    )
    return checkpoint


def run_command(
    cmd: list[str],
    cwd: Path,
    log_path: Path,
    env: dict,
    dry_run: bool,
    command_timeout: int = 0,
) -> tuple[int, bool]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        log_path.write_text("DRY RUN\n" + command_to_text(cmd) + "\n", encoding="utf-8")
        print(command_to_text(cmd))
        return 0, False

    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + command_to_text(cmd) + "\n\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        captcha = False
        timed_out = False
        deadline = time.monotonic() + command_timeout if command_timeout > 0 else None
        while proc.poll() is None:
            time.sleep(1)
            log.flush()
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                log.write(f"\nCommand timeout after {command_timeout}s; terminating crawler subprocess.\n")
                log.flush()
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                break
            if log_has_captcha(log_path):
                captcha = True
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                break

    captcha = captcha or log_has_captcha(log_path)
    return (124 if timed_out else proc.returncode), captcha


def event_matches_device(event: EventRow, device_id: str) -> bool:
    assigned = normalize_device(event.assigned_device)
    device = normalize_device(device_id)
    return assigned in {"", "all", "shared", device}


def select_events(events: list[EventRow], args: argparse.Namespace) -> list[EventRow]:
    selected = [event for event in events if event.enabled or args.include_disabled]
    selected = [event for event in selected if event_matches_device(event, args.device_id)]
    if args.event_ids:
        wanted = {item.strip() for item in args.event_ids.split(",") if item.strip()}
        selected = [event for event in selected if event.event_id in wanted]
    if args.groups:
        wanted_groups = {item.strip() for item in args.groups.split(",") if item.strip()}
        selected = [event for event in selected if event.collection_group in wanted_groups]
    if args.max_events:
        selected = selected[: args.max_events]
    return selected


def iter_keyword_jobs(events: list[EventRow], max_keywords: int | None) -> Iterable[tuple[EventRow, str]]:
    count = 0
    for event in events:
        for keyword in event.keywords:
            yield event, keyword
            count += 1
            if max_keywords and count >= max_keywords:
                return


def collect_search_stage(args: argparse.Namespace) -> int:
    events = select_events(load_manifest(args.manifest), args)
    if not events:
        print("No events selected. Check --device-id, --event-ids, --groups, or manifest enabled flags.")
        return 2

    run_root = args.run_root / args.run_id / f"device_{normalize_device(args.device_id)}"
    ledger_path = run_root / "batch_ledger.csv"
    env = build_crawler_env(args)

    jobs = list(iter_keyword_jobs(events, args.max_keywords))
    print(f"Selected {len(events)} events, {len(jobs)} keyword jobs for stage={args.stage}.")
    completed_search_keys = completed_search_keys_from_ledger(ledger_path, args.stage) if args.resume_skip_completed else set()

    for index, (event, keyword) in enumerate(jobs, start=1):
        started_at = datetime.now().isoformat(timespec="seconds")
        keyword_slug = slug_text(keyword)
        output_dir = run_root / args.stage / event.event_id / keyword_slug
        log_path = output_dir / "crawler.log"
        search_key = (event.event_id, keyword)
        if args.accept_search_max_pages_stop:
            promoted = promote_pilot_page_limit(
                output_dir,
                keyword=keyword,
                context=collection_context_from_args(args),
            )
            if pilot_search_output_complete(output_dir) and search_key not in completed_search_keys:
                reconciled_at = datetime.now().isoformat(timespec="seconds")
                append_ledger(
                    ledger_path,
                    {
                        "started_at": reconciled_at,
                        "finished_at": reconciled_at,
                        "device_id": args.device_id,
                        "account_id": args.account_id,
                        "stage": args.stage,
                        "event_id": event.event_id,
                        "event_name": event.event_name,
                        "keyword": keyword,
                        "output_dir": str(output_dir),
                        "log_path": str(log_path),
                        "returncode": 0,
                        "captcha_detected": False,
                        "status": "ok",
                    },
                )
                completed_search_keys.add(search_key)
                if promoted:
                    print(f"Promoted existing {keyword} output to pilot_page_limit completion.")
        if search_key in completed_search_keys:
            print(f"[{index}/{len(jobs)}] skip completed {args.stage} {event.event_id} | {keyword}")
            continue
        meta = {
            "run_id": args.run_id,
            "device_id": args.device_id,
            "account_id": args.account_id,
            "stage": args.stage,
            "event": event.__dict__ | {"keywords": event.keywords},
            "keyword": keyword,
            "started_at": started_at,
            "output_dir": str(output_dir),
            **collection_context_from_args(args),
        }
        print(f"[{index}/{len(jobs)}] {event.event_id} {event.event_name} | {keyword}")
        attempt = 0
        search_session = 0
        restored_checkpoint = restore_search_checkpoint(output_dir, run_root) if args.all_search_results else None
        if restored_checkpoint is not None:
            print(
                f"Restored partial search checkpoint from {restored_checkpoint}; "
                f"resume page={search_resume_page(output_dir)}."
            )
        while True:
            resume_page = search_resume_page(output_dir)
            search_session += 1
            session_started_at = datetime.now().isoformat(timespec="seconds")
            cmd, cwd = build_media_command(
                event,
                keyword,
                args.stage,
                output_dir,
                args,
                search_start_page=resume_page,
            )
            meta["attempt"] = attempt + 1
            meta["search_session"] = search_session
            meta["search_start_page"] = resume_page
            write_json(output_dir / "batch_meta.json", meta)
            returncode, captcha = run_command(cmd, cwd, log_path, env, args.dry_run, args.command_timeout)
            finished_at = datetime.now().isoformat(timespec="seconds")
            has_output = output_has_search_rows(output_dir) if args.search_card_only else output_has_jsonl_rows(output_dir)
            pagination_status = latest_search_pagination_status(output_dir) if args.all_search_results else {}
            failure_kind = classify_failure(log_path, returncode, captcha)
            if args.all_search_results and failure_kind in {"captcha", "login_expired"}:
                append_search_failure_checkpoint(
                    output_dir,
                    keyword=keyword,
                    page=latest_search_page_from_log(log_path) or resume_page,
                    failure_kind=failure_kind,
                    context=collection_context_from_args(args),
                )
                pagination_status = latest_search_pagination_status(output_dir)
            if (
                args.accept_search_max_pages_stop
                and returncode == 0
                and failure_kind == "empty_output"
                and pagination_status.get("stop_reason") == "max_pages_guard"
                and has_output
            ):
                promote_pilot_page_limit(
                    output_dir,
                    keyword=keyword,
                    context=collection_context_from_args(args),
                )
                pagination_status = latest_search_pagination_status(output_dir)
                failure_kind = ""
            if args.dry_run:
                status = "dry_run"
            elif failure_kind == "captcha":
                status = "captcha"
            elif failure_kind == "login_expired":
                status = "login_expired"
            elif failure_kind == "transient_network":
                status = "retryable_network"
            elif returncode != 0:
                status = "failed"
            elif args.all_search_results and pagination_status.get("stop_reason") in {
                "session_detail_limit",
                "session_page_limit",
            }:
                status = "session_checkpoint"
            elif not has_output and not (
                args.all_search_results and pagination_status.get("complete") is True
            ):
                status = "empty"
            elif args.all_search_results and pagination_status.get("stop_reason") == "max_pages_guard":
                status = "incomplete_guard_hit"
            elif args.all_search_results and pagination_status.get("complete") is not True:
                status = "incomplete_pagination"
            else:
                status = "ok"
            append_ledger(
                ledger_path,
                {
                    "started_at": session_started_at,
                    "finished_at": finished_at,
                    "device_id": args.device_id,
                    "account_id": args.account_id,
                    "stage": args.stage,
                    "event_id": event.event_id,
                    "event_name": event.event_name,
                    "keyword": keyword,
                    "output_dir": str(output_dir),
                    "log_path": str(log_path),
                    "returncode": returncode,
                    "captcha_detected": captcha,
                    "status": status,
                },
            )
            if status == "session_checkpoint":
                resume_page = search_resume_page(output_dir)
                checkpoint_reason = str(pagination_status.get("stop_reason") or "session_checkpoint")
                print(
                    f"Saved search checkpoint ({checkpoint_reason}) after "
                    f"{pagination_status.get('session_pages', 0)} pages and "
                    f"{pagination_status.get('session_detail_attempts', 0)} detail requests; "
                    f"resume page={resume_page}. Cooling down {args.search_session_cooldown}s."
                )
                if not args.dry_run and args.search_session_cooldown > 0:
                    time.sleep(args.search_session_cooldown)
                attempt = 0
                continue
            if failure_kind == "transient_network" and attempt < args.transient_retries:
                quarantined = quarantine_incomplete_output(output_dir, run_root, attempt + 1)
                attempt += 1
                restored_checkpoint = restore_search_checkpoint(output_dir, run_root)
                resume_page = search_resume_page(output_dir)
                print(
                    "Transient search failure; "
                    f"attempt {attempt}/{args.transient_retries} quarantined at {quarantined}. "
                    f"Restored from {restored_checkpoint}; resume page={resume_page}. "
                    f"Retrying this keyword after {args.transient_retry_delay}s."
                )
                time.sleep(args.transient_retry_delay)
                continue
            break

        final_quarantine = None
        if status not in {"ok", "dry_run", "empty"} and output_dir.exists() and output_has_any_jsonl_rows(output_dir):
            final_quarantine = quarantine_incomplete_output(output_dir, run_root, attempt + 1)
            print(f"Preserved partial search batch at {final_quarantine}.")

        if captcha and args.stop_on_captcha:
            print(f"CAPTCHA detected. Stop now and cool down this account. Partial: {final_quarantine or output_dir}")
            return 86
        if failure_kind == "login_expired":
            print(f"Login session expired. Stop now and refresh login/session. Partial: {final_quarantine or output_dir}")
            return 88
        if status == "empty" and args.stop_on_empty:
            print(f"No JSONL output generated. Stop now and refresh login/session. Log: {log_path}")
            return 87
        if status in {"incomplete_guard_hit", "incomplete_pagination"}:
            print(
                f"Search pagination incomplete ({status}); stop_reason="
                f"{pagination_status.get('stop_reason') or 'missing_terminal_status'}. Log: {log_path}"
            )
            if args.stop_on_error:
                return 89
        if failure_kind == "transient_network" and args.stop_on_error:
            print(f"Transient search failure exhausted automatic retries. Log: {log_path}")
            return returncode or 89
        if returncode != 0 and args.stop_on_error:
            print(f"Command failed with code {returncode}. Log: {log_path}")
            return returncode
        if index < len(jobs) and args.sleep_between_keywords > 0:
            print(f"Sleeping {args.sleep_between_keywords}s before next keyword...")
            time.sleep(args.sleep_between_keywords)

    print(f"Done. Ledger: {ledger_path}")
    return 0


def discover_note_urls(run_root: Path, device_id: str, source_stage: str) -> list[str]:
    device_root = run_root / f"device_{normalize_device(device_id)}" / source_stage
    urls: list[str] = []
    seen: set[str] = set()
    for path in sorted(device_root.glob("**/xhs/jsonl/*contents*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = str(row.get("note_url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                urls.append(url)
    return urls


def write_note_url_csv(path: Path, urls: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["note_url"])
        writer.writeheader()
        for url in urls:
            writer.writerow({"note_url": url})


def load_note_urls_from_file(path: Path) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = str(row.get("note_url") or "").strip()
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = str(row.get("note_url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def load_selected_note_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            note_url = str(row.get("note_url") or row.get("note_url_access") or row.get("note_url_public") or "").strip()
            if not note_url or note_url in seen:
                continue
            seen.add(note_url)
            rows.append({
                "event_id": str(row.get("event_id") or "").strip(),
                "event_name": str(row.get("event_name") or "").strip(),
                "phase_id": str(row.get("phase_id") or "").strip(),
                "phase_name": str(row.get("phase_name") or "").strip(),
                "note_id": str(row.get("note_id") or "").strip(),
                "note_url": note_url,
                "representative_rank_in_phase": str(row.get("representative_rank_in_phase") or "").strip(),
                "representative_score": str(row.get("representative_score") or "").strip(),
            })
    return rows


def discover_note_rows(run_root: Path, device_id: str, source_stage: str) -> list[dict[str, str]]:
    device_root = run_root / f"device_{normalize_device(device_id)}" / source_stage
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in sorted(device_root.glob("**/xhs/jsonl/*contents*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                note_url = str(row.get("note_url") or "").strip()
                if not note_url or note_url in seen:
                    continue
                seen.add(note_url)
                rows.append({
                    "event_id": str(row.get("event_id") or "").strip(),
                    "phase_id": str(row.get("phase_id") or "").strip(),
                    "note_id": str(row.get("note_id") or "").strip(),
                    "note_url": note_url,
                })
    return rows


def write_note_rows_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["event_id", "phase_id", "note_id", "note_url"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def chunked(items: list[dict[str, str]], size: int) -> Iterable[list[dict[str, str]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def build_detail_command(
    note_urls: list[str],
    output_dir: Path,
    args: argparse.Namespace,
) -> tuple[list[str], Path]:
    python_cmd, python_cwd = get_media_python_cmd()
    if python_cwd == MEDIA_CRAWLER_DIR:
        main_path = "main.py"
        cwd = MEDIA_CRAWLER_DIR
    else:
        main_path = str(MEDIA_CRAWLER_DIR / "main.py")
        cwd = ROOT
    cmd = [
        *python_cmd,
        main_path,
        "--platform",
        "xhs",
        "--lt",
        args.login_type,
        "--type",
        "detail",
        "--specified_id",
        ",".join(note_urls),
        "--get_comment",
        "false" if args.stage == "selected-details" else "true",
        "--get_sub_comment",
        "true" if args.stage == "selected-sub-comments" else "false",
        "--headless",
        "false",
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(output_dir),
        "--crawler_max_notes_count",
        str(len(note_urls)),
        "--max_comments_count_singlenotes",
        str(args.comments_per_note if args.comments_per_note is not None else 80),
        "--max_concurrency_num",
        str(args.max_concurrency),
        "--crawler_sleep_sec",
        str(args.page_sleep),
    ]
    if getattr(args, "static_proxy_url", ""):
        cmd.extend(
            [
                "--enable_ip_proxy",
                "true",
                "--ip_proxy_provider_name",
                "static",
            ]
        )
    if getattr(args, "international_rednote", False):
        cmd.extend(["--xhs_international", "true"])
    return cmd, cwd


def collect_selected_comments(args: argparse.Namespace) -> int:
    if not args.selected_notes_file:
        print(f"--selected-notes-file is required for {args.stage} stage.")
        return 2
    selected_stage = args.stage
    rows = load_selected_note_rows(args.selected_notes_file.resolve())
    if args.selected_phase_ids:
        wanted_phases = {item.strip() for item in args.selected_phase_ids.split(",") if item.strip()}
        rows = [
            row for row in rows
            if (row.get("phase_id") or row.get("event_id") or "unknown") in wanted_phases
        ]
    if args.selected_notes_per_phase:
        limited: list[dict[str, str]] = []
        counts: dict[str, int] = {}
        for row in rows:
            key = row.get("phase_id") or row.get("event_id") or "unknown"
            counts[key] = counts.get(key, 0)
            if counts[key] < args.selected_notes_per_phase:
                limited.append(row)
                counts[key] += 1
        rows = limited
    if not rows:
        print("No selected note URLs found.")
        return 2

    by_phase: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = row.get("phase_id") or row.get("event_id") or "unknown"
        by_phase.setdefault(key, []).append(row)

    run_root = args.run_root / args.run_id / f"device_{normalize_device(args.device_id)}"
    ledger_path = run_root / "batch_ledger.csv"
    env = build_crawler_env(args)
    jobs: list[tuple[str, int, list[dict[str, str]]]] = []
    for phase_id, phase_rows in sorted(by_phase.items()):
        for chunk_index, chunk in enumerate(chunked(phase_rows, args.notes_per_batch), start=1):
            jobs.append((phase_id, chunk_index, chunk))
    if args.max_batches:
        jobs = jobs[: args.max_batches]

    print(f"{selected_stage} jobs: {len(jobs)} batches, {len(rows)} notes.")
    completed_dirs = completed_output_dirs_from_ledger(ledger_path, selected_stage) if args.resume_skip_completed else set()
    for index, (phase_id, chunk_index, chunk) in enumerate(jobs, start=1):
        first = chunk[0]
        raw_event_id = first.get("phase_id") or first.get("event_id") or phase_id
        event_name = first.get("phase_name") or first.get("event_name") or raw_event_id
        output_dir = run_root / selected_stage / raw_event_id / f"chunk_{chunk_index:03d}"
        log_path = output_dir / "crawler.log"
        has_reusable_output = (
            selected_detail_output_complete(output_dir)
            if selected_stage == "selected-details"
            else comment_pagination_complete(output_dir, selected_stage)
        )
        if str(output_dir) in completed_dirs or (args.resume_skip_completed and has_reusable_output):
            print(f"[{index}/{len(jobs)}] skip completed {raw_event_id} chunk={chunk_index:03d}")
            continue
        started_at = datetime.now().isoformat(timespec="seconds")
        event_payload = {
            "event_id": raw_event_id,
            "event_name": event_name,
            "event_date": "",
            "country_group": "Baseline" if raw_event_id.startswith("B") else "",
            "brand": "",
            "assigned_device": args.device_id,
            "priority": chunk_index,
            "collection_group": "selected_comments",
            "enabled": True,
            "keywords": [],
            "analysis_window_start": "",
            "analysis_window_end": "",
            "notes_limit_recon": 0,
            "notes_limit_deep": len(chunk),
            "comments_per_note_pilot": args.comments_per_note if args.comments_per_note is not None else 80,
            "comments_per_note_deep": args.comments_per_note if args.comments_per_note is not None else 80,
            "author_post_limit": 0,
            "notes": "selected representative notes comments batch",
        }
        meta = {
            "run_id": args.run_id,
            "device_id": args.device_id,
            "account_id": args.account_id,
            "stage": selected_stage,
            "event": event_payload,
            "keyword": f"selected_notes_{raw_event_id}_chunk_{chunk_index:03d}",
            "selected_notes": [
                {k: row.get(k, "") for k in ("note_id", "representative_rank_in_phase", "representative_score")}
                for row in chunk
            ],
            "started_at": started_at,
            "output_dir": str(output_dir),
            **collection_context_from_args(args),
        }
        cmd, cwd = build_detail_command([row["note_url"] for row in chunk], output_dir, args)
        print(f"[{index}/{len(jobs)}] {raw_event_id} chunk={chunk_index:03d} notes={len(chunk)}")
        attempt = 0
        while True:
            meta["attempt"] = attempt + 1
            write_json(output_dir / "batch_meta.json", meta)
            returncode, captcha = run_command(cmd, cwd, log_path, env, args.dry_run, args.command_timeout)
            finished_at = datetime.now().isoformat(timespec="seconds")
            has_output = output_has_jsonl_rows(output_dir)
            has_required_output = (
                selected_detail_output_complete(output_dir)
                if selected_stage == "selected-details"
                else comment_pagination_complete(output_dir, selected_stage)
            )
            failure_kind = classify_failure(log_path, returncode, captcha)
            status = "dry_run" if args.dry_run else (
                "captcha" if failure_kind == "captcha" else
                "login_expired" if failure_kind == "login_expired" else
                "skipped_unavailable" if failure_kind == "unavailable_note" else
                "retryable_network" if failure_kind == "transient_network" else
                "ok" if returncode == 0 and has_output and has_required_output else
                "incomplete_pagination" if returncode == 0 and has_output else
                "empty" if returncode == 0 else
                "failed"
            )
            append_ledger(
                ledger_path,
                {
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "device_id": args.device_id,
                    "account_id": args.account_id,
                    "stage": selected_stage,
                    "event_id": raw_event_id,
                    "event_name": event_name,
                    "keyword": f"selected_notes_chunk_{chunk_index:03d}",
                    "output_dir": str(output_dir),
                    "log_path": str(log_path),
                    "returncode": returncode,
                    "captcha_detected": captcha,
                    "status": status,
                },
            )
            resumable_subcomments = (
                selected_stage == "selected-sub-comments"
                and subcomment_resume_checkpoint_available(output_dir)
            )
            if failure_kind == "transient_network" and attempt < args.transient_retries:
                attempt += 1
                if resumable_subcomments:
                    print(
                        "Transient network failure; preserving parent/cursor checkpoint in place. "
                        f"Retrying attempt {attempt}/{args.transient_retries} after "
                        f"{args.transient_retry_delay}s."
                    )
                else:
                    quarantined = quarantine_incomplete_output(output_dir, run_root, attempt)
                    print(
                        "Transient network failure; "
                        f"attempt {attempt}/{args.transient_retries} quarantined at {quarantined}. "
                        f"Retrying this batch after {args.transient_retry_delay}s."
                    )
                time.sleep(args.transient_retry_delay)
                continue
            break
        final_quarantine = None
        resumable_subcomments = (
            selected_stage == "selected-sub-comments"
            and subcomment_resume_checkpoint_available(output_dir)
        )
        if (
            status not in {"ok", "dry_run", "empty"}
            and output_dir.exists()
            and output_has_jsonl_rows(output_dir)
            and not resumable_subcomments
        ):
            final_quarantine = quarantine_incomplete_output(output_dir, run_root, attempt + 1)
            print(f"Preserved partial batch at {final_quarantine}.")
        elif status not in {"ok", "dry_run", "empty"} and resumable_subcomments:
            print("Preserved resumable parent_comment_id + cursor checkpoint in active output.")
        if captcha and args.stop_on_captcha:
            print(f"CAPTCHA detected. Stop now and cool down this account. Partial: {final_quarantine or output_dir}")
            return 86
        if failure_kind == "login_expired":
            print(f"Login session expired. Stop now and refresh login/session. Partial: {final_quarantine or output_dir}")
            return 88
        if failure_kind == "unavailable_note":
            print(f"Note unavailable on platform; recorded skipped_unavailable and continuing. Log: {log_path}")
        if status == "empty" and args.stop_on_empty:
            print(f"No required JSONL output generated. Stop now and inspect the batch. Log: {log_path}")
            return 87
        if status == "incomplete_pagination":
            if final_quarantine is None and not resumable_subcomments:
                final_quarantine = quarantine_incomplete_output(output_dir, run_root, attempt + 1)
            if resumable_subcomments:
                print("Comment pagination incomplete; resume from saved parent_comment_id + cursor.")
            else:
                print(f"Comment pagination incomplete; quarantined at {final_quarantine}.")
            if args.stop_on_error:
                return 90
        if failure_kind == "transient_network" and args.stop_on_error:
            print(f"Transient network failure exhausted automatic retries. Log: {log_path}")
            return returncode or 89
        if returncode != 0 and args.stop_on_error:
            print(f"Command failed with code {returncode}. Log: {log_path}")
            return returncode
        if index < len(jobs):
            cooldown = max(0, args.sleep_between_batches)
            root_comments = observed_top_level_comments(output_dir)
            if root_comments > args.high_volume_comment_threshold:
                cooldown = max(cooldown, args.high_volume_sleep)
            if args.long_cooldown_every > 0 and index % args.long_cooldown_every == 0:
                cooldown += args.long_cooldown
            if cooldown > 0:
                print(
                    f"Sleeping {cooldown}s before next selected-note batch "
                    f"(observed top-level comments={root_comments})..."
                )
                time.sleep(cooldown)
    print(f"Done. Ledger: {ledger_path}")
    return 0


def run_author_profiles(args: argparse.Namespace) -> int:
    run_root = args.run_root / args.run_id
    urls: list[str] = []
    seen: set[str] = set()
    if args.notes_file:
        for url in load_note_urls_from_file(args.notes_file.resolve()):
            if url not in seen:
                seen.add(url)
                urls.append(url)
    else:
        source_stages = [item.strip() for item in args.source_stage.split(",") if item.strip()]
        for stage in source_stages:
            for url in discover_note_urls(run_root, args.device_id, stage):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
    if not urls:
        print(f"No note URLs found. Run recon/deep-comments first or pass --notes-file.")
        return 2

    if args.author_source_limit:
        urls = urls[: args.author_source_limit]
    output_dir = run_root / f"device_{normalize_device(args.device_id)}" / "author_profiles"
    notes_csv = output_dir / "author_profile_source_note_urls.csv"
    write_note_url_csv(notes_csv, urls)

    python_cmd, python_cwd = get_media_python_cmd()
    script_path = str(ROOT / "xhs_author_probe.py")
    cwd = python_cwd
    cmd = [
        *python_cmd,
        script_path,
        "--notes-csv",
        str(notes_csv),
        "--output-dir",
        str(output_dir),
        "--limit-notes",
        str(len(urls)),
        "--creator-note-limit",
        str(args.author_post_limit),
        "--comment-probe-limit",
        "0",
        "--sleep",
        str(args.author_sleep),
        "--browser-timeout",
        str(args.browser_timeout),
    ]
    log_path = output_dir / "author_profiles.log"
    env = build_crawler_env(args)
    print(f"Author profile source notes: {len(urls)}")
    returncode, captcha = run_command(cmd, cwd, log_path, env, args.dry_run, args.command_timeout)
    if captcha and args.stop_on_captcha:
        print(f"CAPTCHA detected in author profile stage. Log: {log_path}")
        return 86
    print(f"Author profile output: {output_dir}")
    return returncode


def run_commenter_profiles(args: argparse.Namespace) -> int:
    run_root = args.run_root / args.run_id
    output_dir = run_root / f"device_{normalize_device(args.device_id)}" / "commenter_profiles"
    notes_file = args.notes_file
    if not notes_file:
        rows: list[dict[str, str]] = []
        source_stages = [item.strip() for item in args.source_stage.split(",") if item.strip()]
        for stage in source_stages:
            rows.extend(discover_note_rows(run_root, args.device_id, stage))
        if not rows:
            print(f"No note URLs found. Run full-recon-comments/recon first or pass --notes-file.")
            return 2
        notes_file = output_dir / "commenter_profile_source_note_urls.csv"
        write_note_rows_csv(notes_file, rows)

    python_cmd, python_cwd = get_media_python_cmd()
    script_path = str(ROOT / "xhs_commenter_profile_probe.py")
    cmd = [
        *python_cmd,
        script_path,
        "--notes-file",
        str(notes_file.resolve()),
        "--output-dir",
        str(output_dir),
        "--device-id",
        args.device_id,
        "--account-id",
        args.account_id,
        "--comments-per-note",
        str(args.comments_per_note or 10000),
        "--public-post-limit",
        str(args.public_post_limit),
        "--sleep",
        str(args.author_sleep),
        "--browser-timeout",
        str(args.browser_timeout),
    ]
    if args.author_source_limit:
        cmd.extend(["--limit-notes", str(args.author_source_limit)])
    if args.commenter_limit:
        cmd.extend(["--commenter-limit", str(args.commenter_limit)])

    log_path = output_dir / "commenter_profiles.log"
    env = build_crawler_env(args)
    print(f"Commenter profile source notes: {notes_file}")
    returncode, captcha = run_command(cmd, python_cwd, log_path, env, args.dry_run, args.command_timeout)
    if captcha and args.stop_on_captcha:
        print(f"CAPTCHA detected in commenter profile stage. Log: {log_path}")
        return 86
    print(f"Commenter profile output: {output_dir}")
    return returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Distributed XHS event collection runner.")
    parser.add_argument("--stage", choices=["recon", "full-recon-comments", "pilot-comments", "deep-comments", "selected-details", "selected-comments", "selected-sub-comments", "author-profiles", "commenter-profiles"], required=True)
    parser.add_argument("--device-id", required=True, help="A, B, C, or another manifest-assigned device id.")
    parser.add_argument("--account-id", default="", help="Local account label for metadata only, e.g. account_a.")
    parser.add_argument("--collection-egress-region", default="", help="Research stratum for the collector egress, e.g. japan or singapore.")
    parser.add_argument("--collection-egress-id", default="", help="Non-secret fixed egress label, such as a Clash node name.")
    parser.add_argument(
        "--international-rednote",
        action="store_true",
        help="Use RedNote international endpoints; keep its run directory and browser profile separate from domestic Xiaohongshu.",
    )
    parser.add_argument("--static-proxy-url", default="", help="Fixed HTTP proxy shared by MediaCrawler and the pre-launched CDP browser.")
    parser.add_argument(
        "--allow-direct-egress",
        action="store_true",
        help="Allow an explicitly verified direct egress for a regional run when no HTTP proxy is configured.",
    )
    parser.add_argument("--cdp-debug-port", type=int, default=9222, help="CDP port of the browser launched with the same fixed proxy.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id", default="main_20260704")
    parser.add_argument("--event-ids", default="", help="Comma-separated event ids, e.g. E001,E003.")
    parser.add_argument("--groups", default="", help="Comma-separated collection groups, e.g. core,observe.")
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--max-keywords", type=int, default=0)
    parser.add_argument("--notes-per-keyword", type=int, default=0)
    parser.add_argument(
        "--comments-per-note",
        type=int,
        default=None,
        help="Maximum first-level comments per note; 0 means paginate until the endpoint is exhausted.",
    )
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--all-search-results", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--search-card-only", action=argparse.BooleanOptionalAction, default=False, help="Land regional search cards without requesting note details.")
    parser.add_argument("--search-sort", choices=["latest", "general", "popularity_descending"], default="latest")
    parser.add_argument("--window-start", default="")
    parser.add_argument("--window-end", default="")
    parser.add_argument("--max-search-pages", type=int, default=200)
    parser.add_argument(
        "--accept-search-max-pages-stop",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Treat the configured search page cap as completion of an explicitly page-capped pilot.",
    )
    parser.add_argument("--page-sleep", type=int, default=15)
    parser.add_argument("--search-page-cooldown", type=int, default=300)
    parser.add_argument("--search-page-cooldown-every", type=int, default=5)
    parser.add_argument(
        "--search-detail-session-limit",
        type=int,
        default=8,
        help="Maximum search detail requests per crawler subprocess; 0 disables checkpointing.",
    )
    parser.add_argument(
        "--search-page-session-limit",
        type=int,
        default=0,
        help="Maximum successful search pages per crawler subprocess; 0 disables checkpointing.",
    )
    parser.add_argument(
        "--search-session-cooldown",
        type=int,
        default=5400,
        help="Cooldown after a normal search-detail checkpoint before resuming.",
    )
    parser.add_argument("--sleep-between-keywords", type=int, default=600)
    parser.add_argument("--sleep-between-batches", type=int, default=300)
    parser.add_argument("--high-volume-comment-threshold", type=int, default=500)
    parser.add_argument("--high-volume-sleep", type=int, default=1200)
    parser.add_argument("--long-cooldown-every", type=int, default=6)
    parser.add_argument("--long-cooldown", type=int, default=1800)
    parser.add_argument("--notes-per-batch", type=int, default=5)
    parser.add_argument("--max-batches", type=int, default=0, help="For selected-comments: run only the first N batches.")
    parser.add_argument("--selected-notes-file", type=Path, default=None)
    parser.add_argument("--selected-notes-per-phase", type=int, default=0)
    parser.add_argument("--selected-phase-ids", default="", help="For selected-comments: comma-separated phase/event ids to include.")
    parser.add_argument("--resume-skip-completed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--login-type", choices=["qrcode", "cookie", "phone"], default="qrcode")
    parser.add_argument("--stop-on-captcha", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--stop-on-empty", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--stop-on-error", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--transient-retries", type=int, default=1, help="Retries for transient network/CDP failures only.")
    parser.add_argument("--transient-retry-delay", type=int, default=600, help="Seconds to wait before a transient retry.")
    parser.add_argument("--command-timeout", type=int, default=0, help="Maximum seconds for one crawler subprocess; 0 disables the limit.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-stage", default="full-recon-comments,deep-comments,recon", help="For author/commenter profiles: comma-separated source stages.")
    parser.add_argument("--notes-file", type=Path, default=None, help="For author-profiles: explicit notes CSV/JSONL with note_url.")
    parser.add_argument("--author-source-limit", type=int, default=0)
    parser.add_argument("--author-post-limit", type=int, default=20)
    parser.add_argument("--commenter-limit", type=int, default=0, help="For commenter-profiles: maximum unique commenters to probe.")
    parser.add_argument("--public-post-limit", type=int, default=50, help="For commenter-profiles: maximum public posts sampled per commenter.")
    parser.add_argument("--author-sleep", type=float, default=2.0)
    parser.add_argument("--browser-timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.manifest = args.manifest.resolve()
    args.run_root = args.run_root.resolve()
    if not MEDIA_CRAWLER_DIR.exists():
        print(f"MediaCrawler directory not found: {MEDIA_CRAWLER_DIR}")
        return 2
    if args.search_card_only and not args.all_search_results:
        print("--search-card-only requires --all-search-results so terminal pagination is auditable.")
        return 2
    if args.collection_egress_region and not args.static_proxy_url and not args.allow_direct_egress:
        print(
            "Regional collection requires --static-proxy-url, or an explicitly verified "
            "--allow-direct-egress path, so browser and API traffic share one egress."
        )
        return 2
    if args.stage in {"selected-details", "selected-comments", "selected-sub-comments"}:
        return collect_selected_comments(args)
    if args.stage == "author-profiles":
        return run_author_profiles(args)
    if args.stage == "commenter-profiles":
        return run_commenter_profiles(args)
    return collect_search_stage(args)


if __name__ == "__main__":
    raise SystemExit(main())
