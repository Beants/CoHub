# -*- coding: utf-8 -*-
"""Tests for Liepin MCP service orchestration."""

import json

import pytest

from cohub_recruiting.config import (
    MatchModelConfig,
    RecruitingRuntimeConfig,
)
from cohub_recruiting.liepin_mcp.service import (
    LiepinService,
    build_search_phrase,
)
from cohub_recruiting.models import CandidateSummary


def test_build_search_phrase_joins_non_empty_terms_without_duplicates() -> None:
    """Search phrase should keep the query compact and stable."""
    phrase = build_search_phrase(
        {
            "position": "Agent开发",
            "keyword": "Agent开发",
            "expected_city": "上海",
            "experience": "6年",
            "education": "本科",
        },
    )

    assert phrase == "Agent开发 上海 6年 本科"


def test_build_search_phrase_supports_common_alias_fields() -> None:
    """Common model-generated aliases should map into the shared query contract."""
    phrase = build_search_phrase(
        {
            "title": "Agent开发工程师",
            "city": "上海",
            "experience_year_min": 6,
            "degree": "本科",
        },
    )

    assert phrase == "Agent开发工程师 上海 6年以上 本科"


def test_build_search_phrase_supports_keywords_and_experience_year_aliases() -> None:
    """More model-shaped aliases should still normalize into the shared phrase."""
    phrase = build_search_phrase(
        {
            "keywords": "Python算法工程师",
            "location": "上海",
            "experience_year": "6年以上",
            "education": "本科",
        },
    )

    assert phrase == "Python算法工程师 上海 6年以上 本科"


def test_build_search_phrase_supports_experience_years_alias() -> None:
    """Plural experience-year aliases from model tool calls should normalize too."""
    phrase = build_search_phrase(
        {
            "job_title": "Python算法工程师",
            "location": "上海",
            "experience_years": "6年以上",
            "education": "本科",
        },
    )

    assert phrase == "Python算法工程师 上海 6年以上 本科"


def test_build_search_phrase_supports_experience_year_camel_alias() -> None:
    """CamelCase experience aliases from live model calls should normalize."""
    phrase = build_search_phrase(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experienceYear": "6",
            "degree": "本科",
        },
    )

    assert phrase == "Python算法工程师 上海 6年以上 本科"


@pytest.mark.asyncio
async def test_liepin_service_normalizes_english_city_alias_before_applying_filters() -> None:
    """English city aliases from model tool calls should map to recruiter labels."""

    class FakeSession:
        def __init__(self) -> None:
            self.applied_queries = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, page_number
            self.applied_queries.append(query.model_dump(mode="json"))

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="good-1",
                display_name="赵**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "job_title": "Python算法工程师",
            "city": "shanghai",
            "experience_year_min": 6,
            "education": "本科",
        },
    )

    assert result.status == "ok"
    assert fake_session.applied_queries[0]["expected_city"] == "上海"


@pytest.mark.asyncio
async def test_liepin_service_uses_expected_city_for_recruiter_post_filter() -> None:
    """Recruiter candidate cards should match city filters against expected city first."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="qingdao-expected",
                display_name="赵**",
                headline="人力产品经理 / 北京 / 8年 / 本科",
                city="北京",
                expected_city="青岛",
                years_experience="8年",
                education="本科",
                current_title="人力产品经理",
                expected_title="人力产品经理",
                detail_url="https://example.com/candidate/qingdao-expected",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "人力产品经理",
            "city": "青岛",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "qingdao-expected",
    ]


@pytest.mark.asyncio
async def test_liepin_service_returns_login_required_envelope() -> None:
    """Manual verification should be returned as a structured site status."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "not_logged_in"

        async def check_status(self, page):
            return "not_logged_in"

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=None,
        extract_total_from_page=None,
    )

    result = await service.search_candidates({"keyword": "agent开发"})

    assert result.site == "liepin"
    assert result.status == "not_logged_in"
    assert "liepin_continue_last_search" in result.message
    assert "猎聘浏览器窗口" in result.message
    assert "不要再次调用 liepin_prepare_browser" in result.message
    assert "不要再调用 liepin_status" in result.message
    assert result.continue_tool == "liepin_continue_last_search"
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert result.candidates == []


