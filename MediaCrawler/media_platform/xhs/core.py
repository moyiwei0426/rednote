# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/xhs/core.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。

import asyncio
import os
import random
from asyncio import Task
from typing import Dict, List, Optional

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)
from tenacity import RetryError

import config
from base.base_crawler import AbstractCrawler
from model.m_xiaohongshu import NoteUrlInfo, CreatorUrlInfo
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import xhs as xhs_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var

from .client import XiaoHongShuClient
from .exception import DataFetchError, NoteNotFoundError
from .field import SearchSortType
from .help import parse_note_info_from_note_url, parse_creator_info_from_url, get_search_id
from .login import XiaoHongShuLogin
from .pagination import (
    append_quality_status,
    append_raw_search_result,
    classify_page_times,
    load_existing_content_note_ids,
    parse_boundary_ms,
    search_item_publish_time_ms,
    search_page_checkpoint_decision,
    search_stop_decision,
    take_detail_budget,
)


class XiaoHongShuCrawler(AbstractCrawler):
    context_page: Page
    xhs_client: XiaoHongShuClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self) -> None:
        self.index_url = "https://www.rednote.com" if config.XHS_INTERNATIONAL else "https://www.xiaohongshu.com"
        self.cookie_urls = [self.index_url]
        # self.user_agent = utils.get_user_agent()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        self.cdp_manager = None
        self.ip_proxy_pool = None  # Proxy IP pool for automatic proxy refresh

    async def start(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            self.ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await self.ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # Choose launch mode based on configuration
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[XiaoHongShuCrawler] Launching browser using CDP mode")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[XiaoHongShuCrawler] Launching browser using standard mode")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.HEADLESS,
                )
                # stealth.min.js is only needed for the standard Playwright context.
                await self.browser_context.add_init_script(path="libs/stealth.min.js")
            if os.getenv("XHS_DISABLE_GEOLOCATION", "").strip().lower() in {"1", "true", "yes"}:
                await self.browser_context.clear_permissions()
                utils.logger.info("[XiaoHongShuCrawler] Cleared browser permissions for regional collection")

            # A reused CDP browser already has an authenticated XHS page. Reuse it
            # instead of making every batch wait for the root page to finish loading.
            existing_page = next(
                (
                    page
                    for page in self.browser_context.pages
                    if not page.is_closed() and page.url.startswith(self.index_url)
                ),
                None,
            )
            if existing_page is not None:
                self.context_page = existing_page
            else:
                self.context_page = await self.browser_context.new_page()
                try:
                    await self.context_page.goto(
                        self.index_url,
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                except Exception as exc:
                    utils.logger.warning(
                        "[XiaoHongShuCrawler] Index page navigation timed out; "
                        "continuing with the current browser context: %s",
                        exc,
                    )

            # Create a client to interact with the Xiaohongshu website.
            self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
            if not await self.xhs_client.pong():
                login_obj = XiaoHongShuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.xhs_client.update_cookies(
                    browser_context=self.browser_context,
                    urls=self.cookie_urls,
                )

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            else:
                pass

            utils.logger.info("[XiaoHongShuCrawler.start] Xhs Crawler finished ...")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        utils.logger.info("[XiaoHongShuCrawler.search] Begin search Xiaohongshu keywords")
        xhs_limit_count = 20  # Xiaohongshu limit page fixed value
        all_results = bool(getattr(config, "XHS_SEARCH_ALL_RESULTS", False))
        max_pages = max(1, int(getattr(config, "XHS_SEARCH_MAX_PAGES", 200)))
        old_page_stop_count = max(1, int(getattr(config, "XHS_SEARCH_OLD_PAGE_STOP_COUNT", 2)))
        detail_session_limit = max(0, int(getattr(config, "XHS_SEARCH_DETAIL_SESSION_LIMIT", 8)))
        page_session_limit = max(0, int(getattr(config, "XHS_SEARCH_PAGE_SESSION_LIMIT", 0)))
        card_only = bool(getattr(config, "XHS_SEARCH_CARD_ONLY", False))
        page_cooldown_sec = max(
            config.CRAWLER_MAX_SLEEP_SEC,
            int(getattr(config, "XHS_SEARCH_PAGE_COOLDOWN_SEC", 300)),
        )
        window_start_ms = parse_boundary_ms(getattr(config, "XHS_SEARCH_WINDOW_START", ""))
        window_end_ms = parse_boundary_ms(
            getattr(config, "XHS_SEARCH_WINDOW_END", ""),
            end_of_day=True,
        )
        if not all_results and config.CRAWLER_MAX_NOTES_COUNT < xhs_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = xhs_limit_count
        start_page = config.START_PAGE
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(f"[XiaoHongShuCrawler.search] Current search keyword: {keyword}")
            page = 1
            search_id = get_search_id()
            consecutive_old_pages = 0
            existing_detail_ids = load_existing_content_note_ids()
            seen_note_ids: set[str] = set(existing_detail_ids)
            seen_search_note_ids: set[str] = set()
            session_detail_attempts = 0
            utils.logger.info(
                "[XiaoHongShuCrawler.search] Loaded %s existing details; session request limit=%s; card_only=%s",
                len(existing_detail_ids),
                detail_session_limit or "unlimited",
                card_only,
            )
            while True:
                if page < start_page:
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Skip page {page}")
                    page += 1
                    continue

                if all_results:
                    if page > max_pages:
                        append_quality_status(
                            "search_pagination_status.jsonl",
                            {
                                "keyword": keyword,
                                "page": page - 1,
                                "status": "incomplete",
                                "stop_reason": "max_pages_guard",
                                "complete": False,
                                "max_pages": max_pages,
                            },
                        )
                        break
                elif (page - start_page + 1) * xhs_limit_count > config.CRAWLER_MAX_NOTES_COUNT:
                    break

                try:
                    utils.logger.info(f"[XiaoHongShuCrawler.search] search Xiaohongshu keyword: {keyword}, page: {page}")
                    note_ids: List[str] = []
                    xsec_tokens: List[str] = []
                    notes_res = await self.xhs_client.get_note_by_keyword(
                        keyword=keyword,
                        search_id=search_id,
                        page=page,
                        sort=(SearchSortType(config.SORT_TYPE) if config.SORT_TYPE != "" else SearchSortType.GENERAL),
                    )
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Search notes response: {notes_res}")
                    if not notes_res:
                        append_quality_status(
                            "search_pagination_status.jsonl",
                            {
                                "keyword": keyword,
                                "page": page,
                                "status": "incomplete",
                                "stop_reason": "empty_response",
                                "complete": False,
                            },
                        )
                        utils.logger.error("[XiaoHongShuCrawler.search] Empty search response")
                        break
                    has_more = bool(notes_res.get("has_more", False))
                    items = [
                        item
                        for item in notes_res.get("items", [])
                        if item.get("model_type") not in ("rec_query", "hot_query")
                    ]
                    detail_items = []
                    card_time_rows = []
                    skipped_newer_ids = []
                    skipped_duplicate_ids = []
                    skipped_existing_detail_ids = []
                    for rank, item in enumerate(items, start=1):
                        note_id = str(item.get("id") or "")
                        search_publish_time_ms = search_item_publish_time_ms(item)
                        card_time_rows.append({"time": search_publish_time_ms})
                        append_raw_search_result(
                            {
                                "keyword": keyword,
                                "search_id": search_id,
                                "page": page,
                                "rank_in_page": rank,
                                "has_more": has_more,
                                "note_id": note_id,
                                "xsec_token": item.get("xsec_token"),
                                "xsec_source": item.get("xsec_source"),
                                "model_type": item.get("model_type"),
                                "search_publish_time_ms": search_publish_time_ms,
                                "search_item": item,
                            }
                        )
                        if not note_id:
                            continue
                        if note_id in seen_search_note_ids:
                            skipped_duplicate_ids.append(note_id)
                            continue
                        seen_search_note_ids.add(note_id)
                        if note_id in existing_detail_ids:
                            skipped_existing_detail_ids.append(note_id)
                            continue
                        if (
                            window_end_ms is not None
                            and search_publish_time_ms is not None
                            and search_publish_time_ms > window_end_ms
                        ):
                            skipped_newer_ids.append(note_id)
                            continue
                        detail_items.append(item)
                    if card_only:
                        fetch_items, deferred_items = [], []
                    else:
                        fetch_items, deferred_items = take_detail_budget(
                            detail_items,
                            session_detail_attempts,
                            detail_session_limit,
                        )
                    semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
                    task_list = [
                        self.get_note_detail_async_task(
                            note_id=post_item.get("id"),
                            xsec_source=post_item.get("xsec_source"),
                            xsec_token=post_item.get("xsec_token"),
                            semaphore=semaphore,
                        ) for post_item in fetch_items
                    ]
                    note_details = await asyncio.gather(*task_list)
                    session_detail_attempts += len(fetch_items)
                    valid_note_details = []
                    for note_detail in note_details:
                        if note_detail:
                            await xhs_store.update_xhs_note(note_detail)
                            await self.get_notice_media(note_detail)
                            note_id = str(note_detail.get("note_id") or "")
                            if note_id in seen_note_ids:
                                continue
                            seen_note_ids.add(note_id)
                            valid_note_details.append(note_detail)
                            note_ids.append(note_id)
                            xsec_tokens.append(note_detail.get("xsec_token"))
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Note details: {note_details}")
                    await self.batch_get_note_comments(note_ids, xsec_tokens)

                    page_time_status = classify_page_times(
                        card_time_rows if card_only else valid_note_details,
                        window_start_ms,
                        window_end_ms,
                    )
                    if all_results and page_time_status["all_known_rows_older"]:
                        consecutive_old_pages += 1
                    else:
                        consecutive_old_pages = 0

                    stop_reason, complete = search_stop_decision(
                        has_more=has_more,
                        all_results=all_results,
                        consecutive_old_pages=consecutive_old_pages,
                        old_page_stop_count=old_page_stop_count,
                        page=page,
                        max_pages=max_pages,
                    )
                    resume_page = 0
                    if not card_only and deferred_items:
                        stop_reason = "session_detail_limit"
                        complete = False
                        resume_page = page
                    elif (
                        not card_only
                        and not stop_reason
                        and detail_session_limit > 0
                        and session_detail_attempts >= detail_session_limit
                    ):
                        stop_reason = "session_detail_limit"
                        complete = False
                        resume_page = page + 1
                    page_checkpoint_reason, page_checkpoint_resume = search_page_checkpoint_decision(
                        page=page,
                        start_page=start_page,
                        session_limit=page_session_limit,
                        terminal_stop_reason=stop_reason,
                        overlap_pages=1 if card_only else 0,
                    )
                    if page_checkpoint_reason:
                        stop_reason = page_checkpoint_reason
                        complete = False
                        resume_page = page_checkpoint_resume

                    append_quality_status(
                        "search_pagination_status.jsonl",
                        {
                            "keyword": keyword,
                            "page": page,
                            "status": (
                                "complete"
                                if complete
                                else ("checkpoint" if stop_reason == "session_detail_limit" else ("incomplete" if stop_reason else "running"))
                            ),
                            "stop_reason": stop_reason,
                            "complete": complete,
                            "has_more": has_more,
                            "returned_items": len(items),
                            "detail_rows": len(valid_note_details),
                            "detail_failed_ids": [
                                str(item.get("id") or "")
                                for item, detail in zip(fetch_items, note_details)
                                if not detail
                            ],
                            "detail_candidates": len(detail_items),
                            "detail_attempted_ids": [str(item.get("id") or "") for item in fetch_items],
                            "detail_deferred_ids": [str(item.get("id") or "") for item in deferred_items],
                            "session_detail_attempts": session_detail_attempts,
                            "detail_session_limit": detail_session_limit,
                            "session_pages": page - start_page + 1,
                            "page_session_limit": page_session_limit,
                            "card_only": card_only,
                            "resume_page": resume_page,
                            "skipped_newer_ids": skipped_newer_ids,
                            "skipped_duplicate_ids": skipped_duplicate_ids,
                            "skipped_existing_detail_ids": skipped_existing_detail_ids,
                            "existing_detail_rows": len(existing_detail_ids),
                            "unique_notes_seen": len(seen_search_note_ids) if card_only else len(seen_note_ids),
                            "consecutive_old_pages": consecutive_old_pages,
                            **page_time_status,
                        },
                    )

                    if stop_reason:
                        utils.logger.info(
                            "[XiaoHongShuCrawler.search] Stop keyword=%s reason=%s complete=%s",
                            keyword,
                            stop_reason,
                            complete,
                        )
                        break

                    # Sleep after each page navigation
                    page_sleep = page_cooldown_sec if all_results else config.CRAWLER_MAX_SLEEP_SEC
                    await asyncio.sleep(page_sleep)
                    utils.logger.info(f"[XiaoHongShuCrawler.search] Sleeping for {page_sleep} seconds after page {page}")
                    page += 1
                except DataFetchError as exc:
                    append_quality_status(
                        "search_pagination_status.jsonl",
                        {
                            "keyword": keyword,
                            "page": page,
                            "status": "incomplete",
                            "stop_reason": "data_fetch_error",
                            "complete": False,
                            "error": str(exc),
                        },
                    )
                    utils.logger.error("[XiaoHongShuCrawler.search] Get note detail error: %s", exc)
                    raise

    async def get_creators_and_notes(self) -> None:
        """Get creator's notes and retrieve their comment information."""
        utils.logger.info("[XiaoHongShuCrawler.get_creators_and_notes] Begin get Xiaohongshu creators")
        for creator_url in config.XHS_CREATOR_ID_LIST:
            try:
                # Parse creator URL to get user_id and security tokens
                creator_info: CreatorUrlInfo = parse_creator_info_from_url(creator_url)
                utils.logger.info(f"[XiaoHongShuCrawler.get_creators_and_notes] Parse creator URL info: {creator_info}")
                user_id = creator_info.user_id

                # get creator detail info from web html content
                createor_info: Dict = await self.xhs_client.get_creator_info(
                    user_id=user_id,
                    xsec_token=creator_info.xsec_token,
                    xsec_source=creator_info.xsec_source
                )
                if createor_info:
                    await xhs_store.save_creator(user_id, creator=createor_info)
            except ValueError as e:
                utils.logger.error(f"[XiaoHongShuCrawler.get_creators_and_notes] Failed to parse creator URL: {e}")
                continue

            # Use fixed crawling interval
            crawl_interval = config.CRAWLER_MAX_SLEEP_SEC
            # Get all note information of the creator
            all_notes_list = await self.xhs_client.get_all_notes_by_creator(
                user_id=user_id,
                crawl_interval=crawl_interval,
                callback=self.fetch_creator_notes_detail,
                xsec_token=creator_info.xsec_token,
                xsec_source=creator_info.xsec_source,
            )

            note_ids = []
            xsec_tokens = []
            for note_item in all_notes_list:
                note_ids.append(note_item.get("note_id"))
                xsec_tokens.append(note_item.get("xsec_token"))
            await self.batch_get_note_comments(note_ids, xsec_tokens)

    async def fetch_creator_notes_detail(self, note_list: List[Dict]):
        """Concurrently obtain the specified post list and save the data"""
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list = [
            self.get_note_detail_async_task(
                note_id=post_item.get("note_id"),
                xsec_source=post_item.get("xsec_source"),
                xsec_token=post_item.get("xsec_token"),
                semaphore=semaphore,
            ) for post_item in note_list
        ]

        note_details = await asyncio.gather(*task_list)
        for note_detail in note_details:
            if note_detail:
                await xhs_store.update_xhs_note(note_detail)
                await self.get_notice_media(note_detail)

    async def get_specified_notes(self):
        """Get the information and comments of the specified post

        Note: Must specify note_id, xsec_source, xsec_token
        """
        get_note_detail_task_list = []
        for full_note_url in config.XHS_SPECIFIED_NOTE_URL_LIST:
            note_url_info: NoteUrlInfo = parse_note_info_from_note_url(full_note_url)
            utils.logger.info(f"[XiaoHongShuCrawler.get_specified_notes] Parse note url info: {note_url_info}")
            crawler_task = self.get_note_detail_async_task(
                note_id=note_url_info.note_id,
                xsec_source=note_url_info.xsec_source,
                xsec_token=note_url_info.xsec_token,
                semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_note_ids = []
        xsec_tokens = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for note_detail in note_details:
            if note_detail:
                need_get_comment_note_ids.append(note_detail.get("note_id", ""))
                xsec_tokens.append(note_detail.get("xsec_token", ""))
                await xhs_store.update_xhs_note(note_detail)
                await self.get_notice_media(note_detail)
        await self.batch_get_note_comments(need_get_comment_note_ids, xsec_tokens)

    async def get_note_detail_async_task(
        self,
        note_id: str,
        xsec_source: str,
        xsec_token: str,
        semaphore: asyncio.Semaphore,
    ) -> Optional[Dict]:
        """Get note detail

        Args:
            note_id:
            xsec_source:
            xsec_token:
            semaphore:

        Returns:
            Dict: note detail
        """
        note_detail = None
        utils.logger.info(f"[get_note_detail_async_task] Begin get note detail, note_id: {note_id}")
        async with semaphore:
            try:
                try:
                    note_detail = await self.xhs_client.get_note_by_id(note_id, xsec_source, xsec_token)
                except RetryError:
                    pass

                if not note_detail:
                    note_detail = await self.xhs_client.get_note_by_id_from_html(note_id, xsec_source, xsec_token,
                                                                                 enable_cookie=True)
                    if not note_detail:
                        utils.logger.warning(f"[skip] Failed to get note detail, Id: {note_id}, 跳过继续")
                        return None

                note_detail.update({"xsec_token": xsec_token, "xsec_source": xsec_source})

                # Sleep after fetching note detail
                await asyncio.sleep(config.CRAWLER_MAX_SLEEP_SEC)
                utils.logger.info(f"[get_note_detail_async_task] Sleeping for {config.CRAWLER_MAX_SLEEP_SEC} seconds after fetching note {note_id}")

                return note_detail

            except NoteNotFoundError as ex:
                utils.logger.warning(f"[XiaoHongShuCrawler.get_note_detail_async_task] Note not found: {note_id}, {ex}")
                return None
            except DataFetchError as ex:
                utils.logger.error(f"[XiaoHongShuCrawler.get_note_detail_async_task] Get note detail error: {ex}")
                return None
            except KeyError as ex:
                utils.logger.error(f"[XiaoHongShuCrawler.get_note_detail_async_task] have not fund note detail note_id:{note_id}, err: {ex}")
                return None

    async def batch_get_note_comments(self, note_list: List[str], xsec_tokens: List[str]):
        """Batch get note comments"""
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(f"[XiaoHongShuCrawler.batch_get_note_comments] Crawling comment mode is not enabled")
            return

        utils.logger.info(f"[XiaoHongShuCrawler.batch_get_note_comments] Begin batch get note comments, note list: {note_list}")
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for index, note_id in enumerate(note_list):
            task = asyncio.create_task(
                self.get_comments(note_id=note_id, xsec_token=xsec_tokens[index], semaphore=semaphore),
                name=note_id,
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(self, note_id: str, xsec_token: str, semaphore: asyncio.Semaphore):
        """Get note comments with keyword filtering and quantity limitation"""
        async with semaphore:
            utils.logger.info(f"[XiaoHongShuCrawler.get_comments] Begin get note id comments {note_id}")
            # Use fixed crawling interval
            crawl_interval = config.CRAWLER_MAX_SLEEP_SEC
            await self.xhs_client.get_note_all_comments(
                note_id=note_id,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=xhs_store.batch_update_xhs_note_comments,
                max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
            )

            # Sleep after fetching comments
            await asyncio.sleep(crawl_interval)
            utils.logger.info(f"[XiaoHongShuCrawler.get_comments] Sleeping for {crawl_interval} seconds after fetching comments for note {note_id}")

    async def create_xhs_client(self, httpx_proxy: Optional[str]) -> XiaoHongShuClient:
        """Create Xiaohongshu client"""
        utils.logger.info("[XiaoHongShuCrawler.create_xhs_client] Begin create Xiaohongshu API client ...")
        cookie_str, cookie_dict = await utils.convert_browser_context_cookies(
            self.browser_context,
            urls=self.cookie_urls,
        )
        xhs_client_obj = XiaoHongShuClient(
            proxy=httpx_proxy,
            headers={
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "content-type": "application/json;charset=UTF-8",
                "origin": self.index_url,
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": f"{self.index_url}/",
                "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
                "Cookie": cookie_str,
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
            proxy_ip_pool=self.ip_proxy_pool,  # Pass proxy pool for automatic refresh
        )
        return xhs_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info("[XiaoHongShuCrawler.launch_browser] Begin create browser context ...")
        if config.SAVE_LOGIN_STATE:
            # feat issue #14
            # we will save login state to avoid login every time
            user_data_dir = os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                headless=headless,
                proxy=playwright_proxy,  # type: ignore
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                user_agent=user_agent,
            )
            return browser_context
        else:
            browser = await chromium.launch(headless=headless, proxy=playwright_proxy)  # type: ignore
            browser_context = await browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=user_agent)
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser using CDP mode"""
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # Display browser information
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[XiaoHongShuCrawler] CDP browser info: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(f"[XiaoHongShuCrawler] CDP mode launch failed, falling back to standard mode: {e}")
            # Fall back to standard mode
            chromium = playwright.chromium
            return await self.launch_browser(chromium, playwright_proxy, user_agent, headless)

    async def close(self):
        """Close browser context"""
        # Special handling if using CDP mode
        if self.cdp_manager:
            await self.cdp_manager.cleanup()
            self.cdp_manager = None
        else:
            await self.browser_context.close()
        utils.logger.info("[XiaoHongShuCrawler.close] Browser context closed ...")

    async def get_notice_media(self, note_detail: Dict):
        if not config.ENABLE_GET_MEIDAS:
            utils.logger.info(f"[XiaoHongShuCrawler.get_notice_media] Crawling image mode is not enabled")
            return
        await self.get_note_images(note_detail)
        await self.get_notice_video(note_detail)

    async def get_note_images(self, note_item: Dict):
        """Get note images. Please use get_notice_media

        Args:
            note_item: Note item dictionary
        """
        if not config.ENABLE_GET_MEIDAS:
            return
        note_id = note_item.get("note_id")
        image_list: List[Dict] = note_item.get("image_list", [])

        for img in image_list:
            if img.get("url_default") != "":
                img.update({"url": img.get("url_default")})

        if not image_list:
            return
        picNum = 0
        for pic in image_list:
            url = pic.get("url")
            if not url:
                continue
            content = await self.xhs_client.get_note_media(url)
            await asyncio.sleep(random.random())
            if content is None:
                continue
            extension_file_name = f"{picNum}.jpg"
            picNum += 1
            await xhs_store.update_xhs_note_image(note_id, content, extension_file_name)

    async def get_notice_video(self, note_item: Dict):
        """Get note videos. Please use get_notice_media

        Args:
            note_item: Note item dictionary
        """
        if not config.ENABLE_GET_MEIDAS:
            return
        note_id = note_item.get("note_id")

        videos = xhs_store.get_video_url_arr(note_item)

        if not videos:
            return
        videoNum = 0
        for url in videos:
            content = await self.xhs_client.get_note_media(url)
            await asyncio.sleep(random.random())
            if content is None:
                continue
            extension_file_name = f"{videoNum}.mp4"
            videoNum += 1
            await xhs_store.update_xhs_note_video(note_id, content, extension_file_name)
