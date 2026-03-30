# -*- coding: utf-8 -*-
"""Tests for Zhaopin recruiter extraction helpers."""

from textwrap import dedent

import pytest
from playwright.async_api import async_playwright

from copaw.config.utils import (
    get_playwright_chromium_executable_path,
    get_system_default_browser,
)
from cohub_recruiting.zhaopin_mcp.extractors import (
    _EXTRACT_CANDIDATES_SCRIPT,
    _coerce_positive_int,
    extract_candidates_from_page,
    extract_total_from_page,
    parse_candidate_card,
)


def test_parse_candidate_card_builds_candidate_summary() -> None:
    """Normalized raw card payloads should become shared candidate summaries."""
    summary = parse_candidate_card(
        {
            "candidate_id": "zp-1",
            "name": "张先生",
            "headline": "算法工程师 / 上海 / 8年 / 本科",
            "city": "上海",
            "experience": "8年",
            "education": "本科",
            "detail_url": "https://rd6.zhaopin.com/resume/detail/1",
            "extra_attributes": {"最近活跃": "今日活跃"},
        },
        site="zhaopin",
        page=1,
        rank=1,
    )

    assert summary is not None
    assert summary.site == "zhaopin"
    assert summary.candidate_id == "zp-1"
    assert summary.display_name == "张先生"
    assert summary.extra_attributes == {"最近活跃": "今日活跃"}


def test_parse_candidate_card_rejects_missing_identity_fields() -> None:
    """Cards without a name or detail link should be dropped."""
    assert (
        parse_candidate_card(
            {"name": "张先生"},
            site="zhaopin",
            page=1,
            rank=1,
        )
        is None
    )
    assert (
        parse_candidate_card(
            {"detail_url": "https://rd6.zhaopin.com/resume/detail/1"},
            site="zhaopin",
            page=1,
            rank=1,
        )
        is None
    )


def test_parse_candidate_card_rejects_navigation_like_entries() -> None:
    """Generic nav links should not be normalized as candidate cards."""
    assert (
        parse_candidate_card(
            {
                "name": "搜索人才",
                "detail_url": "https://rd6.zhaopin.com/app/search",
            },
            site="zhaopin",
            page=1,
            rank=1,
        )
        is None
    )


def test_parse_candidate_card_rejects_utility_entry_with_non_candidate_headline() -> None:
    """Utility links with counters should not be normalized as candidate cards."""
    assert (
        parse_candidate_card(
            {
                "name": "服务中心",
                "headline": "服务中心 0",
                "detail_url": "https://rd6.zhaopin.com/agent/recommend",
            },
            site="zhaopin",
            page=1,
            rank=1,
        )
        is None
    )


def test_parse_candidate_card_builds_detail_url_from_resume_number() -> None:
    """Generic search URLs should be upgraded when the card has a resume number."""
    summary = parse_candidate_card(
        {
            "name": "李先生",
            "headline": "29岁 6年 硕士 在职-看看机会",
            "city": "青岛",
            "experience": "6年",
            "education": "硕士",
            "detail_url": "https://rd6.zhaopin.com/app/search",
            "resume_number": "nqkwhnjPB5pk1H0XcYSe8ojJbqeO2Ov)",
        },
        site="zhaopin",
        page=1,
        rank=1,
    )

    assert summary is not None
    assert (
        summary.detail_url
        == "https://rd6.zhaopin.com/app/search?resumeNumber=nqkwhnjPB5pk1H0XcYSe8ojJbqeO2Ov%29"
    )


@pytest.mark.asyncio
async def test_extract_candidates_from_page_normalizes_evaluate_results() -> None:
    """The page extractor should skip invalid rows and preserve valid rows."""

    class FakePage:
        async def evaluate(self, script, payload):
            _ = script, payload
            return [
                {
                    "candidate_id": "zp-1",
                    "name": "张先生",
                    "headline": "算法工程师 / 上海 / 8年 / 本科",
                    "city": "上海",
                    "experience": "8年",
                    "education": "本科",
                    "detail_url": "https://rd6.zhaopin.com/resume/detail/1",
                    "extra_attributes": {"最近活跃": "今日活跃"},
                },
                {"name": "无效候选人"},
            ]

    candidates = await extract_candidates_from_page(FakePage(), 2, 10)

    assert [candidate.candidate_id for candidate in candidates] == ["zp-1"]
    assert candidates[0].page == 2
    assert candidates[0].rank == 1


