# -*- coding: utf-8 -*-
"""Service orchestration for the Liepin MCP adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from cohub_recruiting.config import RecruitingRuntimeConfig, load_recruiting_config
from cohub_recruiting.models import NormalizedSearchQuery, SiteSearchResult
from cohub_recruiting.renderer import render_search_results
from .extractors import (
    capture_extraction_debug_snapshot,
    candidate_batch_is_reliable,
    candidate_summary_is_reliable,
    extract_candidates_from_page,
    extract_total_from_page,
)
from .session import LiepinBrowserSession, resolve_browser_launch_config

logger = logging.getLogger(__name__)

_EXTRACTION_RETRY_DELAYS_MS = (1200, 2400)
_SITE_PAGE_CANDIDATE_CAP = 20
_AUTO_PAGE_MAX_PAGES = 10
_CITY_ALIAS_MAP = {
    "shanghai": "上海",
    "beijing": "北京",
    "guangzhou": "广州",
    "shenzhen": "深圳",
    "hangzhou": "杭州",
    "suzhou": "苏州",
    "nanjing": "南京",
    "chengdu": "成都",
    "wuhan": "武汉",
    "xian": "西安",
    "xi'an": "西安",
    "tianjin": "天津",
    "chongqing": "重庆",
    "changsha": "长沙",
    "qingdao": "青岛",
    "xiamen": "厦门",
    "ningbo": "宁波",
    "zhengzhou": "郑州",
    "hefei": "合肥",
    "fuzhou": "福州",
    "jinan": "济南",
    "dalian": "大连",
    "dongguan": "东莞",
    "foshan": "佛山",
    "wuxi": "无锡",
    "shenyang": "沈阳",
    "changchun": "长春",
    "harbin": "哈尔滨",
}
_KNOWN_CITY_LABELS = tuple(
    sorted(
        {
            *(_CITY_ALIAS_MAP.keys()),
            *(_CITY_ALIAS_MAP.values()),
        },
        key=len,
        reverse=True,
    ),
)
_KNOWN_CITY_PATTERN = "|".join(re.escape(label) for label in _KNOWN_CITY_LABELS)
_EDUCATION_TOKENS = (
    "博士/博士后",
    "博士后",
    "博士",
    "硕士",
    "统招本科",
    "本科及以上",
    "本科",
    "大专",
    "中专/中技",
    "中专",
    "中技",
    "高中及以下",
    "emba",
    "mba",
    "bachelor",
    "master",
    "phd",
    "doctor",
)
_RAW_QUERY_PREFIX_PATTERNS = (
    r"^\s*找个\s*",
    r"^\s*找一下\s*",
    r"^\s*请?(?:帮我|帮忙|麻烦你|麻烦)?(?:在猎聘(?:上)?|猎聘(?:上)?)?(?:找个|找一下|找下|找|搜一下|搜下|搜|搜索一下|搜索下|搜索|查找|看看|看下)\s*",
)
_RAW_QUERY_SUFFIX_PATTERNS = (
    r"(?:先)?返回第?[一1]页(?:候选人|简历|人才)?(?:摘要)?列表\s*$",
    r"第?[一1]页(?:候选人|简历|人才)?(?:摘要)?列表\s*$",
    r"(?:候选人|简历|人才)(?:摘要)?列表\s*$",
    r"先返回第?[一1]页\s*$",
)


@dataclass(frozen=True)
class _PageSearchOutcome:
    """Detailed result for one recruiter search page."""

    status: str
    page: int
    candidates: list[Any]
    raw_candidate_count: int = 0
    detected_total: int = 0


def build_search_phrase(
    query_input: Mapping[str, Any] | NormalizedSearchQuery,
    *,
    excluded_fields: set[str] | None = None,
) -> str:
    """Build a compact free-text Liepin search phrase from a query object."""
    if isinstance(query_input, NormalizedSearchQuery):
        data = query_input.model_dump(mode="json")
    else:
        data = _normalize_query_mapping(dict(query_input))

    ordered_fields = [
        "position",
        "keyword",
        "company",
        "expected_city",
        "current_city",
        "experience",
        "education",
        "expected_industry",
        "current_industry",
        "expected_function",
        "current_function",
        "school",
        "major",
        "active_status",
        "job_status",
        "management_experience",
        "expected_salary",
        "current_salary",
    ]

    parts: list[str] = []
    seen: set[str] = set()
    excluded = excluded_fields or set()
    for field in ordered_fields:
        if field in excluded:
            continue
        value = str(data.get(field, "") or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        parts.append(value)
    return " ".join(parts)


class LiepinService:
    """High-level Liepin search service used by the MCP tools."""

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
        self._lock = asyncio.Lock()
        self._last_query: NormalizedSearchQuery | None = None
        self._last_successful_query: NormalizedSearchQuery | None = None
        self._last_result_page_end: int | None = None
        self._last_successful_page_end: int | None = None

    async def status(self) -> dict[str, Any]:
        """Return current Liepin session/login state."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            page = await session.ensure_started()
            status = await session.check_status(page)
            return {
                "site": "liepin",
                "status": status,
                "profile_dir": session.launch_config.profile_dir,
                "browser_kind": session.launch_config.browser_kind,
                "executable_path": session.launch_config.executable_path,
                "message": _build_status_message(status),
                "continue_tool": (
                    "liepin_continue_last_search"
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
        """Open the Liepin browser profile and return the current status."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            page = await session.ensure_started()
            ensure_entry_page = getattr(session, "ensure_entry_page", None)
            if callable(ensure_entry_page):
                page = await ensure_entry_page(page)
            status = await session.check_status(page)
            return {
                "site": "liepin",
                "status": status,
                "profile_dir": session.launch_config.profile_dir,
                "browser_kind": session.launch_config.browser_kind,
                "executable_path": session.launch_config.executable_path,
                "message": _build_status_message(status),
                "continue_tool": (
                    "liepin_continue_last_search"
                    if status in {"not_logged_in", "captcha_required"}
                    else ""
                ),
                "reuse_same_browser_window": True,
                "avoid_reopen_browser": status
                in {"not_logged_in", "captcha_required"},
                "stop_current_turn": status
                in {"not_logged_in", "captcha_required"},
            }

    async def close_browser(self) -> dict[str, Any]:
        """Close the Liepin browser session if it is running."""
        async with self._lock:
            if self._session is not None:
                await self._session.close()
                self._session = None
            return {"site": "liepin", "closed": True}

    async def search_candidates(
        self,
        query_input: Mapping[str, Any] | NormalizedSearchQuery | str,
        *,
        page: int | None = None,
        result_limit: int | None = None,
    ) -> SiteSearchResult:
        """Search candidates on Liepin and return the shared result envelope."""
        async with self._lock:
            config = self._config_loader()
            session = self._get_session(config)
            query = _normalize_query(query_input)
            query = _preserve_previous_specific_title(
                query,
                self._last_successful_query,
            )

            effective_page = page or query.page or config.default_page
            effective_limit = (
                result_limit
                or query.page_size_limit
                or config.default_result_limit
            )
            query.page = effective_page
            query.page_size_limit = effective_limit
            self._last_query = query.model_copy(deep=True)
            self._last_result_page_end = None

            if _should_union_city_search(query):
                result = await self._search_candidates_with_city_union(
                    session,
                    query,
                    effective_page=effective_page,
                    effective_limit=effective_limit,
                    config=config,
                )
            else:
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
                    self._last_result_page_end or effective_page
                )
            return result

    async def next_page(
        self,
        *,
        result_limit: int | None = None,
    ) -> SiteSearchResult:
        """Advance to the next page for the last successful search."""
        async with self._lock:
            if self._last_successful_query is None:
                return SiteSearchResult(
                    site="liepin",
                    status="internal_error",
                    message="当前没有可继续翻页的上一次成功搜索",
                )

            next_query = self._last_successful_query.model_copy(deep=True)
            next_page = (self._last_successful_page_end or next_query.page or 1) + 1
        return await self.search_candidates(
            next_query,
            page=next_page,
            result_limit=result_limit or next_query.page_size_limit,
        )

    async def _search_candidates_for_query(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        effective_page: int,
        effective_limit: int,
        config: RecruitingRuntimeConfig,
    ) -> SiteSearchResult:
        """Choose between single-page and multi-page search execution."""
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
        """Run one recruiter search against a single normalized query."""
        outcome = await self._search_candidates_page(
            session,
            query,
            page_number=effective_page,
            max_cards=effective_limit,
            config=config,
        )
        self._last_result_page_end = effective_page

        if outcome.status != "ok":
            return _build_search_result(
                status=outcome.status,
                page=effective_page,
            )

        total = len(outcome.candidates)
        if outcome.detected_total > 0 and (
            not _query_has_structured_constraints(query)
            or len(outcome.candidates) == outcome.raw_candidate_count
        ):
            total = outcome.detected_total

        result = SiteSearchResult(
            site="liepin",
            status="ok",
            page=effective_page,
            total=total,
            candidates=outcome.candidates,
        )
        result.summary_markdown = render_search_results(
            [result],
            display_limit=effective_limit,
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
        """Accumulate candidate results across pages until the requested limit is met."""
        merged_candidates: list[Any] = []
        seen_candidates: set[tuple[str, str]] = set()
        detected_total = 0
        saw_local_filtering = False
        page_cursor = effective_page
        max_pages = min(
            _AUTO_PAGE_MAX_PAGES,
            max(1, math.ceil(effective_limit / _SITE_PAGE_CANDIDATE_CAP) + 2),
        )

        for _ in range(max_pages):
            outcome = await self._search_candidates_page(
                session,
                query,
                page_number=page_cursor,
                max_cards=effective_limit,
                config=config,
            )
            self._last_result_page_end = page_cursor

            if outcome.status not in {"ok", "empty_result"}:
                return _build_search_result(
                    status=outcome.status,
                    page=page_cursor,
                )

            if outcome.detected_total > 0:
                detected_total = max(detected_total, outcome.detected_total)
            if outcome.raw_candidate_count != len(outcome.candidates):
                saw_local_filtering = True

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
            if (
                detected_total <= 0
                and outcome.raw_candidate_count < _SITE_PAGE_CANDIDATE_CAP
            ):
                break

            page_cursor += 1

        if not merged_candidates:
            return _build_search_result(
                status="empty_result",
                page=effective_page,
            )

        total = len(merged_candidates)
        if detected_total > 0 and not saw_local_filtering:
            total = detected_total

        result = SiteSearchResult(
            site="liepin",
            status="ok",
            page=effective_page,
            total=total,
            candidates=merged_candidates[:effective_limit],
        )
        result.summary_markdown = render_search_results(
            [result],
            display_limit=effective_limit,
        )
        return result

    async def _search_candidates_with_city_union(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        effective_page: int,
        effective_limit: int,
        config: RecruitingRuntimeConfig,
    ) -> SiteSearchResult:
        """Union recruiter results for expected-city OR current-city requests."""
        merged_candidates: list[Any] = []
        seen_candidates: set[tuple[str, str]] = set()
        page_end = effective_page

        for subquery in _build_city_union_queries(query):
            subquery.page = effective_page
            subquery.page_size_limit = effective_limit
            branch_result = await self._search_candidates_for_query(
                session,
                subquery,
                effective_page=effective_page,
                effective_limit=effective_limit,
                config=config,
            )
            page_end = max(page_end, self._last_result_page_end or effective_page)
            if branch_result.status not in {"ok", "empty_result"}:
                return branch_result
            if branch_result.status != "ok":
                continue

            for candidate in branch_result.candidates:
                candidate_key = _candidate_identity_key(candidate)
                if candidate_key in seen_candidates:
                    continue
                seen_candidates.add(candidate_key)
                merged_candidates.append(candidate)

        if not merged_candidates:
            return _build_search_result(
                status="empty_result",
                page=effective_page,
            )

        result = SiteSearchResult(
            site="liepin",
            status="ok",
            page=effective_page,
            total=len(merged_candidates),
            candidates=merged_candidates[:effective_limit],
        )
        result.summary_markdown = render_search_results(
            [result],
            display_limit=effective_limit,
        )
        self._last_result_page_end = page_end
        return result

    async def continue_last_search(self) -> SiteSearchResult:
        """Resume the last Liepin search after manual verification."""
        async with self._lock:
            if self._last_query is None:
                return SiteSearchResult(
                    site="liepin",
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

    @staticmethod
    def _default_session_factory(
        config: RecruitingRuntimeConfig,
    ) -> LiepinBrowserSession:
        """Create the default persistent browser session."""
        return LiepinBrowserSession(
            resolve_browser_launch_config(config.liepin_profile_dir),
        )

    def _get_session(self, config: RecruitingRuntimeConfig) -> Any:
        """Lazily create and cache the site session."""
        if self._session is None:
            self._session = self._session_factory(config)
        return self._session

    async def _search_candidates_page(
        self,
        session: Any,
        query: NormalizedSearchQuery,
        *,
        page_number: int,
        max_cards: int,
        config: RecruitingRuntimeConfig,
    ) -> _PageSearchOutcome:
        """Run one recruiter query page and return detailed extraction metadata."""
        phrase = build_search_phrase(
            query,
            excluded_fields={
                "expected_city",
                "current_city",
                "experience",
                "education",
            },
        )
        if not phrase:
            return _PageSearchOutcome(
                status="unsupported_filter",
                page=page_number,
                candidates=[],
            )

        attempted_phrases: set[str] = set()
        phrases_to_try = [phrase]
        last_raw_candidate_count = 0
        last_detected_total = 0

        while phrases_to_try:
            current_phrase = phrases_to_try.pop(0)
            attempted_phrases.add(current_phrase)

            active_page = await session.ensure_started()
            status = await session.search_phrase(
                active_page,
                current_phrase,
                page_number,
            )
            if status != "ok":
                return _PageSearchOutcome(
                    status=status,
                    page=page_number,
                    candidates=[],
                )

            apply_query_filters = getattr(session, "apply_query_filters", None)
            filter_context: dict[str, Any] = {}
            if callable(apply_query_filters):
                applied = await apply_query_filters(
                    active_page,
                    query,
                    page_number,
                )
                if isinstance(applied, Mapping):
                    filter_context = dict(applied)

            candidates: list[Any] = []
            raw_candidate_count = 0
            if self._extract_candidates_from_page is not None:
                candidates = await self._extract_candidates_with_retry(
                    active_page,
                    page_number=page_number,
                    max_cards=max_cards,
                )
                if not candidate_batch_is_reliable(candidates):
                    await self._write_debug_dump_if_enabled(
                        active_page,
                        query=query,
                        phrase=current_phrase,
                        extracted_candidates=candidates,
                        max_cards=max_cards,
                        dump_dir=config.liepin_debug_dump_dir,
                    )
                    return _PageSearchOutcome(
                        status="extraction_unreliable",
                        page=page_number,
                        candidates=[],
                    )

                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate_summary_is_reliable(candidate)
                ]
                raw_candidate_count = len(candidates)
                logger.info(
                    "Liepin extraction: phrase=%s raw_candidate_count=%s sample=%s",
                    current_phrase,
                    raw_candidate_count,
                    [
                        {
                            "id": getattr(candidate, "candidate_id", ""),
                            "headline": getattr(candidate, "headline", ""),
                            "city": getattr(candidate, "city", ""),
                            "expected_city": getattr(candidate, "expected_city", ""),
                            "years": getattr(candidate, "years_experience", ""),
                            "education": getattr(candidate, "education", ""),
                            "current_title": getattr(candidate, "current_title", ""),
                            "expected_title": getattr(candidate, "expected_title", ""),
                        }
                        for candidate in candidates[:5]
                    ],
                )

                logger.info(
                    "Liepin post-filter disabled: phrase=%s candidate_count=%s",
                    current_phrase,
                    len(candidates),
                )

            detected_total = 0
            if self._extract_total_from_page is not None:
                detected_total = await self._extract_total_from_page(
                    active_page,
                )

            retry_phrase = _build_retry_phrase_for_unapplied_city_filters(
                query,
                current_phrase=current_phrase,
                filter_context=filter_context,
            )
            if retry_phrase and retry_phrase not in attempted_phrases:
                logger.info(
                    "Liepin retry with city phrase fallback: base=%s retry=%s",
                    current_phrase,
                    retry_phrase,
                )
                phrases_to_try.append(retry_phrase)
                continue

            if candidates:
                return _PageSearchOutcome(
                    status="ok",
                    page=page_number,
                    candidates=candidates,
                    raw_candidate_count=raw_candidate_count,
                    detected_total=detected_total,
                )

            last_raw_candidate_count = raw_candidate_count
            last_detected_total = max(last_detected_total, detected_total)

            break

        return _PageSearchOutcome(
            status="empty_result",
            page=page_number,
            candidates=[],
            raw_candidate_count=last_raw_candidate_count,
            detected_total=last_detected_total,
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
        """Persist bounded debug evidence for unreliable recruiter extraction."""
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
            target_dir / f"liepin-extraction-unreliable-{timestamp}.json"
        )
        payload = {
            "site": "liepin",
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
                    logger.debug(
                        "Liepin extraction retry wait failed: delay_ms=%s",
                        delay_ms,
                        exc_info=True,
                    )
            candidates = await self._extract_candidates_from_page(
                page,
                page_number,
                max_cards,
            )
            if candidate_batch_is_reliable(candidates):
                logger.info(
                    "Liepin extraction recovered after retry: delay_ms=%s raw_candidate_count=%s",
                    delay_ms,
                    len(candidates),
                )
                return candidates

        return candidates


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
                loaded = _normalize_query_mapping(loaded)
            return NormalizedSearchQuery.model_validate(loaded)
        parsed = _normalize_free_text_query(raw)
        if parsed is not None:
            return parsed
        return NormalizedSearchQuery(keyword=raw)
    return NormalizedSearchQuery.model_validate(
        _normalize_query_mapping(dict(query_input)),
    )


def _normalize_free_text_query(raw_query: str) -> NormalizedSearchQuery | None:
    """Parse obvious natural-language recruiter requests into structured query fields."""
    raw = str(raw_query or "").strip()
    if not raw:
        return None

    working = _strip_query_wrappers(raw)
    extracted: dict[str, Any] = {}

    for target_key, patterns in (
        (
            "current_city",
            (
                rf"现在在\s*(?P<city>{_KNOWN_CITY_PATTERN})",
                rf"目前在\s*(?P<city>{_KNOWN_CITY_PATTERN})",
            ),
        ),
        (
            "expected_city",
            (
                rf"能来\s*(?P<city>{_KNOWN_CITY_PATTERN})",
                rf"期望(?:在)?\s*(?P<city>{_KNOWN_CITY_PATTERN})",
                rf"base\s*(?:在)?\s*(?P<city>{_KNOWN_CITY_PATTERN})",
            ),
        ),
    ):
        for pattern in patterns:
            match = re.search(pattern, working, flags=re.IGNORECASE)
            if match:
                extracted[target_key] = _canonicalize_city_label(
                    match.group("city"),
                )
                working = _remove_match_span(working, match.span())
                break

    education_match = re.search(
        "|".join(re.escape(token) for token in _EDUCATION_TOKENS),
        working,
        flags=re.IGNORECASE,
    )
    if education_match:
        education = _normalize_education(education_match.group(0))
        if education:
            extracted["education"] = education
        working = _remove_match_span(working, education_match.span())

    experience_match = re.search(
        r"(?P<range>\d+\s*[-~至到]\s*\d+\s*年)|(?P<min>\d+)\s*(?:年以上|年及以上|年\+|年以上经验|年以上工作经验|年经验以上)",
        working,
        flags=re.IGNORECASE,
    )
    if experience_match:
        if experience_match.group("range"):
            extracted["experience"] = re.sub(
                r"\s+",
                "",
                experience_match.group("range"),
            )
        else:
            extracted["experience"] = _format_min_years(
                experience_match.group("min"),
            )
        working = _remove_match_span(working, experience_match.span())

    generic_city_match = _find_generic_city_match(working)
    if generic_city_match and not (
        extracted.get("expected_city") or extracted.get("current_city")
    ):
        extracted["expected_city"] = _canonicalize_city_label(
            generic_city_match.group("city"),
        )
        working = _remove_match_span(working, generic_city_match.span())

    position = _clean_position_text(working)
    if position:
        extracted["position"] = position

    if any(
        extracted.get(field)
        for field in (
            "position",
            "expected_city",
            "current_city",
            "experience",
            "education",
        )
    ):
        return NormalizedSearchQuery.model_validate(extracted)
    return None


def _normalize_query_mapping(raw_query: dict[str, Any]) -> dict[str, Any]:
    """Map common model-generated aliases into the shared query contract."""
    data = dict(raw_query)

    alias_map = {
        "city": "expected_city",
        "location": "expected_city",
        "currentLocation": "current_city",
        "keyword": "keyword",
        "keywords": "keyword",
        "title": "position",
        "job_title": "position",
        "degree": "education",
        "education_level": "education",
        "experience_year": "experience",
        "experience_years": "experience",
        "experienceYear": "experience",
    }
    for source_key, target_key in alias_map.items():
        if source_key in data and target_key not in data:
            data[target_key] = data[source_key]

    for city_key in ("expected_city", "current_city"):
        if city_key in data:
            data[city_key] = _canonicalize_city_label(data[city_key])

    if "experience" in data:
        data["experience"] = _format_min_years(data["experience"])

    if "experience_year_min" in data and "experience" not in data:
        data["experience"] = _format_min_years(data["experience_year_min"])
    if "experience_min" in data and "experience" not in data:
        data["experience"] = _format_min_years(data["experience_min"])

    return data


def _format_min_years(value: Any) -> str:
    """Format numeric min-year values into a natural recruiting phrase."""
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return f"{text}年以上"
    return text


def _canonicalize_city_label(value: Any) -> str:
    """Map common English city aliases into the Chinese labels used by Liepin."""
    text = str(value or "").strip()
    if not text:
        return ""
    return _CITY_ALIAS_MAP.get(text.lower(), text)


def _strip_query_wrappers(text: str) -> str:
    """Remove common conversational wrappers around recruiter search requests."""
    cleaned = str(text or "").strip()
    for pattern in _RAW_QUERY_PREFIX_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
    for pattern in _RAW_QUERY_SUFFIX_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
    return cleaned.strip(" ：:，,。；;、")


def _remove_match_span(text: str, span: tuple[int, int]) -> str:
    """Remove one matched substring and normalize surrounding separators."""
    start, end = span
    merged = f"{text[:start]} {text[end:]}"
    return re.sub(r"\s+", " ", merged).strip()


def _find_generic_city_match(text: str) -> re.Match[str] | None:
    """Find a plain city term in a compact recruiter query string."""
    patterns = (
        rf"(?P<city>{_KNOWN_CITY_PATTERN})(?=的)",
        rf"(?:(?<=^)|(?<=[\s,，、/]))(?P<city>{_KNOWN_CITY_PATTERN})(?=$|[\s,，、/])",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _clean_position_text(text: str) -> str:
    """Trim leftover conversational scaffolding and recruiter-result hints."""
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"[，,。；;、]+", " ", cleaned)
    cleaned = re.sub(r"\b(?:先|再|只|帮我|找|搜|搜索)\b", " ", cleaned)
    cleaned = re.sub(r"(?:候选人|简历|人才)(?:摘要)?(?:列表)?", " ", cleaned)
    cleaned = re.sub(r"第?[一1]页", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" 的：:，,。；;、")


def _build_status_message(status: str) -> str:
    """Build a stable user-action hint for manual Liepin verification."""
    if status == "not_logged_in":
        return (
            "请在同一个猎聘浏览器窗口中完成登录，然后调用 "
            "liepin_continue_last_search 继续搜索。不要再次调用 "
            "liepin_prepare_browser，不要再调用 liepin_status，也不要打开"
            "新的浏览器窗口。当前轮次到此为止，请等用户完成验证后再继续。"
        )
    if status == "captcha_required":
        return (
            "请在同一个猎聘浏览器窗口中完成人机验证，然后调用 "
            "liepin_continue_last_search 继续搜索。不要再次调用 "
            "liepin_prepare_browser，不要再调用 liepin_status，也不要打开"
            "新的浏览器窗口。当前轮次到此为止，请等用户完成验证后再继续。"
        )
    if status == "site_layout_changed":
        return (
            "猎聘招聘方页面结构发生变化。请保持当前已登录的猎聘窗口，不要"
            "打开新的浏览器窗口，不要切换到 browser_use，也不要继续调用"
            "其他猎聘工具。当前轮次到此为止。"
        )
    if status == "extraction_unreliable":
        return (
            "猎聘候选人列表抽取结果不可靠。请保持当前已登录的猎聘窗口，不要"
            "切换到 browser_use，也不要继续调用其他猎聘工具。当前轮次到"
            "此为止。"
        )
    if status == "empty_result":
        return (
            "当前条件下未找到候选人。请直接告诉用户本次没有符合条件的结果，"
            "等待用户确认是否放宽条件。不要自动放宽条件，不要继续调用其他"
            "liepin_* 工具。当前轮次到此为止。"
        )
    return (
        "已打开或复用同一个猎聘浏览器窗口。后续如需人工验证，请继续"
        "在这个窗口中完成。"
    )


def _filter_candidates_against_query(
    query: NormalizedSearchQuery,
    candidates: list[Any],
    *,
    skip_title_check: bool = False,
    applied_site_filters: set[str] | None = None,
) -> list[Any]:
    """Keep only candidates that satisfy obvious structured query constraints."""
    if not candidates:
        return candidates
    if not _query_has_structured_constraints(query):
        return candidates

    filtered = [
        candidate
        for candidate in candidates
        if _candidate_matches_query(
            query,
            candidate,
            skip_title_check=skip_title_check,
            applied_site_filters=applied_site_filters,
        )
    ]
    return filtered


def _candidate_matches_query(
    query: NormalizedSearchQuery,
    candidate: Any,
    *,
    skip_title_check: bool = False,
    applied_site_filters: set[str] | None = None,
) -> bool:
    """Apply city/years/education/title checks against a candidate summary."""
    site_filters = applied_site_filters or set()

    if query.expected_city and not _matches_structured_city_constraint(
        query.expected_city,
        _candidate_city_for_expected_city_filter(candidate),
        soft_when_missing="expected_city" in site_filters,
    ):
        return False

    if query.current_city and not _matches_structured_city_constraint(
        query.current_city,
        str(getattr(candidate, "city", "") or "").strip(),
        soft_when_missing="current_city" in site_filters,
    ):
        return False

    if query.experience:
        required_years = _extract_min_years(query.experience)
        candidate_years = _extract_min_years(
            getattr(candidate, "years_experience", ""),
        )
        if required_years is not None:
            if (
                candidate_years is None
                and "experience" in site_filters
            ):
                pass
            elif candidate_years is None or candidate_years < required_years:
                return False

    if query.education and not _matches_structured_education_constraint(
        query.education,
        getattr(candidate, "education", ""),
        soft_when_missing="education" in site_filters,
    ):
        return False

    title_query = query.position or query.keyword
    if (
        title_query
        and not skip_title_check
        and not _matches_title_query(title_query, candidate)
    ):
        return False

    return True


def _candidate_city_for_expected_city_filter(candidate: Any) -> str:
    """Prefer recruiter-side expected city before falling back to current city."""
    expected_city = str(getattr(candidate, "expected_city", "") or "").strip()
    if expected_city:
        return expected_city
    return str(getattr(candidate, "city", "") or "").strip()


def _is_trusted_recruiter_surface(filter_context: Mapping[str, Any]) -> bool:
    """Return True when the recruiter frontend confirms a trusted filtered list."""
    surface = str(filter_context.get("search_surface", "") or "").strip()
    trusted = bool(filter_context.get("trusted_site_filters"))
    return surface == "recruiter" and trusted


def _collect_applied_site_filters(
    filter_context: Mapping[str, Any],
) -> set[str]:
    """Return structured filters that the recruiter frontend confirms it applied."""
    if not _is_trusted_recruiter_surface(filter_context):
        return set()

    applied = filter_context.get("applied_filters")
    if not isinstance(applied, Mapping):
        return set()

    return {
        str(key)
        for key, value in applied.items()
        if value
    }


def _matches_city(expected_city: str, candidate_city: str) -> bool:
    """Return True when the candidate city satisfies the expected city filter."""
    expected = _normalize_text(expected_city)
    actual = _normalize_text(candidate_city)
    if not expected:
        return True
    if not actual:
        return False
    return expected in actual or actual in expected


def _matches_education_level(
    required_education: str,
    candidate_education: str,
) -> bool:
    """Return True when the candidate education meets or exceeds the request."""
    education_rank = {
        "高中及以下": 0,
        "中专": 1,
        "中技": 1,
        "大专": 2,
        "本科": 3,
        "硕士": 4,
        "mba": 4,
        "emba": 4,
        "博士": 5,
        "博士后": 5,
    }
    required = _normalize_education(required_education)
    candidate = _normalize_education(candidate_education)
    if not required:
        return True
    if not candidate:
        return False
    return education_rank.get(candidate, -1) >= education_rank.get(required, -1)


def _matches_structured_city_constraint(
    expected_city: str,
    candidate_city: str,
    *,
    soft_when_missing: bool,
) -> bool:
    """Allow missing recruiter fields but reject explicit city conflicts."""
    actual = str(candidate_city or "").strip()
    if not actual:
        return soft_when_missing
    return _matches_city(expected_city, actual)


def _matches_structured_education_constraint(
    required_education: str,
    candidate_education: str,
    *,
    soft_when_missing: bool,
) -> bool:
    """Allow missing recruiter fields but reject explicit education conflicts."""
    actual = str(candidate_education or "").strip()
    if not actual:
        return soft_when_missing
    return _matches_education_level(required_education, actual)


def _matches_title_query(
    title_query: str,
    candidate: Any,
) -> bool:
    """Return True when the candidate's role-related text matches the query."""
    haystack = _normalize_text(
        " ".join(
            str(part or "")
            for part in (
                getattr(candidate, "expected_title", ""),
                getattr(candidate, "current_title", ""),
                getattr(candidate, "headline", ""),
                " ".join(getattr(candidate, "highlights", []) or []),
            )
        ),
    )
    needle = _normalize_text(title_query)
    if not needle:
        return True
    if needle in haystack:
        return True

    tokens = _extract_match_tokens(title_query)
    return bool(tokens) and all(token in haystack for token in tokens)


def _extract_match_tokens(text: str) -> list[str]:
    """Extract core mixed-language title tokens for strict post-filtering."""
    normalized = _normalize_text(text)
    if not normalized:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9+#./-]+|[\u4e00-\u9fff]{2,}", normalized):
        core_token = _normalize_title_token(token)
        if len(core_token) < 2 or core_token in seen:
            continue
        seen.add(core_token)
        tokens.append(core_token)
    return tokens


def _normalize_title_token(token: str) -> str:
    """Reduce generic suffix-heavy title fragments to their informative core."""
    normalized = _normalize_text(token)
    if not normalized:
        return ""
    if re.fullmatch(r"[a-z0-9+#./-]+", normalized):
        return normalized

    for suffix in (
        "工程师",
        "经理",
        "负责人",
        "主管",
        "总监",
        "顾问",
        "专家",
        "leader",
    ):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            stripped = normalized[: -len(suffix)]
            if len(stripped) >= 2:
                return stripped
    return normalized


def _extract_min_years(text: str) -> int | None:
    """Extract a minimum years-of-experience integer from free-form text."""
    normalized = _normalize_text(text)
    if "应届" in normalized or "在校" in normalized:
        return 0

    match = re.search(r"(\d+)(?:\.\d+)?", normalized)
    if match:
        return int(match.group(1))
    return None


def _normalize_education(text: str) -> str:
    """Normalize multilingual education labels into a shared Chinese label."""
    normalized = _normalize_text(text)
    mapping = {
        "bachelor": "本科",
        "master": "硕士",
        "phd": "博士",
        "doctor": "博士",
    }
    for source, target in mapping.items():
        if source in normalized:
            return target
    for label in ("博士后", "博士", "硕士", "emba", "mba", "本科", "大专", "中专", "中技", "高中及以下"):
        if _normalize_text(label) in normalized:
            return label
    return ""


def _normalize_text(text: str) -> str:
    """Normalize mixed Chinese/English text for fuzzy comparisons."""
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"hr(?=[\u4e00-\u9fff])", "人力", normalized)
    replacements = {
        "shanghai": "上海",
        "beijing": "北京",
        "guangzhou": "广州",
        "shenzhen": "深圳",
        "hangzhou": "杭州",
        "serviceyears": "年",
        "years": "年",
        "year": "年",
        "serviceyear": "年",
        "bachelor": "本科",
        "master": "硕士",
        "phd": "博士",
        "doctor": "博士",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _query_has_structured_constraints(query: NormalizedSearchQuery) -> bool:
    """Return True when local post-filtering may reduce the raw site result count."""
    return any(
        (
            query.position,
            query.keyword,
            query.current_city,
            query.expected_city,
            query.experience,
            query.education,
        ),
    )


def _preserve_previous_specific_title(
    query: NormalizedSearchQuery,
    previous_query: NormalizedSearchQuery | None,
) -> NormalizedSearchQuery:
    """Keep the last successful specific title when a follow-up broadens it accidentally."""
    if previous_query is None:
        return query

    current_title = _effective_query_title(query)
    previous_title = _effective_query_title(previous_query)
    if not current_title or not previous_title:
        return query
    if not _title_broadens_previous(current_title, previous_title):
        return query

    if query.position:
        query.position = previous_title
    elif query.keyword:
        query.keyword = previous_title
    elif previous_query.position:
        query.position = previous_title
    else:
        query.keyword = previous_title
    return query


def _effective_query_title(query: NormalizedSearchQuery) -> str:
    """Return the effective title-like term from a normalized query."""
    return str(query.position or query.keyword or "").strip()


def _title_broadens_previous(
    current_title: str,
    previous_title: str,
) -> bool:
    """Detect when a new title is a looser subset of the last successful title."""
    current = _normalize_text(current_title)
    previous = _normalize_text(previous_title)
    if not current or not previous or current == previous:
        return False
    if current in previous and len(current) < len(previous):
        return True

    current_tokens = set(_extract_match_tokens(current_title))
    previous_tokens = set(_extract_match_tokens(previous_title))
    return bool(current_tokens) and current_tokens < previous_tokens


def _should_union_city_search(query: NormalizedSearchQuery) -> bool:
    """Run two recruiter searches when the request means expected-city OR current-city."""
    return bool(query.expected_city and query.current_city)


def _build_city_union_queries(
    query: NormalizedSearchQuery,
) -> list[NormalizedSearchQuery]:
    """Split an OR-city request into recruiter-native expected/current city searches."""
    expected_city_query = query.model_copy(deep=True)
    expected_city_query.current_city = ""

    current_city_query = query.model_copy(deep=True)
    current_city_query.expected_city = ""

    return [
        expected_city_query,
        current_city_query,
    ]


def _candidate_identity_key(candidate: Any) -> tuple[str, str]:
    """Build a stable dedupe key for merged recruiter candidate batches."""
    return (
        str(getattr(candidate, "candidate_id", "") or "").strip(),
        str(getattr(candidate, "detail_url", "") or "").strip(),
    )


def _build_retry_phrase_for_unapplied_city_filters(
    query: NormalizedSearchQuery,
    *,
    current_phrase: str,
    filter_context: Mapping[str, Any],
) -> str:
    """Retry with city terms in the phrase when recruiter city filters do not apply."""
    if not _is_trusted_recruiter_surface(filter_context):
        return ""

    applied_filters = filter_context.get("applied_filters")
    if not isinstance(applied_filters, Mapping):
        return ""

    has_unapplied_city_filter = (
        query.expected_city
        and not bool(applied_filters.get("expected_city"))
    ) or (
        query.current_city
        and not bool(applied_filters.get("current_city"))
    )
    if not has_unapplied_city_filter:
        return ""

    retry_phrase = build_search_phrase(
        query,
        excluded_fields={"experience", "education"},
    )
    if retry_phrase == current_phrase:
        return ""
    return retry_phrase


def _build_search_result(
    *,
    status: str,
    page: int,
) -> SiteSearchResult:
    """Build a stable MCP result envelope, including no-reopen hints."""
    continue_tool = (
        "liepin_continue_last_search"
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
        site="liepin",
        status=status,
        page=page,
        total=0,
        message=_build_status_message(status),
        continue_tool=continue_tool,
        reuse_same_browser_window=requires_manual_action,
        avoid_reopen_browser=requires_manual_action,
        stop_current_turn=requires_manual_action,
    )
