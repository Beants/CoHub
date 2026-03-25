# -*- coding: utf-8 -*-
"""Smoke tests for the Zhaopin MCP package surface."""

import json

import pytest

from copaw.agents.skills.recruiting_assistant.config import (
    MatchModelConfig,
    RecruitingRuntimeConfig,
)
from copaw.agents.skills.recruiting_assistant.models import CandidateSummary


def test_zhaopin_server_exports_expected_tool_functions() -> None:
    """The Zhaopin MCP entrypoint should expose the standard recruiting tool surface."""
    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp import server

    assert callable(server.zhaopin_status)
    assert callable(server.zhaopin_prepare_browser)
    assert callable(server.zhaopin_search_candidates)
    assert callable(server.zhaopin_next_page)
    assert callable(server.zhaopin_continue_last_search)
    assert callable(server.zhaopin_close_browser)


@pytest.mark.asyncio
async def test_zhaopin_service_close_browser_reports_closed() -> None:
    """The Zhaopin service should expose the standard close-browser response."""
    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService()

    result = await service.close_browser()

    assert result == {"site": "zhaopin", "closed": True}


@pytest.mark.asyncio
async def test_zhaopin_prepare_browser_returns_same_window_hint() -> None:
    """Browser preparation should tell the model to reuse the same window."""

    class FakeSession:
        def __init__(self) -> None:
            self.launch_config = type(
                "LaunchConfig",
                (),
                {
                    "profile_dir": "/tmp/zhaopin",
                    "browser_kind": "chromium",
                    "executable_path": (
                        "/Applications/Google Chrome.app/test"
                    ),
                },
            )()
            self.ensure_entry_page_calls = 0

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            self.ensure_entry_page_calls += 1
            return page

        async def check_status(self, page):
            _ = page
            return "captcha_required"

    fake_session = FakeSession()

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
    )

    result = await service.prepare_browser()

    assert result["status"] == "captcha_required"
    assert "zhaopin_continue_last_search" in result["message"]
    assert "同一个智联招聘浏览器窗口" in result["message"]
    assert result["avoid_reopen_browser"] is True
    assert result["stop_current_turn"] is True
    assert fake_session.ensure_entry_page_calls == 1


@pytest.mark.asyncio
async def test_zhaopin_service_returns_login_required_envelope() -> None:
    """Manual verification should be returned as a structured site status."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "not_logged_in"

        async def check_status(self, page):
            _ = page
            return "not_logged_in"

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: FakeSession(),
    )

    result = await service.search_candidates({"keyword": "Python算法工程师"})

    assert result.site == "zhaopin"
    assert result.status == "not_logged_in"
    assert result.continue_tool == "zhaopin_continue_last_search"
    assert "同一个智联招聘浏览器窗口" in result.message
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert result.candidates == []


@pytest.mark.asyncio
async def test_zhaopin_service_builds_ok_result_from_extracted_cards() -> None:
    """Successful searches should preserve extracted recruiter candidates."""

    class FakeSession:
        def __init__(self) -> None:
            self.last_phrase = ""
            self.last_page = 0

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.last_phrase = phrase
            self.last_page = page_number
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id="zhaopin-1",
                display_name="张先生",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                years_experience="8年",
                education="本科",
                detail_url="https://rd6.zhaopin.com/resume/detail/1",
                extra_attributes={
                    "最近活跃": "今日活跃",
                    "年龄": "32",
                },
                page=page_number,
                rank=1,
            ),
        ]

    async def fake_extract_total(page):
        _ = page
        return 28

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
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
        page=2,
        result_limit=5,
    )

    assert fake_session.last_phrase == "Python算法工程师"
    assert fake_session.last_page == 2
    assert result.status == "ok"
    assert result.total == 28
    assert len(result.candidates) == 1
    assert result.candidates[0].extra_attributes == {
        "最近活跃": "今日活跃",
        "年龄": "32",
    }
    assert result.summary_markdown.startswith("### 智联招聘")
    assert (
        "[打开智联招聘详情](https://rd6.zhaopin.com/resume/detail/1)"
        in result.summary_markdown
    )


@pytest.mark.asyncio
async def test_zhaopin_service_returns_full_current_page_by_default() -> None:
    """Without an explicit limit, Zhaopin should return every extracted card on the page."""

    class FakeSession:
        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    observed_max_cards: list[int] = []

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page
        observed_max_cards.append(max_cards)
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id=f"zhaopin-{index}",
                display_name=f"候选人{index}",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                years_experience="8年",
                education="本科",
                detail_url=f"https://rd6.zhaopin.com/resume/detail/{index}",
                page=page_number,
                rank=index,
            )
            for index in range(1, 4)
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=1,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates({"keyword": "Python算法工程师"})

    assert observed_max_cards == [0]
    assert [candidate.candidate_id for candidate in result.candidates] == [
        "zhaopin-1",
        "zhaopin-2",
        "zhaopin-3",
    ]
    assert "候选人3" in result.summary_markdown


@pytest.mark.asyncio
async def test_zhaopin_service_applies_structured_filters_before_paging() -> None:
    """When structured filters are available, search should land on page 1 first and then filter."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []
            self.filter_calls: list[dict[str, object]] = []

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.search_calls.append((phrase, page_number))
            return "ok"

        async def apply_query_filters(self, page, query, page_number=1):
            _ = page
            self.filter_calls.append(
                {
                    "expected_city": query.expected_city,
                    "current_city": query.current_city,
                    "experience": query.experience,
                    "education": query.education,
                    "page_number": page_number,
                },
            )
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

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id="zhaopin-1",
                display_name="张先生",
                headline="Python算法工程师 / 青岛 / 8年 / 本科",
                city="青岛",
                years_experience="8年",
                education="本科",
                detail_url="https://rd6.zhaopin.com/resume/detail/1",
                page=page_number,
                rank=1,
            ),
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "expected_city": "青岛",
            "experience": "6年以上",
            "education": "本科",
        },
        page=2,
    )

    assert result.status == "ok"
    assert fake_session.search_calls == [("Python算法工程师", 1)]
    assert fake_session.filter_calls == [
        {
            "expected_city": "青岛",
            "current_city": "",
            "experience": "6年以上",
            "education": "本科",
            "page_number": 2,
        },
    ]


