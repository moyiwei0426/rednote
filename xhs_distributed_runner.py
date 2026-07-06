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
        comments_limit = args.comments_per_note or 10000
    elif stage == "pilot-comments":
        get_comment = "true"
        note_limit = args.notes_per_keyword or event.notes_limit_recon
        comments_limit = args.comments_per_note or event.comments_per_note_pilot
    elif stage == "deep-comments":
        get_comment = "true"
        note_limit = args.notes_per_keyword or event.notes_limit_deep
        comments_limit = args.comments_per_note or event.comments_per_note_deep
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
    ]
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
    completed: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("stage") == stage and row.get("status") == "ok" and row.get("output_dir"):
                completed.add(row["output_dir"])
    return completed


def completed_search_keys_from_ledger(path: Path, stage: str) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    completed: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("stage") == stage and row.get("status") == "ok":
                event_id = (row.get("event_id") or "").strip()
                keyword = (row.get("keyword") or "").strip()
                if event_id and keyword:
                    completed.add((event_id, keyword))
    return completed


def output_has_comment_rows(output_dir: Path) -> bool:
    for path in output_dir.glob("xhs/jsonl/*comments*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                return any(line.strip() for line in fh)
        except OSError:
            continue
    return False


def command_to_text(cmd: list[str]) -> str:
    return " ".join(json.dumps(part, ensure_ascii=False) if " " in part else part for part in cmd)


def run_command(cmd: list[str], cwd: Path, log_path: Path, env: dict, dry_run: bool) -> tuple[int, bool]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        log_path.write_text("DRY RUN\n" + command_to_text(cmd) + "\n", encoding="utf-8")
        print(command_to_text(cmd))
        return 0, False

    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + command_to_text(cmd) + "\n\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    text = log_path.read_text(encoding="utf-8", errors="replace")
    captcha = any(marker in text for marker in CAPTCHA_MARKERS)
    return proc.returncode, captcha


def event_matches_device(event: EventRow, device_id: str) -> bool:
    assigned = normalize_device(event.assigned_device)
    device = normalize_device(device_id)
    return assigned in {"", "all", device}


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
    env = os.environ.copy()
    env.setdefault("UV_DEFAULT_INDEX", "https://pypi.org/simple")

    jobs = list(iter_keyword_jobs(events, args.max_keywords))
    print(f"Selected {len(events)} events, {len(jobs)} keyword jobs for stage={args.stage}.")
    completed_search_keys = completed_search_keys_from_ledger(ledger_path, args.stage) if args.resume_skip_completed else set()

    for index, (event, keyword) in enumerate(jobs, start=1):
        started_at = datetime.now().isoformat(timespec="seconds")
        keyword_slug = slug_text(keyword)
        output_dir = run_root / args.stage / event.event_id / keyword_slug
        log_path = output_dir / "crawler.log"
        if (event.event_id, keyword) in completed_search_keys:
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
        }
        write_json(output_dir / "batch_meta.json", meta)
        cmd, cwd = build_media_command(event, keyword, args.stage, output_dir, args)

        print(f"[{index}/{len(jobs)}] {event.event_id} {event.event_name} | {keyword}")
        returncode, captcha = run_command(cmd, cwd, log_path, env, args.dry_run)
        finished_at = datetime.now().isoformat(timespec="seconds")
        status = "dry_run" if args.dry_run else ("ok" if returncode == 0 and not captcha else ("captcha" if captcha else "failed"))
        append_ledger(
            ledger_path,
            {
                "started_at": started_at,
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

        if captcha and args.stop_on_captcha:
            print(f"CAPTCHA detected. Stop now and cool down this account. Log: {log_path}")
            return 86
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
        "true",
        "--get_sub_comment",
        "false",
        "--headless",
        "false",
        "--save_data_option",
        "jsonl",
        "--save_data_path",
        str(output_dir),
        "--crawler_max_notes_count",
        str(len(note_urls)),
        "--max_comments_count_singlenotes",
        str(args.comments_per_note or 80),
        "--max_concurrency_num",
        str(args.max_concurrency),
    ]
    return cmd, cwd


def collect_selected_comments(args: argparse.Namespace) -> int:
    if not args.selected_notes_file:
        print("--selected-notes-file is required for selected-comments stage.")
        return 2
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
    env = os.environ.copy()
    env.setdefault("UV_DEFAULT_INDEX", "https://pypi.org/simple")
    jobs: list[tuple[str, int, list[dict[str, str]]]] = []
    for phase_id, phase_rows in sorted(by_phase.items()):
        for chunk_index, chunk in enumerate(chunked(phase_rows, args.notes_per_batch), start=1):
            jobs.append((phase_id, chunk_index, chunk))
    if args.max_batches:
        jobs = jobs[: args.max_batches]

    print(f"Selected-comments jobs: {len(jobs)} batches, {len(rows)} notes.")
    completed_dirs = completed_output_dirs_from_ledger(ledger_path, "selected-comments") if args.resume_skip_completed else set()
    for index, (phase_id, chunk_index, chunk) in enumerate(jobs, start=1):
        first = chunk[0]
        raw_event_id = first.get("phase_id") or first.get("event_id") or phase_id
        event_name = first.get("phase_name") or first.get("event_name") or raw_event_id
        output_dir = run_root / "selected-comments" / raw_event_id / f"chunk_{chunk_index:03d}"
        log_path = output_dir / "crawler.log"
        if str(output_dir) in completed_dirs or (args.resume_skip_completed and output_has_comment_rows(output_dir)):
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
            "comments_per_note_pilot": args.comments_per_note or 80,
            "comments_per_note_deep": args.comments_per_note or 80,
            "author_post_limit": 0,
            "notes": "selected representative notes comments batch",
        }
        meta = {
            "run_id": args.run_id,
            "device_id": args.device_id,
            "account_id": args.account_id,
            "stage": "selected-comments",
            "event": event_payload,
            "keyword": f"selected_notes_{raw_event_id}_chunk_{chunk_index:03d}",
            "selected_notes": [
                {k: row.get(k, "") for k in ("note_id", "representative_rank_in_phase", "representative_score")}
                for row in chunk
            ],
            "started_at": started_at,
            "output_dir": str(output_dir),
        }
        write_json(output_dir / "batch_meta.json", meta)
        cmd, cwd = build_detail_command([row["note_url"] for row in chunk], output_dir, args)
        print(f"[{index}/{len(jobs)}] {raw_event_id} chunk={chunk_index:03d} notes={len(chunk)}")
        returncode, captcha = run_command(cmd, cwd, log_path, env, args.dry_run)
        finished_at = datetime.now().isoformat(timespec="seconds")
        status = "dry_run" if args.dry_run else ("ok" if returncode == 0 and not captcha else ("captcha" if captcha else "failed"))
        append_ledger(
            ledger_path,
            {
                "started_at": started_at,
                "finished_at": finished_at,
                "device_id": args.device_id,
                "account_id": args.account_id,
                "stage": "selected-comments",
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
        if captcha and args.stop_on_captcha:
            print(f"CAPTCHA detected. Stop now and cool down this account. Log: {log_path}")
            return 86
        if returncode != 0 and args.stop_on_error:
            print(f"Command failed with code {returncode}. Log: {log_path}")
            return returncode
        if index < len(jobs) and args.sleep_between_batches > 0:
            print(f"Sleeping {args.sleep_between_batches}s before next selected-note batch...")
            time.sleep(args.sleep_between_batches)
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
    env = os.environ.copy()
    env.setdefault("UV_DEFAULT_INDEX", "https://pypi.org/simple")
    print(f"Author profile source notes: {len(urls)}")
    returncode, captcha = run_command(cmd, cwd, log_path, env, args.dry_run)
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
    env = os.environ.copy()
    env.setdefault("UV_DEFAULT_INDEX", "https://pypi.org/simple")
    print(f"Commenter profile source notes: {notes_file}")
    returncode, captcha = run_command(cmd, python_cwd, log_path, env, args.dry_run)
    if captcha and args.stop_on_captcha:
        print(f"CAPTCHA detected in commenter profile stage. Log: {log_path}")
        return 86
    print(f"Commenter profile output: {output_dir}")
    return returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Distributed XHS event collection runner.")
    parser.add_argument("--stage", choices=["recon", "full-recon-comments", "pilot-comments", "deep-comments", "selected-comments", "author-profiles", "commenter-profiles"], required=True)
    parser.add_argument("--device-id", required=True, help="A, B, C, or another manifest-assigned device id.")
    parser.add_argument("--account-id", default="", help="Local account label for metadata only, e.g. account_a.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id", default="main_20260704")
    parser.add_argument("--event-ids", default="", help="Comma-separated event ids, e.g. E001,E003.")
    parser.add_argument("--groups", default="", help="Comma-separated collection groups, e.g. core,observe.")
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--max-keywords", type=int, default=0)
    parser.add_argument("--notes-per-keyword", type=int, default=0)
    parser.add_argument("--comments-per-note", type=int, default=0)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--sleep-between-keywords", type=int, default=600)
    parser.add_argument("--sleep-between-batches", type=int, default=300)
    parser.add_argument("--notes-per-batch", type=int, default=5)
    parser.add_argument("--max-batches", type=int, default=0, help="For selected-comments: run only the first N batches.")
    parser.add_argument("--selected-notes-file", type=Path, default=None)
    parser.add_argument("--selected-notes-per-phase", type=int, default=0)
    parser.add_argument("--selected-phase-ids", default="", help="For selected-comments: comma-separated phase/event ids to include.")
    parser.add_argument("--resume-skip-completed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--login-type", choices=["qrcode", "cookie", "phone"], default="qrcode")
    parser.add_argument("--stop-on-captcha", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--stop-on-error", action=argparse.BooleanOptionalAction, default=False)
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
    if args.stage == "selected-comments":
        return collect_selected_comments(args)
    if args.stage == "author-profiles":
        return run_author_profiles(args)
    if args.stage == "commenter-profiles":
        return run_commenter_profiles(args)
    return collect_search_stage(args)


if __name__ == "__main__":
    raise SystemExit(main())