@pytest.mark.asyncio
async def test_liepin_prepare_browser_returns_same_window_hint() -> None:
    """Browser preparation should tell the model to reuse the same window."""

    class FakeSession:
        def __init__(self) -> None:
            self.launch_config = type(
                "LaunchConfig",
                (),
                {
                    "profile_dir": "/tmp/liepin",
                    "browser_kind": "chromium",
                    "executable_path": "/Applications/Google Chrome.app/test",
                },
            )()
            self.ensure_entry_page_calls = 0

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            self.ensure_entry_page_calls += 1
            return page

        async def check_status(self, page):
            return "captcha_required"

    fake_session = FakeSession()
    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=None,
        extract_total_from_page=None,
    )

    result = await service.prepare_browser()

    assert result["status"] == "captcha_required"
    assert "liepin_continue_last_search" in result["message"]
    assert "同一个猎聘浏览器窗口" in result["message"]
    assert result["avoid_reopen_browser"] is True
    assert "不要再次调用 liepin_prepare_browser" in result["message"]
    assert "不要再调用 liepin_status" in result["message"]
    assert result["stop_current_turn"] is True
    assert fake_session.ensure_entry_page_calls == 1


@pytest.mark.asyncio
async def test_liepin_service_blocks_browser_fallback_on_layout_change() -> None:
    """Layout-change results should stay inside the existing Liepin browser flow."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "site_layout_changed"

        async def check_status(self, page):
            return "ok"

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=None,
        extract_total_from_page=None,
    )

    result = await service.search_candidates({"keyword": "agent开发"})

    assert result.status == "site_layout_changed"
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert "不要打开新的浏览器窗口" in result.message
    assert "不要切换到 browser_use" in result.message


@pytest.mark.asyncio
async def test_liepin_continue_last_search_checks_status_before_retrying() -> None:
    """Resume should not navigate again while manual verification is unfinished."""

    class FakeSession:
        def __init__(self) -> None:
            self.launch_config = type(
                "LaunchConfig",
                (),
                {
                    "profile_dir": "/tmp/liepin",
                    "browser_kind": "chromium",
                    "executable_path": "/Applications/Google Chrome.app/test",
                },
            )()
            self.search_phrase_calls = 0

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            self.search_phrase_calls += 1
            return "captcha_required"

        async def check_status(self, page):
            return "captcha_required"

    fake_session = FakeSession()
    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=None,
        extract_total_from_page=None,
    )

    await service.search_candidates({"keyword": "agent开发"})
    result = await service.continue_last_search()

    assert result.status == "captcha_required"
    assert result.continue_tool == "liepin_continue_last_search"
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert fake_session.search_phrase_calls == 1


@pytest.mark.asyncio
async def test_liepin_service_builds_ok_result_from_extracted_cards() -> None:
    """Successful searches should preserve extracted candidates."""

    class FakeSession:
        def __init__(self) -> None:
            self.last_phrase = ""
            self.last_page = 0

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            self.last_phrase = phrase
            self.last_page = page_number
            return "ok"

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="lp-1",
                display_name="张先生",
                headline="Agent开发 / 上海 / 6年 / 本科",
                city="上海",
                years_experience="6年",
                education="本科",
                detail_url="https://example.com/candidate/1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    async def fake_extract_total(page):
        return 139

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=fake_extract_total,
    )

    result = await service.search_candidates(
        {
            "position": "Agent开发",
            "expected_city": "上海",
            "experience": "6年",
            "education": "本科",
        },
        page=2,
        result_limit=1,
    )

    assert fake_session.last_phrase == "Agent开发"
    assert fake_session.last_page == 2
    assert result.status == "ok"
    assert result.total == 139
    assert result.summary_markdown.startswith("### 猎聘")
    assert "[打开猎聘详情](https://example.com/candidate/1)" in result.summary_markdown
    assert len(result.candidates) == 1
    assert result.candidates[0].display_name == "张先生"


@pytest.mark.asyncio
async def test_liepin_service_returns_frontend_candidates_without_constraint_post_filter() -> None:
    """Visible recruiter cards should pass through unchanged even when structured fields conflict."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="good-1",
                display_name="刘**",
                headline="Python算法工程师 / 上海 / 9年 / 本科",
                city="上海",
                years_experience="9年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-1",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="bad-city",
                display_name="王**",
                headline="Python算法工程师 / 北京 / 9年 / 本科",
                city="北京",
                years_experience="9年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/bad-city",
                page=page_number,
                rank=2,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="bad-years",
                display_name="张**",
                headline="Python算法工程师 / 上海 / 3年 / 本科",
                city="上海",
                years_experience="3年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/bad-years",
                page=page_number,
                rank=3,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="bad-title",
                display_name="李**",
                headline="销售经理 / 上海 / 10年 / 本科",
                city="上海",
                years_experience="10年",
                education="本科",
                current_title="销售经理",
                detail_url="https://example.com/candidate/bad-title",
                page=page_number,
                rank=4,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience_min": 6,
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "good-1",
        "bad-city",
        "bad-years",
        "bad-title",
    ]