@pytest.mark.asyncio
async def test_zhaopin_continue_last_search_checks_status_before_retrying() -> None:
    """Resume should not navigate again while manual verification is unfinished."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_phrase_calls = 0

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            self.search_phrase_calls += 1
            return "captcha_required"

        async def check_status(self, page):
            _ = page
            return "captcha_required"

    fake_session = FakeSession()

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
    )

    await service.search_candidates({"keyword": "Python算法工程师"})
    result = await service.continue_last_search()

    assert result.status == "captcha_required"
    assert result.continue_tool == "zhaopin_continue_last_search"
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert fake_session.search_phrase_calls == 1


@pytest.mark.asyncio
async def test_zhaopin_service_next_page_reuses_last_successful_query() -> None:
    """Follow-up paging should reuse the last successful query and increment the page."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.search_calls.append((phrase, page_number))
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id=f"zhaopin-{page_number}",
                display_name=f"候选人{page_number}",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                years_experience="8年",
                education="本科",
                detail_url=f"https://rd6.zhaopin.com/resume/detail/{page_number}",
                page=page_number,
                rank=1,
            ),
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    first_result = await service.search_candidates(
        {"title": "Python算法工程师", "city": "上海"},
        result_limit=1,
    )
    second_result = await service.next_page()

    assert first_result.status == "ok"
    assert second_result.status == "ok"
    assert second_result.page == 2
    assert [candidate.candidate_id for candidate in second_result.candidates] == [
        "zhaopin-2",
    ]
    assert fake_session.search_calls == [
        ("Python算法工程师", 1),
        ("Python算法工程师", 2),
    ]