@pytest.mark.asyncio
async def test_extract_total_from_page_coerces_visible_count() -> None:
    """Visible total-count text should be normalized into a positive integer."""

    class FakePage:
        async def evaluate(self, script):
            _ = script
            return "共278人"

    total = await extract_total_from_page(FakePage())

    assert total == 278
    assert _coerce_positive_int("共278人") == 278
    assert _coerce_positive_int("0") == 0
    assert _coerce_positive_int("") == 0


@pytest.mark.asyncio
async def test_extract_script_prefers_resume_cards_over_navigation() -> None:
    """The browser-side extractor should target result cards instead of nav links."""
    default_kind, default_path = get_system_default_browser()
    executable_path = None
    if default_kind == "chromium" and default_path:
        executable_path = default_path
    else:
        executable_path = get_playwright_chromium_executable_path()
    if not executable_path:
        pytest.skip("No Chromium executable is available for extractor script tests")

    html = dedent(
        """
        <div class="app-nav">
          <a href="/app/index">首页</a>
          <a href="/app/search">搜索人才</a>
        </div>
        <div class="search-result is-mt-12">
          <div class="search-resume-list">
            <div class="search-resume-item-wrap" data-detail-url="https://rd6.zhaopin.com/resume/detail/1">
              <div class="search-resume-item resume-item-exp">
                <div class="search-resume-item__inner">
                  <div class="resume-item__content resume-card-exp">
                    <div class="resume-item__basic">
                      <div class="resume-item__basic-info">
                        <div class="talent-basic-info talent-basic-exp old-circle-style">
                          <div class="talent-basic-info__title">
                            <div class="talent-basic-info__name">
                              <div title="李先生" class="talent-basic-info__name--inner is-mr-8">李先生</div>
                              <div class="global-active-tag__wrapper">
                                <div class="global-active-tag">半小时前有投递</div>
                              </div>
                            </div>
                          </div>
                          <div class="talent-basic-info__basic">
                            <span class="age-label">38岁</span>
                            <span class="work-years-label">10年</span>
                            <span class="education-label">硕士</span>
                            <span class="career-status-label">在职-正在找工作</span>
                          </div>
                          <div class="talent-basic-info__extra">
                            <div class="talent-basic-info__extra--prefix">期望：</div>
                            <div class="talent-basic-info__extra--content">
                              <span class="desired-city">青岛</span>
                              <span class="desired-job-type">算法工程师</span>
                              <span class="desired-salary">2.5万-3.5万</span>
                            </div>
                          </div>
                          <div class="talent-basic-info__tags talent-basic-info__tags-search">
                            <div class="km-tag"><div title="Python"><span>Python</span></div></div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        """
    )

    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(
            executable_path=executable_path,
            headless=True,
        )
    except Exception as exc:
        await playwright.stop()
        pytest.skip(f"Chromium launch is unavailable in this environment: {exc}")
    try:
        page = await browser.new_page()
        await page.set_content(html)
        raw_cards = await page.evaluate(
            _EXTRACT_CANDIDATES_SCRIPT,
            {"maxCards": 5},
        )
    finally:
        await browser.close()
        await playwright.stop()

    candidates = [
        parse_candidate_card(
            raw_card,
            site="zhaopin",
            page=1,
            rank=index,
        )
        for index, raw_card in enumerate(raw_cards, start=1)
        if isinstance(raw_card, dict)
    ]
    normalized = [candidate for candidate in candidates if candidate is not None]

    assert len(normalized) == 1
    assert normalized[0].display_name == "李先生"
    assert normalized[0].city == "青岛"
    assert normalized[0].years_experience == "10年"
    assert normalized[0].education == "硕士"
    assert normalized[0].detail_url == "https://rd6.zhaopin.com/resume/detail/1"
