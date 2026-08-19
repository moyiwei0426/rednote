from __future__ import annotations

import argparse
import json
from pathlib import Path

import xhs_distributed_runner as runner


def event() -> runner.EventRow:
    return runner.EventRow(
        event_id="E020",
        event_name="AI model selection",
        event_date="",
        country_group="Application",
        brand="Mixed",
        assigned_device="A",
        priority=1,
        collection_group="top10_full_comments",
        enabled=True,
        keywords=["AI model"],
        analysis_window_start="2026-05-05",
        analysis_window_end="2026-08-02",
        notes_limit_recon=0,
        notes_limit_deep=0,
        comments_per_note_pilot=0,
        comments_per_note_deep=0,
        author_post_limit=0,
        notes="",
    )


def args(**overrides):
    values = {
        "notes_per_keyword": 0,
        "comments_per_note": 0,
        "max_concurrency": 1,
        "page_sleep": 15,
        "search_page_cooldown": 300,
        "search_detail_session_limit": 8,
        "search_page_session_limit": 0,
        "search_card_only": False,
        "all_search_results": True,
        "search_sort": "latest",
        "window_start": "2026-05-05",
        "window_end": "2026-08-02",
        "max_search_pages": 200,
        "stage": "recon",
        "login_type": "qrcode",
        "static_proxy_url": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def option_value(command: list[str], option: str) -> str:
    return command[command.index(option) + 1]


def test_recon_command_uses_exhaustive_time_window(tmp_path):
    command, _cwd = runner.build_media_command(
        event(),
        "AI model",
        "recon",
        tmp_path,
        args(),
        search_start_page=4,
    )
    assert option_value(command, "--xhs_search_all_results") == "true"
    assert option_value(command, "--xhs_search_sort") == "time_descending"
    assert option_value(command, "--xhs_search_window_start") == "2026-05-05"
    assert option_value(command, "--xhs_search_window_end") == "2026-08-02"
    assert option_value(command, "--xhs_search_max_pages") == "200"
    assert option_value(command, "--xhs_search_page_cooldown_sec") == "300"
    assert option_value(command, "--xhs_search_detail_session_limit") == "8"
    assert option_value(command, "--xhs_search_page_session_limit") == "0"
    assert option_value(command, "--start") == "4"


def test_search_checkpoint_resumes_from_recorded_page(tmp_path):
    quality = tmp_path / "xhs" / "quality"
    quality.mkdir(parents=True)
    (quality / "search_pagination_status.jsonl").write_text(
        json.dumps(
            {
                "page": 4,
                "status": "checkpoint",
                "stop_reason": "session_detail_limit",
                "resume_page": 4,
                "complete": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert runner.search_resume_page(tmp_path) == 4


def test_running_search_checkpoint_resumes_after_last_successful_page(tmp_path):
    quality = tmp_path / "xhs" / "quality"
    quality.mkdir(parents=True)
    (quality / "search_pagination_status.jsonl").write_text(
        json.dumps(
            {
                "page": 10,
                "status": "running",
                "stop_reason": "",
                "complete": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert runner.search_resume_page(tmp_path) == 11


def test_failed_search_page_is_retried_from_same_page(tmp_path):
    quality = tmp_path / "xhs" / "quality"
    quality.mkdir(parents=True)
    (quality / "search_pagination_status.jsonl").write_text(
        json.dumps(
            {
                "page": 11,
                "status": "incomplete",
                "stop_reason": "data_fetch_error",
                "complete": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert runner.search_resume_page(tmp_path) == 11


def test_subprocess_captcha_checkpoint_is_auditable_and_resumes_same_page(tmp_path):
    path = runner.append_search_failure_checkpoint(
        tmp_path,
        keyword="AI model",
        page=16,
        failure_kind="captcha",
        context={"collection_egress_region": "singapore"},
    )

    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["status"] == "incomplete"
    assert row["stop_reason"] == "captcha"
    assert row["resume_page"] == 16
    assert row["source"] == "xhs_distributed_runner"
    assert row["collection_egress_region"] == "singapore"
    assert runner.search_resume_page(tmp_path) == 16


def test_latest_search_page_is_recovered_from_crawler_log(tmp_path):
    log_path = tmp_path / "crawler.log"
    log_path.write_text(
        "search Xiaohongshu keyword: AI model, page: 1\n"
        "Sleeping for 300 seconds after page 1\n"
        "search Xiaohongshu keyword: AI model, page: 2\n"
        "CAPTCHA appeared, request failed, Verifytype: 216\n",
        encoding="utf-8",
    )

    assert runner.latest_search_page_from_log(log_path) == 2


def test_regional_card_only_command_uses_static_proxy_without_secret_on_command_line(tmp_path):
    command, _cwd = runner.build_media_command(
        event(),
        "AI model",
        "recon",
        tmp_path,
        args(search_card_only=True, static_proxy_url="http://user:secret@127.0.0.1:7897"),
    )
    assert option_value(command, "--xhs_search_card_only") == "true"
    assert option_value(command, "--enable_ip_proxy") == "true"
    assert option_value(command, "--ip_proxy_provider_name") == "static"
    assert "secret" not in " ".join(command)


def test_regional_environment_records_provenance_and_removes_xhs_bypass(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,.xiaohongshu.com,.rednote.com")
    env = runner.build_crawler_env(
        args(
            account_id="account_regional_jp",
            collection_egress_region="japan",
            collection_egress_id="jp-fixed",
            cdp_debug_port=9322,
            static_proxy_url="http://127.0.0.1:7897",
        )
    )
    assert env["XHS_COLLECTION_EGRESS_REGION"] == "japan"
    assert env["XHS_COLLECTION_EGRESS_ID"] == "jp-fixed"
    assert env["XHS_COLLECTION_ACCOUNT_ID"] == "account_regional_jp"
    assert env["XHS_CDP_DEBUG_PORT"] == "9322"
    assert env["XHS_STATIC_PROXY_URL"] == "http://127.0.0.1:7897"
    assert "xiaohongshu" not in env["NO_PROXY"]
    assert "rednote" not in env["NO_PROXY"]


def test_detail_command_preserves_zero_as_unlimited(tmp_path):
    command, _cwd = runner.build_detail_command(
        ["https://www.xiaohongshu.com/explore/n1?xsec_token=t"],
        tmp_path,
        args(stage="selected-sub-comments"),
    )
    assert option_value(command, "--max_comments_count_singlenotes") == "0"
    assert option_value(command, "--get_sub_comment") == "true"


def test_selected_details_command_disables_comment_collection(tmp_path):
    command, _cwd = runner.build_detail_command(
        ["https://www.xiaohongshu.com/explore/n1?xsec_token=t"],
        tmp_path,
        args(stage="selected-details"),
    )
    assert option_value(command, "--get_comment") == "false"
    assert option_value(command, "--get_sub_comment") == "false"


def test_selected_detail_completion_requires_expected_note_content(tmp_path):
    (tmp_path / "xhs" / "jsonl").mkdir(parents=True)
    (tmp_path / "batch_meta.json").write_text(
        json.dumps({"selected_notes": [{"note_id": "n1"}, {"note_id": "n2"}]}),
        encoding="utf-8",
    )
    contents = tmp_path / "xhs" / "jsonl" / "detail_contents.jsonl"
    contents.write_text(json.dumps({"note_id": "n1"}) + "\n", encoding="utf-8")
    assert not runner.selected_detail_output_complete(tmp_path)
    contents.write_text(
        json.dumps({"note_id": "n1"}) + "\n" + json.dumps({"note_id": "n2"}) + "\n",
        encoding="utf-8",
    )
    assert runner.selected_detail_output_complete(tmp_path)


def test_pagination_status_is_required_for_new_batches(tmp_path):
    quality = tmp_path / "xhs" / "quality"
    quality.mkdir(parents=True)
    path = quality / "comment_pagination_status.jsonl"
    path.write_text(
        json.dumps({"kind": "top_level", "note_id": "n1", "status": "complete"}) + "\n"
        + json.dumps({"kind": "reply", "note_id": "n1", "root_comment_id": "c1", "status": "complete"}) + "\n",
        encoding="utf-8",
    )
    assert runner.comment_pagination_complete(tmp_path, "selected-sub-comments")
    path.write_text(
        path.read_text(encoding="utf-8")
        + json.dumps({"kind": "reply", "note_id": "n1", "root_comment_id": "c1", "status": "incomplete"})
        + "\n",
        encoding="utf-8",
    )
    assert not runner.comment_pagination_complete(tmp_path, "selected-sub-comments")


def test_login_timeout_and_network_failures_are_classified(tmp_path):
    log_path = tmp_path / "crawler.log"
    log_path.write_text("登录已过期\n", encoding="utf-8")
    assert runner.classify_failure(log_path, 1, False) == "login_expired"

    log_path.write_text("Command timeout after 600s; terminating crawler subprocess.\n", encoding="utf-8")
    assert runner.classify_failure(log_path, 124, False) == "transient_network"

    log_path.write_text("httpx.RemoteProtocolError: server disconnected\n", encoding="utf-8")
    assert runner.classify_failure(log_path, 1, False) == "transient_network"


def test_empty_search_and_partial_comments_are_not_complete(tmp_path):
    quality = tmp_path / "xhs" / "quality"
    quality.mkdir(parents=True)
    search_status = quality / "search_pagination_status.jsonl"
    search_status.write_text(
        json.dumps(
            {
                "keyword": "AI model",
                "page": 4,
                "status": "incomplete",
                "stop_reason": "empty_response",
                "complete": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert runner.latest_search_pagination_status(tmp_path)["complete"] is False

    comment_status = quality / "comment_pagination_status.jsonl"
    comment_status.write_text(
        json.dumps({"kind": "top_level", "note_id": "n1", "status": "complete"})
        + "\n"
        + json.dumps(
            {
                "kind": "reply",
                "note_id": "n1",
                "root_comment_id": "c1",
                "status": "incomplete",
                "observed_comments": 3,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert not runner.comment_pagination_complete(tmp_path, "selected-sub-comments")


def test_partial_attempt_is_moved_to_quarantine(tmp_path, monkeypatch):
    run_root = tmp_path / "run" / "device_a"
    output = run_root / "selected-sub-comments" / "E020" / "chunk_001"
    output.mkdir(parents=True)
    (output / "partial.jsonl").write_text('{"comment_id":"c1"}\n', encoding="utf-8")
    monkeypatch.setattr(runner, "now_stamp", lambda: "20260802_120000")

    quarantined = runner.quarantine_incomplete_output(output, run_root, 1)
    assert quarantined == tmp_path / "run" / "incomplete_attempts_20260802_120000_retry1" / "selected-sub-comments" / "E020" / "chunk_001"
    assert quarantined.exists()
    assert not output.exists()


def test_quarantined_search_checkpoint_is_restored_for_resume(tmp_path):
    run_root = tmp_path / "run" / "device_a"
    output = run_root / "recon" / "E020" / "ai_model"
    checkpoint = (
        run_root.parent
        / "incomplete_attempts_20260806_133645_retry1"
        / "recon"
        / "E020"
        / "ai_model"
    )
    quality = checkpoint / "xhs" / "quality"
    raw = checkpoint / "xhs" / "raw"
    quality.mkdir(parents=True)
    raw.mkdir(parents=True)
    (quality / "search_pagination_status.jsonl").write_text(
        json.dumps({"page": 10, "status": "running", "stop_reason": "", "complete": False}) + "\n",
        encoding="utf-8",
    )
    (raw / "search_results.jsonl").write_text('{"note_id":"n1"}\n', encoding="utf-8")

    restored = runner.restore_search_checkpoint(output, run_root)

    assert restored == checkpoint
    assert runner.search_resume_page(output) == 11
    assert (output / "xhs" / "raw" / "search_results.jsonl").read_text(encoding="utf-8") == '{"note_id":"n1"}\n'
    marker = json.loads((output / "checkpoint_restore.json").read_text(encoding="utf-8"))
    assert marker["source"] == str(checkpoint)
    assert marker["resume_page"] == 11


def test_raw_search_jsonl_counts_as_partial_output(tmp_path):
    raw = tmp_path / "xhs" / "raw" / "search_results.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text('{"note_id":"n1"}\n', encoding="utf-8")
    assert runner.output_has_any_jsonl_rows(tmp_path)
    assert not runner.output_has_jsonl_rows(tmp_path)
    assert runner.output_has_search_rows(tmp_path)


def test_page_capped_pilot_promotes_raw_search_output_without_claiming_endpoint_exhaustion(tmp_path):
    raw = tmp_path / "xhs" / "raw" / "search_results.jsonl"
    quality = tmp_path / "xhs" / "quality" / "search_pagination_status.jsonl"
    raw.parent.mkdir(parents=True)
    quality.parent.mkdir(parents=True)
    raw.write_text('{"note_id":"n1"}\n', encoding="utf-8")
    quality.write_text(
        json.dumps(
            {
                "keyword": "Gaokao day one",
                "page": 5,
                "status": "incomplete",
                "stop_reason": "max_pages_guard",
                "complete": False,
                "max_pages": 5,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert runner.promote_pilot_page_limit(
        tmp_path,
        keyword="Gaokao day one",
        context={"collection_egress_region": "singapore"},
    )
    latest = runner.latest_search_pagination_status(tmp_path)
    assert latest["complete"] is True
    assert latest["status"] == "complete"
    assert latest["stop_reason"] == "pilot_page_limit"
    assert latest["pilot_scope"] is True
    assert latest["collection_egress_region"] == "singapore"
    assert runner.pilot_search_output_complete(tmp_path)
