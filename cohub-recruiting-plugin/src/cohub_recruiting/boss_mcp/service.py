# -*- coding: utf-8 -*-
"""High-level BOSS recruiter search service used by the MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from cohub_recruiting.config import RecruitingRuntimeConfig, load_recruiting_config
from cohub_recruiting.models import NormalizedSearchQuery, SiteSearchResult
from cohub_recruiting.renderer import render_search_results
from .extractors import extract_candidates_from_page, extract_total_from_page
from .session import BossBrowserSession, resolve_browser_launch_config

logger = logging.getLogger(__name__)


def build_search_phrase(
    query_input: Mapping[str, Any] | NormalizedSearchQuery,
) -> str:
    """Build the primary recruiter search phrase for BOSS."""
    if isinstance(query_input, NormalizedSearchQuery):
        query = query_input
    else:
        query = NormalizedSearchQuery.model_validate(
            _normalize_query_mapping(dict(query_input)),
        )

    for value in (query.position, query.keyword, query.company):
        text = str(value or "").strip()
        if text:
            return text
    return ""


class BossService:
    """High-level BOSS search service used by the MCP tools."""

    def __init__(
        self,
        *,
        config_loader: Callable[[], RecruitingRuntimeConfig] = (
            load_recruiting_config
        ),
        session_factory: Callable[[RecruitingRuntimeConfig], Any]
        | None = None,
        extract_candidates_from_page: Callable[
            [Any, int, int],
            Awaitable[list],
        ]
        | None = extract_candidates_from_page,
        extract_total_from_page: Callable[[Any], Awaitable[int]]
        | None = extract_total_from_page,
    ) -> None:
        self._lock = asyncio.Lock()
        self._config_loader = config_loader
        self._session_factory = session_factory or self._default_session_factory
        self._extract_candidates_from_page = extract_candidates_from_page
        self._extract_total_from_page = extract_total_from_page
        self._session: Any | None = None
        self._last_query: NormalizedSearchQuery | None = None
        self._last_successful_query: NormalizedSearchQuery | None = None

    async def status(self) -> dict[str, Any]:
        """Return the current BOSS session state."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            page = await session.ensure_started()
            status = await session.check_status(page)
            return {
                "site": "boss",
                "status": status,
                "profile_dir": session.launch_config.profile_dir,
                "browser_kind": session.launch_config.browser_kind,
                "executable_path": session.launch_config.executable_path,
                "message": _build_status_message(status),
                "continue_tool": (
                    "boss_continue_last_search"
                    if status in {"not_logged_in", "captcha_required"}
                    else ""
                ),
                "reuse_same_browser_window": True,
                "avoid_reopen_browser": status
                in {"not_logged_in", "captcha_required"},
                "stop_current_turn": status
                in {"not_logged_in", "captcha_required"},
            }

    async def prepare_browser(self) -> dict[str, Any]:
        """Prepare the persistent BOSS browser session."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            page = await session.ensure_started()
            ensure_entry_page = getattr(session, "ensure_entry_page", None)
            if callable(ensure_entry_page):
                page = await ensure_entry_page(page)
            status = await session.check_status(page)
            return {
                "site": "boss",
                "status": status,
                "profile_dir": session.launch_config.profile_dir,
                "browser_kind": session.launch_config.browser_kind,
                "executable_path": session.launch_config.executable_path,
                "message": _build_status_message(status),
                "continue_tool": (
                    "boss_continue_last_search"
                    if status in {"not_logged_in", "captcha_required"}
                    else ""
                ),
                "reuse_same_browser_window": True,
                "avoid_reopen_browser": status
                in {"not_logged_in", "captcha_required"},
                "stop_current_turn": status
                in {"not_logged_in", "captcha_required"},
            }

    async def search_candidates(
        self,
        query_input: Mapping[str, Any] | NormalizedSearchQuery | str,
        *,
        page: int | None = None,
        result_limit: int | None = None,
    ) -> SiteSearchResult:
        """Search BOSS candidates and return the shared result envelope."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            query = _normalize_query(query_input)
            query.page = page or query.page or config.default_page
            query.page_size_limit = (
                result_limit
                or query.page_size_limit
                or config.default_result_limit
            )
            self._last_query = query.model_copy(deep=True)

            phrase = build_search_phrase(query)
            if not phrase:
                return _build_search_result(
                    status="unsupported_filter",
                    page=query.page,
                )

            active_page = await session.ensure_started()
            ensure_entry_page = getattr(session, "ensure_entry_page", None)
            if callable(ensure_entry_page):
                active_page = await ensure_entry_page(active_page)

            status = await session.search_phrase(
                active_page,
                phrase,
                query.page,
            )
            if status != "ok":
                return _build_search_result(status=status, page=query.page)

            candidates: list[Any] = []
            if self._extract_candidates_from_page is not None:
                candidates = await self._extract_candidates_from_page(
                    active_page,
                    query.page,
                    query.page_size_limit,
                )

            if not candidates:
                return _build_search_result(status="empty_result", page=query.page)

            total = len(candidates)
            if self._extract_total_from_page is not None:
                extracted_total = await self._extract_total_from_page(active_page)
                if extracted_total > 0:
                    total = extracted_total

            result = SiteSearchResult(
                site="boss",
                status="ok",
                page=query.page,
                total=total,
                candidates=candidates[: query.page_size_limit],
            )
            result.summary_markdown = render_search_results(
                [result],
                display_limit=query.page_size_limit,
            )
            self._last_successful_query = query.model_copy(deep=True)
            return result

    async def next_page(
        self,
        *,
        result_limit: int | None = None,
    ) -> SiteSearchResult:
        """Advance to the next page for the last successful BOSS search."""
        async with self._lock:
            if self._last_successful_query is None:
                return SiteSearchResult(
                    site="boss",
                    status="internal_error",
                    message="当前没有可继续翻页的上一次成功搜索",
                )

            next_query = self._last_successful_query.model_copy(deep=True)
            next_query.page = (next_query.page or 1) + 1

        return await self.search_candidates(
            next_query,
            page=next_query.page,
            result_limit=result_limit or next_query.page_size_limit,
        )

    async def continue_last_search(self) -> SiteSearchResult:
        """Resume the most recent BOSS search after manual verification."""
        async with self._lock:
            if self._last_query is None:
                return SiteSearchResult(
                    site="boss",
                    status="internal_error",
                    message="当前没有可继续的上一次搜索",
                )

            config = self._config_loader()
            session = self._get_session(config)
            active_page = await session.ensure_started()
            status = await session.check_status(active_page)
            if status != "ok":
                return _build_search_result(
                    status=status,
                    page=self._last_query.page,
                )

            last_query = self._last_query

        return await self.search_candidates(
            last_query,
            page=last_query.page,
            result_limit=last_query.page_size_limit,
        )

    async def close_browser(self) -> dict[str, Any]:
        """Close the BOSS browser session if it is running."""
        async with self._lock:
            if self._session is not None:
                await self._session.close()
                self._session = None
            return {"site": "boss", "closed": True}

    @staticmethod
    def _default_session_factory(
        config: RecruitingRuntimeConfig,
    ) -> BossBrowserSession:
        """Create the default persistent browser session."""
        return BossBrowserSession(
            resolve_browser_launch_config(
                config.boss_profile_dir,
                cdp_url=config.boss_cdp_url,
            ),
        )

    def _get_session(self, config: RecruitingRuntimeConfig) -> Any:
        """Lazily create and cache the site session."""
        if self._session is None:
            self._session = self._session_factory(config)
        return self._session