@pytest.mark.asyncio
async def test_zhaopin_service_aggregates_across_pages_when_result_limit_exceeds_page_cap() -> None:
    """Explicit limits above one page should accumulate unique candidates across pages."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.search_calls.append((phrase, page_number))
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id=f"zhaopin-{page_number}-{index}",
                display_name=f"候选人{page_number}-{index}",
                headline="Python算法工程师 / 深圳 / 3年 / 硕士",
                city="深圳",
                years_experience="3年",
                education="硕士",
                detail_url=(
                    f"https://rd6.zhaopin.com/resume/detail/{page_number}-{index}"
                ),
                page=page_number,
                rank=index,
            )
            for index in range(1, 21)
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates(
        {"keyword": "Python算法工程师"},
        result_limit=25,
    )

    assert result.status == "ok"
    assert result.page == 1
    assert len(result.candidates) == 25
    assert result.candidates[0].candidate_id == "zhaopin-1-1"
    assert result.candidates[-1].candidate_id == "zhaopin-2-5"
    assert fake_session.search_calls == [
        ("Python算法工程师", 1),
        ("Python算法工程师", 2),
    ]


@pytest.mark.asyncio
async def test_zhaopin_service_next_page_starts_after_last_aggregated_page_end() -> None:
    """Follow-up paging after aggregation should start from the first unseen results page."""

    class FakeSession:
        def __init__(self) -> None:
            self.search_calls: list[tuple[str, int]] = []

        async def ensure_started(self):
            return "page"

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page
            self.search_calls.append((phrase, page_number))
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    fake_session = FakeSession()

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id=f"zhaopin-{page_number}-{index}",
                display_name=f"候选人{page_number}-{index}",
                headline="Python算法工程师 / 深圳 / 3年 / 硕士",
                city="深圳",
                years_experience="3年",
                education="硕士",
                detail_url=(
                    f"https://rd6.zhaopin.com/resume/detail/{page_number}-{index}"
                ),
                page=page_number,
                rank=index,
            )
            for index in range(1, 21)
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    first_result = await service.search_candidates(
        {"keyword": "Python算法工程师"},
        result_limit=25,
    )
    second_result = await service.next_page()

    assert first_result.status == "ok"
    assert second_result.status == "ok"
    assert second_result.page == 3
    assert second_result.candidates[0].candidate_id == "zhaopin-3-1"
    assert second_result.candidates[-1].candidate_id == "zhaopin-4-5"
    assert fake_session.search_calls == [
        ("Python算法工程师", 1),
        ("Python算法工程师", 2),
        ("Python算法工程师", 3),
        ("Python算法工程师", 4),
    ]


@pytest.mark.asyncio
async def test_zhaopin_service_returns_extraction_unreliable_for_bad_candidate_batch() -> None:
    """Clearly non-candidate batches should stop the turn as extraction_unreliable."""

    class FakeSession:
        async def ensure_started(self):
            return object()

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id="search",
                display_name="搜索人才",
                headline="搜索人才",
                city="搜索人才",
                detail_url="https://rd6.zhaopin.com/app/search",
                page=page_number,
                rank=1,
            ),
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates({"keyword": "Python算法工程师"})

    assert result.status == "extraction_unreliable"
    assert result.stop_current_turn is True
    assert result.avoid_reopen_browser is True
    assert "browser_use" in result.message
    assert result.candidates == []


@pytest.mark.asyncio
async def test_zhaopin_service_retries_candidate_extraction_before_failing() -> None:
    """Transient extraction noise should be retried before declaring failure."""

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

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    fake_session = FakeSession()
    extract_calls = 0

    async def fake_extract_candidates(page, page_number, max_cards):
        nonlocal extract_calls
        _ = page, max_cards
        extract_calls += 1
        if extract_calls == 1:
            return [
                CandidateSummary(
                    site="zhaopin",
                    candidate_id="search",
                    display_name="搜索人才",
                    headline="搜索人才",
                    city="搜索人才",
                    detail_url="https://rd6.zhaopin.com/app/search",
                    page=page_number,
                    rank=1,
                ),
            ]
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id="good-1",
                display_name="郑先生",
                headline="10小时前在线 31岁 3年 硕士 在职-正在找工作",
                city="深圳",
                years_experience="3年",
                education="硕士",
                detail_url="https://rd6.zhaopin.com/app/search?resumeNumber=good-1",
                page=page_number,
                rank=1,
            ),
        ]

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
        ),
        session_factory=lambda config: fake_session,
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
    )

    result = await service.search_candidates({"keyword": "Python算法工程师"})

    assert result.status == "ok"
    assert [candidate.candidate_id for candidate in result.candidates] == ["good-1"]
    assert extract_calls == 2
    assert fake_session.page.wait_calls


@pytest.mark.asyncio
async def test_zhaopin_service_writes_debug_dump_for_unreliable_extraction(
    tmp_path,
) -> None:
    """Unreliable Zhaopin extraction should persist bounded debug evidence when enabled."""

    class FakeSession:
        async def ensure_started(self):
            return object()

        async def ensure_entry_page(self, page):
            return page

        async def search_phrase(self, page, phrase, page_number):
            _ = page, phrase, page_number
            return "ok"

        async def check_status(self, page):
            _ = page
            return "ok"

    async def fake_extract_candidates(page, page_number, max_cards):
        _ = page, max_cards
        return [
            CandidateSummary(
                site="zhaopin",
                candidate_id="search",
                display_name="搜索人才",
                headline="搜索人才",
                city="搜索人才",
                detail_url="https://rd6.zhaopin.com/app/search",
                page=page_number,
                rank=1,
            ),
        ]

    async def fake_capture_debug_snapshot(page, max_cards):
        _ = page, max_cards
        return {
            "url": "https://rd6.zhaopin.com/app/search",
            "title": "搜索人才",
            "raw_cards": [
                {
                    "name": "搜索人才",
                    "detail_url": "https://rd6.zhaopin.com/app/search",
                },
            ],
        }

    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import (
        ZhaopinService,
    )

    service = ZhaopinService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["zhaopin"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            zhaopin_profile_dir="/tmp/zhaopin",
            zhaopin_debug_dump_dir=str(tmp_path),
        ),
        session_factory=lambda config: FakeSession(),
        extract_candidates_from_page=fake_extract_candidates,
        extract_total_from_page=None,
        capture_debug_snapshot=fake_capture_debug_snapshot,
    )

    result = await service.search_candidates(
        {
            "title": "Python算法工程师",
            "city": "深圳",
            "experience": "1-3年",
            "education": "硕士",
        },
    )

    assert result.status == "extraction_unreliable"
    debug_files = sorted(tmp_path.glob("zhaopin-extraction-unreliable-*.json"))
    assert len(debug_files) == 1

    payload = json.loads(debug_files[0].read_text(encoding="utf-8"))
    assert payload["phrase"] == "Python算法工程师"
    assert payload["query"]["position"] == "Python算法工程师"
    assert payload["query"]["expected_city"] == "深圳"
    assert payload["query"]["experience"] == "1-3年"
    assert payload["query"]["education"] == "硕士"
    assert payload["snapshot"]["title"] == "搜索人才"
    assert payload["extracted_candidates"][0]["display_name"] == "搜索人才"