@pytest.mark.asyncio
async def test_liepin_service_returns_frontend_visible_cards_without_local_post_filtering() -> None:
    """Frontend-visible recruiter cards should be returned as-is without local constraint filtering."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="frontend-title",
                display_name="赵**",
                headline="算法工程师 / 北京 / 3年 / 大专",
                city="北京",
                expected_city="北京",
                years_experience="3年",
                education="大专",
                current_title="算法工程师",
                detail_url="https://example.com/candidate/frontend-title",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "frontend-title",
    ]


@pytest.mark.asyncio
async def test_liepin_service_normalizes_experience_years_alias_without_local_post_filtering() -> None:
    """Model-shaped aliases should still normalize correctly even when local filtering is disabled."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="good-7y",
                display_name="周**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-7y",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="bad-3y",
                display_name="吴**",
                headline="Python算法工程师 / 上海 / 3年 / 本科",
                city="上海",
                years_experience="3年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/bad-3y",
                page=page_number,
                rank=2,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "job_title": "Python算法工程师",
            "location": "上海",
            "experience_years": "6年以上",
            "education": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "good-7y",
        "bad-3y",
    ]


@pytest.mark.asyncio
async def test_liepin_service_returns_frontend_results_even_when_title_split_does_not_match_locally() -> None:
    """Frontend-visible cards should still be returned instead of failing closed on local title logic."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="python-backend",
                display_name="傅**",
                headline="Python / 上海 / 11年 / 本科",
                city="上海",
                years_experience="11年",
                education="本科",
                current_title="Python后端开发工程师",
                detail_url="https://example.com/candidate/python-backend",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="algo-only",
                display_name="李**",
                headline="算法工程师 / 上海 / 10年 / 本科",
                city="上海",
                years_experience="10年",
                education="本科",
                current_title="算法工程师",
                detail_url="https://example.com/candidate/algo-only",
                page=page_number,
                rank=2,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "python-backend",
        "algo-only",
    ]
    assert result.stop_current_turn is False
    assert result.avoid_reopen_browser is False


@pytest.mark.asyncio
async def test_liepin_service_returns_all_frontend_keyword_results_without_title_post_filter() -> None:
    """Recruiter-side keyword results should be returned as rendered by the frontend."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="bad-title",
                display_name="赵**",
                headline="算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                years_experience="8年",
                education="本科",
                current_title="算法工程师",
                detail_url="https://example.com/candidate/bad-title",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="good-title",
                display_name="钱**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-title",
                page=page_number,
                rank=2,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "bad-title",
        "good-title",
    ]


@pytest.mark.asyncio
async def test_liepin_service_keeps_explicit_structured_conflicts_when_frontend_shows_them() -> None:
    """Explicitly conflicting structured fields should still pass through if the recruiter frontend shows them."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="bad-years",
                display_name="赵**",
                headline="Python算法工程师 / 上海 / 3年 / 本科",
                city="上海",
                expected_city="上海",
                years_experience="3年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/bad-years",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="good-match",
                display_name="孙**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                expected_city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-match",
                page=page_number,
                rank=2,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "bad-years",
        "good-match",
    ]


@pytest.mark.asyncio
async def test_liepin_service_keeps_matching_recruiter_card_when_structured_fields_are_missing() -> None:
    """Trusted recruiter cards may pass missing structured fields, but not explicit mismatches."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="frontend-visible",
                display_name="赵**",
                headline="Python算法工程师",
                city="",
                expected_city="",
                years_experience="",
                education="",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/frontend-visible",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "frontend-visible",
    ]