def _normalize_query(
    query_input: Mapping[str, Any] | NormalizedSearchQuery | str,
) -> NormalizedSearchQuery:
    """Normalize JSON, mapping, or raw string into the shared query model."""
    if isinstance(query_input, NormalizedSearchQuery):
        return query_input.model_copy(deep=True)
    if isinstance(query_input, str):
        raw = query_input.strip()
        if not raw:
            return NormalizedSearchQuery()
        if raw.startswith("{"):
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                return NormalizedSearchQuery.model_validate(
                    _normalize_query_mapping(loaded),
                )
        return NormalizedSearchQuery(keyword=raw)
    return NormalizedSearchQuery.model_validate(
        _normalize_query_mapping(dict(query_input)),
    )


def _normalize_query_mapping(raw_query: dict[str, Any]) -> dict[str, Any]:
    """Map common model-generated aliases into the shared query contract."""
    data = dict(raw_query)
    alias_map = {
        "city": "expected_city",
        "location": "expected_city",
        "currentLocation": "current_city",
        "title": "position",
        "job_title": "position",
        "keywords": "keyword",
        "degree": "education",
        "education_level": "education",
    }
    for source_key, target_key in alias_map.items():
        if source_key in data and target_key not in data:
            data[target_key] = data[source_key]
    return data


def _build_status_message(status: str) -> str:
    """Build a stable user-action hint for manual BOSS verification."""
    if status == "not_logged_in":
        return (
            "请在同一个 BOSS 浏览器窗口中完成登录，然后调用 "
            "boss_continue_last_search 继续搜索。不要再次调用 "
            "boss_prepare_browser，也不要打开新的浏览器窗口。当前轮次到此为止。"
        )
    if status == "captcha_required":
        return (
            "请在同一个 BOSS 浏览器窗口中完成人机验证，然后调用 "
            "boss_continue_last_search 继续搜索。不要再次调用 "
            "boss_prepare_browser，也不要打开新的浏览器窗口。当前轮次到此为止。"
        )
    if status == "site_layout_changed":
        return (
            "BOSS 招聘者页面结构发生变化。请保持当前已登录的 BOSS 窗口，"
            "不要打开新的浏览器窗口，也不要切换到 browser_use。当前轮次到此为止。"
        )
    if status == "extraction_unreliable":
        return (
            "BOSS 候选人列表抽取结果不可靠。请保持当前已登录的 BOSS 窗口，"
            "不要切换到 browser_use。当前轮次到此为止。"
        )
    if status == "empty_result":
        return (
            "当前条件下未找到候选人。请直接告诉用户本次没有符合条件的结果，"
            "等待用户确认是否放宽条件。不要自动放宽条件。"
        )
    if status == "unsupported_filter":
        return "缺少可直接搜索的关键词"
    return "已打开或复用同一个 BOSS 浏览器窗口。后续如需人工验证，请继续在这个窗口中完成。"


def _build_search_result(
    *,
    status: str,
    page: int,
) -> SiteSearchResult:
    """Build a stable MCP result envelope for BOSS."""
    continue_tool = (
        "boss_continue_last_search"
        if status in {"not_logged_in", "captcha_required"}
        else ""
    )
    requires_manual_action = status in {
        "not_logged_in",
        "captcha_required",
        "site_layout_changed",
        "extraction_unreliable",
        "empty_result",
    }
    return SiteSearchResult(
        site="boss",
        status=status,
        page=page,
        total=0,
        message=_build_status_message(status),
        continue_tool=continue_tool,
        reuse_same_browser_window=requires_manual_action,
        avoid_reopen_browser=requires_manual_action,
        stop_current_turn=requires_manual_action,
    )
