from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import config
from media_platform.xhs.client import XiaoHongShuClient
from media_platform.xhs.exception import PaginationIncompleteError
from media_platform.xhs.pagination import (
    append_raw_search_result,
    classify_page_times,
    cursor_stop_reason,
    load_existing_content_note_ids,
    parse_boundary_ms,
    search_item_publish_time_ms,
    search_page_checkpoint_decision,
    search_stop_decision,
    take_detail_budget,
)


def ms(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_search_window_and_terminal_last_page():
    status = classify_page_times(
        [{"time": ms("2026-05-04")}, {"time": ms("2026-05-05")}, {"time": ms("2026-08-02")}],
        parse_boundary_ms("2026-05-05"),
        parse_boundary_ms("2026-08-02", end_of_day=True),
    )
    assert status["older_rows"] == 1
    assert status["in_window_rows"] == 2
    assert search_stop_decision(
        has_more=False,
        all_results=True,
        consecutive_old_pages=0,
        old_page_stop_count=2,
        page=3,
        max_pages=200,
    ) == ("endpoint_exhausted", True)


def test_search_page_guard_is_not_complete():
    assert search_stop_decision(
        has_more=True,
        all_results=True,
        consecutive_old_pages=0,
        old_page_stop_count=2,
        page=200,
        max_pages=200,
    ) == ("max_pages_guard", False)


def test_search_page_session_checkpoint_is_resumable_and_not_terminal():
    assert search_page_checkpoint_decision(
        page=18,
        start_page=11,
        session_limit=8,
        terminal_stop_reason="",
    ) == ("session_page_limit", 19)
    assert search_page_checkpoint_decision(
        page=18,
        start_page=11,
        session_limit=8,
        terminal_stop_reason="window_exhausted",
    ) == ("", 0)
    assert search_page_checkpoint_decision(
        page=18,
        start_page=11,
        session_limit=8,
        terminal_stop_reason="",
        overlap_pages=1,
    ) == ("session_page_limit", 18)


def test_raw_search_result_is_landed_before_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    path = append_raw_search_result(
        {
            "keyword": "AI model",
            "page": 3,
            "rank_in_page": 2,
            "note_id": "n1",
            "search_item": {"id": "n1", "note_card": {"display_title": "AI model help"}},
        }
    )
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["note_id"] == "n1"
    assert row["search_item"]["note_card"]["display_title"] == "AI model help"


def test_raw_search_result_includes_regional_collection_context(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    monkeypatch.setenv("XHS_COLLECTION_EGRESS_REGION", "japan")
    monkeypatch.setenv("XHS_COLLECTION_EGRESS_ID", "jp-fixed")
    monkeypatch.setenv("XHS_COLLECTION_ACCOUNT_ID", "account_regional_jp")
    monkeypatch.setenv("XHS_CDP_DEBUG_PORT", "9322")
    path = append_raw_search_result({"keyword": "AI model", "note_id": "n1"})
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["collection_egress_region"] == "japan"
    assert row["collection_egress_id"] == "jp-fixed"
    assert row["collection_account_id"] == "account_regional_jp"
    assert row["collection_cdp_port"] == "9322"


def test_existing_detail_ids_are_loaded_for_cross_process_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    content_path = tmp_path / "xhs" / "jsonl" / "search_contents_2026-08-03.jsonl"
    content_path.parent.mkdir(parents=True)
    content_path.write_text(
        '{"note_id":"n1"}\ninvalid\n{"id":"n2"}\n{"note_id":"n1"}\n',
        encoding="utf-8",
    )
    assert load_existing_content_note_ids() == {"n1", "n2"}


def test_detail_budget_defers_remaining_page_items():
    items = [{"id": f"n{index}"} for index in range(20)]
    selected, deferred = take_detail_budget(items, used=2, limit=18)
    assert len(selected) == 16
    assert [item["id"] for item in deferred] == ["n16", "n17", "n18", "n19"]


def test_search_card_publish_time_supports_relative_and_absolute_labels():
    reference = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc).astimezone()

    def item(label: str) -> dict:
        return {"note_card": {"corner_tag_info": [{"type": "publish_time", "text": label}]}}

    yesterday = search_item_publish_time_ms(item("昨天 23:47"), reference=reference)
    ten_hours = search_item_publish_time_ms(item("10小时前"), reference=reference)
    absolute = search_item_publish_time_ms(item("08-02 12:30"), reference=reference)
    assert yesterday is not None
    assert ten_hours is not None
    assert absolute is not None
    assert yesterday < int(reference.timestamp() * 1000)
    assert ten_hours < int(reference.timestamp() * 1000)


def test_cursor_guard_detects_repeat():
    assert cursor_stop_reason("cursor-1", "cursor-1", True, {"cursor-1"}) == "repeated_cursor"
    assert cursor_stop_reason("cursor-1", "", True, {"cursor-1"}) == "missing_next_cursor"
    assert cursor_stop_reason("cursor-1", "cursor-2", False, {"cursor-1"}) == "endpoint_exhausted"


@pytest.mark.asyncio
async def test_zero_comment_limit_means_unlimited(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(config, "ENABLE_GET_SUB_COMMENTS", False)
    client = object.__new__(XiaoHongShuClient)
    pages = iter(
        [
            {"has_more": True, "cursor": "next", "comments": [{"id": "c1", "note_id": "n1"}]},
            {"has_more": False, "cursor": "", "comments": [{"id": "c2", "note_id": "n1"}]},
        ]
    )

    async def get_note_comments(**_kwargs):
        return next(pages)

    client.get_note_comments = get_note_comments
    rows = await client.get_note_all_comments("n1", "token", crawl_interval=0, max_count=0)
    assert [row["id"] for row in rows] == ["c1", "c2"]
    status_path = tmp_path / "xhs" / "quality" / "comment_pagination_status.jsonl"
    latest = json.loads(status_path.read_text(encoding="utf-8").splitlines()[-1])
    assert latest["status"] == "complete"
    assert latest["observed_comments"] == 2
    assert latest["unlimited"] is True


@pytest.mark.asyncio
async def test_repeated_root_cursor_fails_and_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(config, "ENABLE_GET_SUB_COMMENTS", False)
    client = object.__new__(XiaoHongShuClient)

    async def get_note_comments(**_kwargs):
        return {"has_more": True, "cursor": "", "comments": [{"id": "c1", "note_id": "n1"}]}

    client.get_note_comments = get_note_comments
    with pytest.raises(PaginationIncompleteError):
        await client.get_note_all_comments("n1", "token", crawl_interval=0, max_count=0)
    status_path = tmp_path / "xhs" / "quality" / "comment_pagination_status.jsonl"
    latest = json.loads(status_path.read_text(encoding="utf-8").splitlines()[-1])
    assert latest["status"] == "incomplete"
    assert "missing_next_cursor" in latest["error"]


def test_public_ip_location_is_kept_for_notes_and_comments():
    from store import xhs as xhs_store

    assert xhs_store._extract_public_location({"public_ip_location": ""}, {"ip_location": "上海"}) == "上海"
    assert xhs_store._extract_public_location({"region": "北京"}) == "北京"
