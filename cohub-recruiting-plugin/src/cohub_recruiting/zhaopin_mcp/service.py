# -*- coding: utf-8 -*-
"""High-level Zhaopin recruiter search service used by the MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

from cohub_recruiting.config import RecruitingRuntimeConfig, load_recruiting_config
from cohub_recruiting.models import NormalizedSearchQuery, SiteSearchResult
from cohub_recruiting.renderer import render_search_results
from .extractors import (
    candidate_batch_is_reliable,
    candidate_summary_is_reliable,
    capture_extraction_debug_snapshot,
    extract_candidates_from_page,
    extract_total_from_page,
)
from .session import ZhaopinBrowserSession, resolve_browser_launch_config

_EXTRACTION_RETRY_DELAYS_MS = (1200, 2400)
_SITE_PAGE_CANDIDATE_CAP = 20
_AUTO_PAGE_MAX_PAGES = 10


def build_search_phrase(
    query_input: Mapping[str, Any] | NormalizedSearchQuery,
) -> str:
    """Build the primary recruiter search phrase for Zhaopin."""
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


class ZhaopinService:
    """High-level Zhaopin search service used by the MCP tools."""

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
        capture_debug_snapshot: Callable[[Any, int], Awaitable[dict[str, Any]]]
        | None = capture_extraction_debug_snapshot,
    ) -> None:
        self._config_loader = config_loader
        self._session_factory = session_factory or self._default_session_factory
        self._extract_candidates_from_page = extract_candidates_from_page
        self._extract_total_from_page = extract_total_from_page
        self._capture_debug_snapshot = capture_debug_snapshot
        self._session: Any | None = None
        self._last_query: NormalizedSearchQuery | None = None
        self._last_successful_query: NormalizedSearchQuery | None = None
        self._last_successful_page_end: int | None = None
        self._lock = asyncio.Lock()

    async def status(self) -> dict[str, Any]:
        """Return the current Zhaopin session state."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            page = await session.ensure_started()
            status = await session.check_status(page)
            return {
                "site": "zhaopin",
                "status": status,
                "profile_dir": session.launch_config.profile_dir,
                "browser_kind": session.launch_config.browser_kind,
                "executable_path": session.launch_config.executable_path,
                "message": _build_status_message(status),
                "continue_tool": (
                    "zhaopin_continue_last_search"
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
        """Prepare the persistent Zhaopin browser session."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            page = await session.ensure_started()
            ensure_entry_page = getattr(session, "ensure_entry_page", None)
            if callable(ensure_entry_page):
                page = await ensure_entry_page(page)
            status = await session.check_status(page)
            return {
                "site": "zhaopin",
                "status": status,
                "profile_dir": session.launch_config.profile_dir,
                "browser_kind": session.launch_config.browser_kind,
                "executable_path": session.launch_config.executable_path,
                "message": _build_status_message(status),
                "continue_tool": (
                    "zhaopin_continue_last_search"
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
        """Search Zhaopin candidates and return the shared result envelope."""
        async with self._lock:
            return await self._search_candidates_unlocked(
                query_input, page=page, result_limit=result_limit,
            )

    async def _search_candidates_unlocked(
        self,
        query_input: Mapping[str, Any] | NormalizedSearchQuery | str,
        *,
        page: int | None = None,
        result_limit: int | None = None,
    ) -> SiteSearchResult:
        """Unlocked implementation of search_candidates."""
        config = self._config_loader()
        session = self._get_session(config)
        query = _normalize_query(query_input)
        effective_page = page or query.page or config.default_page
        effective_limit = _resolve_page_size_limit(query, result_limit)
        query.page = effective_page
        query.page_size_limit = effective_limit
        self._last_query = query.model_copy(deep=True)
        self._last_successful_page_end = None

        phrase = build_search_phrase(query)
        if not phrase:
            return _build_search_result(
                status="unsupported_filter",
                page=query.page,
            )

        result = await self._search_candidates_for_query(
            session,
            query,
            effective_page=effective_page,
            effective_limit=effective_limit,
            config=config,
        )
        if result.status == "ok":
            self._last_successful_query = query.model_copy(deep=True)
            self._last_successful_page_end = (
                self._last_successful_page_end or effective_page
            )
        return result

    async def next_page(
        self,
        *,
        result_limit: int | None = None,
    ) -> SiteSearchResult:
        """Advance to the next page for the last successful Zhaopin search."""
        async with self._lock:
            if self._last_successful_query is None:
                return SiteSearchResult(
                    site="zhaopin",
                    status="internal_error",
                    message="当前没有可继续翻页的上一次成功搜索",
                )

            next_query = self._last_successful_query.model_copy(deep=True)
            next_query.page = (
                self._last_successful_page_end or next_query.page or 1
            ) + 1
            return await self._search_candidates_unlocked(
                next_query,
                page=next_query.page,
                result_limit=(
                    result_limit
                    if result_limit is not None
                    else next_query.page_size_limit
                ),
            )

    async def continue_last_search(self) -> SiteSearchResult:
        """Resume the most recent Zhaopin search after manual verification."""
        async with self._lock:
            if self._last_query is None:
                return SiteSearchResult(
                    site="zhaopin",
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

            return await self._search_candidates_unlocked(
                self._last_query,
                page=self._last_query.page,
                result_limit=self._last_query.page_size_limit,
            )

    async def close_browser(self) -> dict[str, Any]:
        """Close the Zhaopin browser session if it is running."""
        async with self._lock:
            if self._session is not None:
                await self._session.close()
                self._session = None
            return {"site": "zhaopin", "closed": True}

    async def _search_candidates_for_query(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        effective_page: int,
        effective_limit: int,
        config: RecruitingRuntimeConfig,
    ) -> SiteSearchResult:
        """Choose between single-page and multi-page Zhaopin execution."""
        if effective_limit > _SITE_PAGE_CANDIDATE_CAP:
            return await self._search_candidates_paginated(
                session,
                query,
                effective_page=effective_page,
                effective_limit=effective_limit,
                config=config,
            )
        return await self._search_candidates_once(
            session,
            query,
            effective_page=effective_page,
            effective_limit=effective_limit,
            config=config,
        )

    async def _search_candidates_once(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        effective_page: int,
        effective_limit: int,
        config: RecruitingRuntimeConfig,
    ) -> SiteSearchResult:
        """Run one Zhaopin search and return the current page batch."""
        outcome = await self._search_candidates_page(
            session,
            query,
            page_number=effective_page,
            max_cards=effective_limit,
            config=config,
        )
        self._last_successful_page_end = effective_page

        if outcome.status != "ok":
            return _build_search_result(
                status=outcome.status,
                page=effective_page,
            )

        display_limit = effective_limit if effective_limit > 0 else None
        total = outcome.detected_total or len(outcome.candidates)
        result = SiteSearchResult(
            site="zhaopin",
            status="ok",
            page=effective_page,
            total=total,
            candidates=(
                outcome.candidates[:effective_limit]
                if effective_limit > 0
                else outcome.candidates
            ),
        )
        result.summary_markdown = render_search_results(
            [result],
            display_limit=display_limit,
        )
        return result

    async def _search_candidates_paginated(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        effective_page: int,
        effective_limit: int,
        config: RecruitingRuntimeConfig,
    ) -> SiteSearchResult:
        """Accumulate unique Zhaopin candidates across pages up to the explicit limit."""
        merged_candidates: list[Any] = []
        seen_candidates: set[tuple[str, str]] = set()
        detected_total = 0
        page_cursor = effective_page
        max_pages = min(
            _AUTO_PAGE_MAX_PAGES,
            max(1, ((effective_limit - 1) // _SITE_PAGE_CANDIDATE_CAP) + 3),
        )

        for _ in range(max_pages):
            outcome = await self._search_candidates_page(
                session,
                query,
                page_number=page_cursor,
                max_cards=0,
                config=config,
            )
            self._last_successful_page_end = page_cursor

            if outcome.status not in {"ok", "empty_result"}:
                return _build_search_result(
                    status=outcome.status,
                    page=page_cursor,
                )
            if outcome.status == "empty_result":
                break

            if outcome.detected_total > 0:
                detected_total = max(detected_total, outcome.detected_total)

            for candidate in outcome.candidates:
                candidate_key = _candidate_identity_key(candidate)
                if candidate_key in seen_candidates:
                    continue
                seen_candidates.add(candidate_key)
                merged_candidates.append(candidate)
                if len(merged_candidates) >= effective_limit:
                    break

            if len(merged_candidates) >= effective_limit:
                break
            if (
                detected_total > 0
                and (page_cursor - effective_page + 1) * _SITE_PAGE_CANDIDATE_CAP
                >= detected_total
            ):
                break
            if len(outcome.candidates) < _SITE_PAGE_CANDIDATE_CAP:
                break

            page_cursor += 1

        if not merged_candidates:
            return _build_search_result(
                status="empty_result",
                page=effective_page,
            )

        result = SiteSearchResult(
            site="zhaopin",
            status="ok",
            page=effective_page,
            total=detected_total or len(merged_candidates),
            candidates=merged_candidates[:effective_limit],
        )
        result.summary_markdown = render_search_results(
            [result],
            display_limit=effective_limit,
        )
        return result

    async def _search_candidates_page(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        page_number: int,
        max_cards: int,
        config: RecruitingRuntimeConfig,
    ) -> "_ZhaopinPageSearchOutcome":
        """Execute one Zhaopin recruiter search page and extract its candidates."""
        subquery = query.model_copy(deep=True)
        subquery.page = page_number
        subquery.page_size_limit = max_cards

        phrase = build_search_phrase(subquery)
        if not phrase:
            return _ZhaopinPageSearchOutcome(status="unsupported_filter")

        active_page = await session.ensure_started()
        ensure_entry_page = getattr(session, "ensure_entry_page", None)
        if callable(ensure_entry_page):
            active_page = await ensure_entry_page(active_page)

        apply_query_filters = getattr(session, "apply_query_filters", None)
        search_page_number = 1 if callable(apply_query_filters) else page_number
        status = await session.search_phrase(
            active_page,
            phrase,
            search_page_number,
        )
        if status != "ok":
            return _ZhaopinPageSearchOutcome(status=status)

        if callable(apply_query_filters):
            await apply_query_filters(
                active_page,
                subquery,
                page_number,
            )
            status = await session.check_status(active_page)
            if status != "ok":
                return _ZhaopinPageSearchOutcome(status=status)

        candidates: list[Any] = []
        if self._extract_candidates_from_page is not None:
            candidates = await self._extract_candidates_with_retry(
                active_page,
                page_number=page_number,
                max_cards=max_cards,
            )
            if not candidate_batch_is_reliable(candidates):
                await self._write_debug_dump_if_enabled(
                    active_page,
                    query=subquery,
                    phrase=phrase,
                    extracted_candidates=candidates,
                    max_cards=max_cards,
                    dump_dir=config.zhaopin_debug_dump_dir,
                )
                return _ZhaopinPageSearchOutcome(status="extraction_unreliable")

            candidates = [
                candidate
                for candidate in candidates
                if candidate_summary_is_reliable(candidate)
            ]

        if not candidates:
            return _ZhaopinPageSearchOutcome(status="empty_result")

        detected_total = 0
        if self._extract_total_from_page is not None:
            extracted_total = await self._extract_total_from_page(active_page)
            if extracted_total > 0:
                detected_total = extracted_total

        return _ZhaopinPageSearchOutcome(
            status="ok",
            candidates=candidates,
            detected_total=detected_total,
        )

    async def _write_debug_dump_if_enabled(
        self,
        page: Any,
        *,
        query: NormalizedSearchQuery,
        phrase: str,
        extracted_candidates: list[Any],
        max_cards: int,
        dump_dir: str | None,
    ) -> None:
        """Persist bounded debug evidence for unreliable Zhaopin extraction."""
        if not dump_dir or self._capture_debug_snapshot is None:
            return

        snapshot: dict[str, Any]
        try:
            snapshot = await self._capture_debug_snapshot(page, max_cards)
        except Exception as exc:
            snapshot = {"snapshot_error": str(exc)}

        target_dir = Path(dump_dir).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target_path = (
            target_dir / f"zhaopin-extraction-unreliable-{timestamp}.json"
        )
        payload = {
            "site": "zhaopin",
            "status": "extraction_unreliable",
            "query": query.model_dump(mode="json"),
            "phrase": phrase,
            "extracted_candidates": [
                candidate.model_dump(mode="json")
                if hasattr(candidate, "model_dump")
                else candidate
                for candidate in extracted_candidates
            ],
            "snapshot": snapshot,
        }
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _extract_candidates_with_retry(
        self,
        page: Any,
        *,
        page_number: int,
        max_cards: int,
    ) -> list[Any]:
        """Retry candidate extraction on transient recruiter rendering noise."""
        if self._extract_candidates_from_page is None:
            logger.error("_extract_candidates_from_page is not set")
            return []

        candidates = await self._extract_candidates_from_page(
            page,
            page_number,
            max_cards,
        )
        if candidate_batch_is_reliable(candidates):
            return candidates

        wait_for_timeout = getattr(page, "wait_for_timeout", None)
        for delay_ms in _EXTRACTION_RETRY_DELAYS_MS:
            if callable(wait_for_timeout):
                try:
                    await wait_for_timeout(delay_ms)
                except Exception:
                    logger.warning(
                        "Unexpected error during extraction retry wait",
                        exc_info=True,
                    )
            candidates = await self._extract_candidates_from_page(
                page,
                page_number,
                max_cards,
            )
            if candidate_batch_is_reliable(candidates):
                return candidates

        return candidates

    @staticmethod
    def _default_session_factory(
        config: RecruitingRuntimeConfig,
    ) -> ZhaopinBrowserSession:
        """Create the default persistent browser session."""
        return ZhaopinBrowserSession(
            resolve_browser_launch_config(config.zhaopin_profile_dir),
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


def _resolve_page_size_limit(
    query: NormalizedSearchQuery,
    result_limit: int | None,
) -> int:
    """Resolve the per-page limit, defaulting to full-page extraction."""
    if result_limit is not None:
        return max(0, int(result_limit))
    if "page_size_limit" in query.model_fields_set:
        return max(0, int(query.page_size_limit))
    return 0


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
    """Build a stable user-action hint for manual Zhaopin verification."""
    if status == "not_logged_in":
        return (
            "请在同一个智联招聘浏览器窗口中完成登录，然后调用 "
            "zhaopin_continue_last_search 继续搜索。不要再次调用 "
            "zhaopin_prepare_browser，也不要打开新的浏览器窗口。当前轮次到此为止。"
        )
    if status == "captcha_required":
        return (
            "请在同一个智联招聘浏览器窗口中完成人机验证，然后调用 "
            "zhaopin_continue_last_search 继续搜索。不要再次调用 "
            "zhaopin_prepare_browser，也不要打开新的浏览器窗口。当前轮次到此为止。"
        )
    if status == "site_layout_changed":
        return (
            "智联招聘招聘方页面结构发生变化。请保持当前已登录的智联招聘窗口，"
            "不要打开新的浏览器窗口，也不要切换到 browser_use。当前轮次到此为止。"
        )
    if status == "extraction_unreliable":
        return (
            "智联招聘候选人列表抽取结果不可靠。请保持当前已登录的智联招聘窗口，"
            "不要切换到 browser_use。当前轮次到此为止。"
        )
    if status == "empty_result":
        return (
            "当前条件下未找到候选人。请直接告诉用户本次没有符合条件的结果，"
            "等待用户确认是否放宽条件。不要自动放宽条件。"
        )
    if status == "unsupported_filter":
        return "缺少可直接搜索的关键词"
    return "已打开或复用同一个智联招聘浏览器窗口。后续如需人工验证，请继续在这个窗口中完成。"


@dataclass
class _ZhaopinPageSearchOutcome:
    """Internal single-page search outcome for Zhaopin pagination flows."""

    status: str
    candidates: list[Any] | None = None
    detected_total: int = 0

    def __post_init__(self) -> None:
        if self.candidates is None:
            self.candidates = []


def _candidate_identity_key(candidate: Any) -> tuple[str, str]:
    """Build a stable dedupe key for merged Zhaopin candidate batches."""
    return (
        str(getattr(candidate, "candidate_id", "") or "").strip(),
        str(getattr(candidate, "detail_url", "") or "").strip(),
    )


def _build_search_result(
    *,
    status: str,
    page: int,
) -> SiteSearchResult:
    """Build a stable MCP result envelope for Zhaopin."""
    continue_tool = (
        "zhaopin_continue_last_search"
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
        site="zhaopin",
        status=status,
        page=page,
        total=0,
        message=_build_status_message(status),
        continue_tool=continue_tool,
        reuse_same_browser_window=requires_manual_action,
        avoid_reopen_browser=requires_manual_action,
        stop_current_turn=requires_manual_action,
    )
