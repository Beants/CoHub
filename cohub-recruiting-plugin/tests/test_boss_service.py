# -*- coding: utf-8 -*-
"""Smoke tests for the BOSS MCP package surface."""

import pytest

from cohub_recruiting.config import (
    MatchModelConfig,
    RecruitingRuntimeConfig,
)
from cohub_recruiting.models import CandidateSummary


def test_boss_server_exports_expected_tool_functions() -> None:
    """The BOSS MCP entrypoint should expose the standard recruiting tool surface."""
    from cohub_recruiting.boss_mcp import server

    assert callable(server.boss_status)
    assert callable(server.boss_prepare_browser)
    assert callable(server.boss_search_candidates)
    assert callable(server.boss_next_page)
    assert callable(server.boss_continue_last_search)
    assert callable(server.boss_close_browser)


@pytest.mark.asyncio
async def test_boss_service_close_browser_reports_closed() -> None:
    """The BOSS service should expose the standard close-browser response."""
    from cohub_recruiting.boss_mcp.service import (
        BossService,
    )

    service = BossService()

    result = await service.close_browser()

    assert result == {"site": "boss", "closed": True}


@pytest.mark.asyncio
async def test_boss_prepare_browser_returns_same_window_hint() -> None:
    """Browser preparation should tell the model to reuse the same window."""

    class FakeSession:
        def __init__(self) -> None:
            self.launch_config = type(
                "LaunchConfig",
                (),
                {
                    "profile_dir": "/tmp/boss",
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
            _ = page
            return "captcha_required"

    fake_session = FakeSession()

    from cohub_recruiting.boss_mcp.service import (
        BossService,
    )

    service = BossService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["boss"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            boss_profile_dir="/tmp/boss",
        ),
        session_factory=lambda config: fake_session,
    )

    result = await service.prepare_browser()

    assert result["status"] == "captcha_required"
    assert "boss_continue_last_search" in result["message"]
    assert "同一个 BOSS 浏览器窗口" in result["message"]
    assert result["avoid_reopen_browser"] is True
    assert result["stop_current_turn"] is True
    assert fake_session.ensure_entry_page_calls == 1


@pytest.mark.asyncio
async def test_boss_service_returns_login_required_envelope() -> None:
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

    from cohub_recruiting.boss_mcp.service import (
        BossService,
    )

    service = BossService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["boss"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            boss_profile_dir="/tmp/boss",
        ),
        session_factory=lambda config: FakeSession(),
    )

    result = await service.search_candidates({"keyword": "Python算法工程师"})

    assert result.site == "boss"
    assert result.status == "not_logged_in"
    assert result.continue_tool == "boss_continue_last_search"
    assert "同一个 BOSS 浏览器窗口" in result.message
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert result.candidates == []


@pytest.mark.asyncio
async def test_boss_service_builds_ok_result_from_extracted_cards() -> None:
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
                site="boss",
                candidate_id="boss-1",
                display_name="张先生",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                years_experience="8年",
                education="本科",
                detail_url="https://example.com/boss/1",
                extra_attributes={
                    "活跃度": "今日活跃",
                    "年龄": "32",
                },
                page=page_number,
                rank=1,
            ),
        ]

    async def fake_extract_total(page):
        _ = page
        return 28

    from cohub_recruiting.boss_mcp.service import (
        BossService,
    )

    service = BossService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["boss"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            boss_profile_dir="/tmp/boss",
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
        "活跃度": "今日活跃",
        "年龄": "32",
    }
    assert result.summary_markdown.startswith("### BOSS直聘")
    assert "[打开BOSS直聘详情](https://example.com/boss/1)" in result.summary_markdown


@pytest.mark.asyncio
async def test_boss_continue_last_search_checks_status_before_retrying() -> None:
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

    from cohub_recruiting.boss_mcp.service import (
        BossService,
    )

    service = BossService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["boss"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            boss_profile_dir="/tmp/boss",
        ),
        session_factory=lambda config: fake_session,
    )

    await service.search_candidates({"keyword": "Python算法工程师"})
    result = await service.continue_last_search()

    assert result.status == "captcha_required"
    assert result.continue_tool == "boss_continue_last_search"
    assert result.reuse_same_browser_window is True
    assert result.avoid_reopen_browser is True
    assert result.stop_current_turn is True
    assert fake_session.search_phrase_calls == 1


@pytest.mark.asyncio
async def test_boss_service_next_page_reuses_last_successful_query() -> None:
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
                site="boss",
                candidate_id=f"boss-{page_number}",
                display_name=f"候选人{page_number}",
                headline="Python算法工程师 / 上海 / 8年 / 本科",
                city="上海",
                years_experience="8年",
                education="本科",
                detail_url=f"https://example.com/boss/{page_number}",
                page=page_number,
                rank=1,
            ),
        ]

    from cohub_recruiting.boss_mcp.service import (
        BossService,
    )

    service = BossService(
        config_loader=lambda: RecruitingRuntimeConfig(
            enabled_sites=["boss"],
            failure_mode="partial_success",
            default_page=1,
            default_result_limit=20,
            match_model=MatchModelConfig(),
            boss_profile_dir="/tmp/boss",
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
        "boss-2",
    ]
    assert fake_session.search_calls == [
        ("Python算法工程师", 1),
        ("Python算法工程师", 2),
    ]