@pytest.mark.asyncio
async def test_liepin_service_preserves_previous_specific_title_when_follow_up_broadens_it() -> None:
    """Follow-up refinements should not silently broaden the previous successful title."""

    class FakeSession:
        def __init__(self) -> None:
            self.phrases: list[str] = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, page_number
            self.phrases.append(phrase)
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page
        if fake_session.phrases[-1] != "HR产品经理":
            return []
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="hrpm-1",
                display_name="王**",
                headline="人力信息系统HRIS / 深圳-龙华区 / 13年 / 本科",
                city="深圳-龙华区",
                expected_city="青岛",
                years_experience="13年",
                education="本科",
                current_title="人力信息系统HRIS",
                expected_title="HR产品经理",
                detail_url="https://example.com/candidate/hrpm-1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    first_result = await service.search_candidates(
        {
            "title": "HR产品经理",
            "city": "青岛",
        },
    )
    second_result = await service.search_candidates(
        {
            "title": "产品经理",
            "city": "青岛",
        },
    )

    assert first_result.status == "ok"
    assert second_result.status == "ok"
    assert fake_session.phrases == ["HR产品经理", "HR产品经理"]


@pytest.mark.asyncio
async def test_liepin_service_retries_with_city_in_phrase_when_recruiter_city_filter_is_unapplied() -> None:
    """If recruiter city filters fail to apply, retry with the city added back into the phrase."""

    class FakeSession:
        def __init__(self) -> None:
            self.phrases: list[str] = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, page_number
            self.phrases.append(phrase)
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": False,
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page
        if fake_session.phrases[-1] != "HR产品经理 青岛":
            return [
                CandidateSummary(
                    site="liepin",
                    candidate_id="hangzhou-noise",
                    display_name="汤**",
                    headline="产品经理 / 杭州 / 10年 / 本科",
                    city="杭州",
                    expected_city="杭州",
                    years_experience="10年",
                    education="本科",
                    current_title="HR产品经理",
                    expected_title="产品经理",
                    detail_url="https://example.com/candidate/hangzhou-noise",
                    page=page_number,
                    rank=1,
                ),
            ][:max_cards]

        return [
            CandidateSummary(
                site="liepin",
                candidate_id="qingdao-hit",
                display_name="周**",
                headline="海外人力产品经理 / 青岛 / 7年 / 硕士",
                city="青岛",
                expected_city="青岛",
                years_experience="7年",
                education="硕士",
                current_title="海外人力产品经理",
                expected_title="人力产品经理",
                detail_url="https://example.com/candidate/qingdao-hit",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "HR产品经理",
            "expected_city": "青岛",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "qingdao-hit",
    ]
    assert fake_session.phrases == [
        "HR产品经理",
        "HR产品经理 青岛",
    ]


@pytest.mark.asyncio
async def test_liepin_service_aggregates_across_pages_until_result_limit_is_met() -> None:
    """Large result limits should keep paging until enough candidates are accumulated."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.search_calls.append((phrase, page_number))
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="liepin",
                candidate_id=f"p{page_number}-{rank}",
                display_name=f"候选人{page_number}-{rank}",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                expected_city="上海",
                years_experience="8年",
                education="本科",
                current_title="Python算法工程师",
                detail_url=f"https://example.com/candidate/p{page_number}-{rank}",
                page=page_number,
                rank=rank,
            )
            for rank in range(1, 21)
        ]

    async def fake_extract_total(page):
        _ = page
        return 80

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=fake_extract_total,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "education": "本科",
        },
        result_limit=45,
    )

    assert result.status == "ok"
    assert result.total == 80
    assert len(result.candidates) == 45
    assert [candidate.candidate_id for candidate in result.candidates[:3]] == [
        "p1-1",
        "p1-2",
        "p1-3",
    ]
    assert [candidate.candidate_id for candidate in result.candidates[-3:]] == [
        "p3-3",
        "p3-4",
        "p3-5",
    ]
    assert fake_session.search_calls == [
        ("Python算法工程师", 1),
        ("Python算法工程师", 2),
        ("Python算法工程师", 3),
    ]


@pytest.mark.asyncio
async def test_liepin_service_next_page_reuses_last_successful_query() -> None:
    """Follow-up paging should reuse the last successful query and increment the page."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.search_calls.append((phrase, page_number))
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="liepin",
                candidate_id=f"p{page_number}-1",
                display_name=f"候选人{page_number}-1",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                expected_city="上海",
                years_experience="8年",
                education="本科",
                current_title="Python算法工程师",
                detail_url=f"https://example.com/candidate/p{page_number}-1",
                page=page_number,
                rank=1,
            ),
        ]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    first_result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "education": "本科",
        },
        result_limit=1,
    )
    second_result = await service.next_page()

    assert first_result.status == "ok"
    assert second_result.status == "ok"
    assert second_result.page == 2
    assert [candidate.candidate_id for candidate in second_result.candidates] == [
        "p2-1",
    ]
    assert fake_session.search_calls == [
        ("Python算法工程师", 1),
        ("Python算法工程师", 2),
    ]


@pytest.mark.asyncio
async def test_liepin_service_unions_expected_and_current_city_searches() -> None:
    """OR-city requests should merge recruiter results from expected and current city searches."""

    class FakeSession:
        def __init__(self) -> None:
            self.applied_queries: list[dict[str, str]] = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, page_number
            payload = query.model_dump(mode="json")
            self.applied_queries.append(payload)
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": bool(payload["expected_city"]),
                    "current_city": bool(payload["current_city"]),
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page
        current_query = fake_session.applied_queries[-1]
        if current_query["expected_city"]:
            return [
                CandidateSummary(
                    site="liepin",
                    candidate_id="expected-city-match",
                    display_name="王**",
                    headline="HRIS / 深圳 / 13年 / 本科",
                    city="深圳",
                    expected_city="青岛",
                    years_experience="13年",
                    education="本科",
                    current_title="HRIS",
                    expected_title="HR产品经理",
                    detail_url="https://example.com/candidate/expected-city-match",
                    page=page_number,
                    rank=1,
                ),
            ][:max_cards]

        return [
            CandidateSummary(
                site="liepin",
                candidate_id="current-city-match",
                display_name="李**",
                headline="人力产品经理 / 青岛 / 8年 / 本科",
                city="青岛",
                expected_city="苏州",
                years_experience="8年",
                education="本科",
                current_title="人力产品经理",
                expected_title="人力产品经理",
                detail_url="https://example.com/candidate/current-city-match",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="expected-city-match",
                display_name="王**",
                headline="HRIS / 深圳 / 13年 / 本科",
                city="深圳",
                expected_city="青岛",
                years_experience="13年",
                education="本科",
                current_title="HRIS",
                expected_title="HR产品经理",
                detail_url="https://example.com/candidate/expected-city-match",
                page=page_number,
                rank=2,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "HR产品经理",
            "expected_city": "青岛",
            "current_city": "青岛",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "expected-city-match",
        "current-city-match",
    ]
    assert [
        (
            query["expected_city"],
            query["current_city"],
        )
        for query in fake_session.applied_queries
    ] == [
        ("青岛", ""),
        ("", "青岛"),
    ]


@pytest.mark.asyncio
async def test_liepin_service_uses_keyword_phrase_without_redundant_structured_filters() -> None:
    """City, experience, and education should stay in recruiter filters, not the search box."""

    class FakeSession:
        def __init__(self) -> None:
            self.last_phrase = ""
            self.applied_queries = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, page_number
            self.last_phrase = phrase
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, page_number
            self.applied_queries.append(query.model_dump(mode="json"))

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="good-1",
                display_name="赵**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "degree": "本科",
        },
    )

    assert result.status == "ok"
    assert fake_session.last_phrase == "Python算法工程师"
    assert fake_session.applied_queries == [
        {
            "sites": [],
            "keyword": "",
            "position": "Python算法工程师",
            "company": "",
            "current_city": "",
            "expected_city": "上海",
            "experience": "6年以上",
            "education": "本科",
            "current_industry": "",
            "expected_industry": "",
            "current_function": "",
            "expected_function": "",
            "current_salary": "",
            "expected_salary": "",
            "school": "",
            "major": "",
            "active_status": "",
            "job_status": "",
            "management_experience": "",
            "page": 1,
            "page_size_limit": 20,
        },
    ]


@pytest.mark.asyncio
async def test_liepin_service_normalizes_json_string_queries_before_search() -> None:
    """JSON-string queries should still pass through alias normalization."""

    class FakeSession:
        def __init__(self) -> None:
            self.last_phrase = ""

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            self.last_phrase = phrase
            return "ok"

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        return []

    async def fake_extract_total(page):
        return 0

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=fake_extract_total,
    )

    await service.search_candidates(
        '{"keywords":"Python算法工程师","location":"上海","experience_year":"6年以上","education":"本科"}',
    )

    assert fake_session.last_phrase == "Python算法工程师"


@pytest.mark.asyncio
async def test_liepin_service_normalizes_plain_string_queries_before_search() -> None:
    """Plain natural-language strings should map obvious filters into the shared query contract."""

    class FakeSession:
        def __init__(self) -> None:
            self.last_phrase = ""
            self.applied_queries = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, page_number
            self.last_phrase = phrase
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, page_number
            self.applied_queries.append(query.model_dump(mode="json"))
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="good-1",
                display_name="赵**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                expected_city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates("上海 Python算法工程师 6年以上 本科")

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == ["good-1"]
    assert fake_session.last_phrase == "Python算法工程师"
    assert fake_session.applied_queries == [
        {
            "sites": [],
            "keyword": "",
            "position": "Python算法工程师",
            "company": "",
            "current_city": "",
            "expected_city": "上海",
            "experience": "6年以上",
            "education": "本科",
            "current_industry": "",
            "expected_industry": "",
            "current_function": "",
            "expected_function": "",
            "current_salary": "",
            "expected_salary": "",
            "school": "",
            "major": "",
            "active_status": "",
            "job_status": "",
            "management_experience": "",
            "page": 1,
            "page_size_limit": 20,
        },
    ]


@pytest.mark.asyncio
async def test_liepin_service_normalizes_city_prefixed_plain_string_queries() -> None:
    """Compact natural-language requests like '找个青岛的人力产品经理' should still split city and position."""

    class FakeSession:
        def __init__(self) -> None:
            self.last_phrase = ""
            self.applied_queries = []

        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            _ = page, page_number
            self.last_phrase = phrase
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, page_number
            self.applied_queries.append(query.model_dump(mode="json"))
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                },
            }

        async def check_status(self, page):
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="qingdao-1",
                display_name="周**",
                headline="人力产品经理 / 青岛 / 8年 / 本科",
                city="青岛",
                expected_city="青岛",
                years_experience="8年",
                education="本科",
                current_title="人力产品经理",
                detail_url="https://example.com/candidate/qingdao-1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates("找个青岛的人力产品经理")

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == ["qingdao-1"]
    assert fake_session.last_phrase == "人力产品经理"
    assert fake_session.applied_queries[0]["expected_city"] == "青岛"
    assert fake_session.applied_queries[0]["position"] == "人力产品经理"


@pytest.mark.asyncio
async def test_liepin_service_fail_closes_unreliable_candidate_extraction() -> None:
    """Garbage page-level results should not be reported as successful candidates."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="search",
                display_name="共有 3000+ 份简历",
                headline="共有",
                city="共有",
                detail_url="https://lpt.liepin.com/search",
                page=page_number,
                rank=1,
            ),
            CandidateSummary(
                site="liepin",
                candidate_id="search",
                display_name=(
                    "30天内活跃 康** 44岁 20年 本科 重庆-江北区 期望： 重庆建筑工程管理/项目经理15-20K "
                    "工程管理/勘察/监理 自由职业 合伙人2025.11-至今(4个月) 上海普赛建筑设计咨询有限公司"
                ),
                headline="重庆 / 20年 / 本科",
                city="重庆",
                years_experience="20年",
                education="本科",
                detail_url="https://lpt.liepin.com/search",
                page=page_number,
                rank=2,
            ),
        ]

    async def fake_extract_total(page):
        return 3000

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=fake_extract_total,
    )

    result = await service.search_candidates("Python算法工程师 上海 6年以上 本科")

    assert result.status == "extraction_unreliable"
    assert result.stop_current_turn is True
    assert result.avoid_reopen_browser is True
    assert "browser_use" in result.message
    assert result.candidates == []


@pytest.mark.asyncio
async def test_liepin_service_retries_candidate_extraction_before_failing() -> None:
    """Transient recruiter rendering noise should be retried before declaring extraction failure."""

    class FakePage:
        def __init__(self) -> None:
            self.wait_calls: list[int] = []

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_calls.append(timeout_ms)

    class FakeSession:
        def __init__(self) -> None:
            self.page = FakePage()

        async def ensure_started(self):
            return self.page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page, query, page_number
            return {
                "search_surface": "recruiter",
                "trusted_site_filters": True,
                "applied_filters": {
                    "expected_city": True,
                    "experience": True,
                    "education": True,
                },
            }

        async def check_status(self, page):
            _ = page
            return "ok"

    fake_session = FakeSession()
    extract_calls = 0

    async def fake_extract_candidates(page, page_number, max_cards):
        nonlocal extract_calls
        _ = page
        extract_calls += 1
        if extract_calls == 1:
            return [
                CandidateSummary(
                    site="liepin",
                    candidate_id="search",
                    display_name="共有 3000+ 份简历",
                    headline="共有",
                    city="共有",
                    detail_url="https://lpt.liepin.com/search",
                    page=page_number,
                    rank=1,
                ),
            ]

        return [
            CandidateSummary(
                site="liepin",
                candidate_id="good-1",
                display_name="赵**",
                headline="Python算法工程师 / 上海 / 7年 / 本科",
                city="上海",
                expected_city="上海",
                years_experience="7年",
                education="本科",
                current_title="Python算法工程师",
                detail_url="https://example.com/candidate/good-1",
                page=page_number,
                rank=1,
            ),
        ][:max_cards]

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "上海",
            "experience": "6年以上",
            "education": "本科",
        },
    )

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == ["good-1"]
    assert extract_calls == 2
    assert fake_session.page.wait_calls


@pytest.mark.asyncio
async def test_liepin_service_writes_debug_dump_for_unreliable_extraction(
    tmp_path,
) -> None:
    """Unreliable extraction should persist debug evidence when enabled."""

    class FakeSession:
        async def ensure_started(self):
            return object()

        async def search_phrase(self, page, phrase, page_number):
            return "ok"

        async def check_status(self, page):
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        return [
            CandidateSummary(
                site="liepin",
                candidate_id="search",
                display_name="共有 3000+ 份简历",
                headline="共有",
                city="共有",
                detail_url="https://lpt.liepin.com/search",
                page=page_number,
                rank=1,
            ),
        ]

    async def fake_capture_debug_snapshot(page, max_cards):
        return {
            "url": "https://lpt.liepin.com/search",
            "title": "搜索人才",
            "raw_cards": [{"href": "https://lpt.liepin.com/search", "text": "共有 3000+ 份简历"}],
        }

    service = LiepinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["liepin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            liepin_profile_dir="/tmp/liepin",
            liepin_debug_dump_dir=str(tmp_path),
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
        capture_debug_snapshot=fake_capture_debug_snapshot,
    )

    result = await service.search_candidates("Python算法工程师 上海 6年以上 本科")

    assert result.status == "extraction_unreliable"
    debug_files = sorted(tmp_path.glob("liepin-extraction-unreliable-*.json"))
    assert len(debug_files) == 1

    payload = json.loads(debug_files[0].read_text(encoding="utf-8"))
    assert payload["phrase"] == "Python算法工程师"
    assert payload["query"]["position"] == "Python算法工程师"
    assert payload["query"]["expected_city"] == "上海"
    assert payload["query"]["experience"] == "6年以上"
    assert payload["query"]["education"] == "本科"
    assert payload["snapshot"]["title"] == "搜索人才"
    assert payload["extracted_candidates"][0]["display_name"] == "共有 3000+ 份简历"
