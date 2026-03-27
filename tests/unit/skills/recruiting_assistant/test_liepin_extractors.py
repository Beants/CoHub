# -*- coding: utf-8 -*-
"""Tests for Liepin candidate extraction helpers."""

import pytest

from copaw.agents.skills.recruiting_assistant.liepin_mcp.extractors import (
    extract_candidates_from_page,
    extract_total_from_page,
    parse_candidate_card,
)


def test_parse_candidate_card_extracts_core_fields() -> None:
    """Parse a raw candidate card into the shared summary schema."""
    candidate = parse_candidate_card(
        """
        张先生
        Agent开发
        上海 6年 本科
        最近经历：AI平台
        """,
        detail_url="https://example.com/candidate/1",
        site="liepin",
        page=1,
        rank=1,
    )

    assert candidate is not None
    assert candidate.display_name == "张先生"
    assert candidate.headline == "Agent开发 / 上海 / 6年 / 本科"
    assert candidate.city == "上海"
    assert candidate.years_experience == "6年"
    assert candidate.education == "本科"
    assert candidate.detail_url == "https://example.com/candidate/1"


def test_parse_candidate_card_skips_empty_blocks() -> None:
    """Do not create candidate summaries from empty noise blocks."""
    assert (
        parse_candidate_card(
            " \n \n ",
            detail_url="https://example.com/candidate/1",
            site="liepin",
            page=1,
            rank=1,
        )
        is None
    )


@pytest.mark.asyncio
async def test_extract_candidates_from_page_prefers_resume_cards_html() -> None:
    """Recruiter search HTML should yield real candidate cards and detail links."""

    html = """
    <html>
      <body>
        <ul>
          <li
            data-resumeidencode="abc123"
            data-resumeurl="https://lpt.liepin.com/cvview/showresumedetail?resIdEncode=abc123&amp;index=0&amp;position=1"
            class="resumeCardWrap--FcnzW"
          >
            <div class="resumeCardContent--A03AZ">
              <div class="nest-resume-status">
                <span class="nest-resume-offline nest-resume-offline-active"><em>今天活跃</em></span>
              </div>
              <div class="nest-resume-personal">
                <div class="nest-resume-personal-name"><em>施**</em></div>
                <div class="nest-resume-personal-detail">
                  <span class="personal-detail-age">37岁</span>
                  <span class="personal-detail-workyears">14年</span>
                  <span class="personal-detail-edulevel">本科</span>
                  <span class="personal-detail-dq">上海</span>
                </div>
                <div class="nest-resume-personal-expect">
                  <em>期望：</em>
                  <span class="personal-expect-content">
                    <span>上海</span>
                    <span>Python算法工程师</span>
                    <span>45-50K·14薪</span>
                  </span>
                </div>
                <div class="nest-resume-personal-skills">
                  <span>python</span>
                  <span>机器学习</span>
                </div>
              </div>
              <div class="nest-resume-work-item">
                <div class="work-item-content">
                  <span class="work-item-compname">联想(上海)计算机科技有限公司</span>
                  <em class="work-item-content-divide"></em>
                  <span class="work-item-extra">
                    <span title="python高级开发工程师">python高级开发工程师</span>
                    <em class="work-item-content-divide"></em>
                    <span class="work-item-content-duration">2016.07-至今(9年8个月)</span>
                  </span>
                </div>
              </div>
            </div>
          </li>
          <li
            data-resumeidencode="def456"
            data-resumeurl="https://lpt.liepin.com/cvview/showresumedetail?resIdEncode=def456&amp;index=1&amp;position=2"
            class="resumeCardWrap--FcnzW"
          >
            <div class="resumeCardContent--A03AZ">
              <div class="nest-resume-status">
                <span class="nest-resume-offline"><em>3天内活跃</em></span>
              </div>
              <div class="nest-resume-personal">
                <div class="nest-resume-personal-name"><em>李**</em></div>
                <div class="nest-resume-personal-detail">
                  <span class="personal-detail-age">31岁</span>
                  <span class="personal-detail-workyears">8年</span>
                  <span class="personal-detail-edulevel">本科</span>
                  <span class="personal-detail-dq">上海-浦东新区</span>
                </div>
                <div class="nest-resume-personal-expect">
                  <em>期望：</em>
                  <span class="personal-expect-content">
                    <span>上海</span>
                    <span>高级算法工程师</span>
                    <span>35-45K</span>
                  </span>
                </div>
              </div>
              <div class="nest-resume-work-item">
                <div class="work-item-content">
                  <span class="work-item-compname">某智能科技公司</span>
                  <em class="work-item-content-divide"></em>
                  <span class="work-item-extra">
                    <span title="算法工程师">算法工程师</span>
                    <em class="work-item-content-divide"></em>
                    <span class="work-item-content-duration">2020.03-至今(5年)</span>
                  </span>
                </div>
              </div>
            </div>
          </li>
        </ul>
      </body>
    </html>
    """

    class FakePage:
        url = "https://lpt.liepin.com/search"

        async def evaluate(self, script, args):
            return []

        async def content(self):
            return html

    candidates = await extract_candidates_from_page(
        FakePage(),
        page_number=1,
        max_cards=10,
    )

    assert len(candidates) == 2

    first = candidates[0]
    assert first.display_name == "施**"
    assert first.candidate_id == "abc123"
    assert first.city == "上海"
    assert first.expected_city == "上海"
    assert first.years_experience == "14年"
    assert first.education == "本科"
    assert first.expected_title == "Python算法工程师"
    assert first.expected_salary == "45-50K·14薪"
    assert first.current_company == "联想(上海)计算机科技有限公司"
    assert first.current_title == "python高级开发工程师"
    assert first.detail_url.startswith(
        "https://lpt.liepin.com/cvview/showresumedetail?resIdEncode=abc123",
    )
    assert "今天活跃" in first.highlights


@pytest.mark.asyncio
async def test_extract_total_from_page_supports_resume_count_copy() -> None:
    """Recruiter pages often expose total counts as '共有 N 份简历'."""

    class FakeLocator:
        async def inner_text(self, timeout=3000):
            _ = timeout
            return "筛选条件 共有 894 份简历 智能排序"

    class FakePage:
        def locator(self, _selector):
            return FakeLocator()

    total = await extract_total_from_page(FakePage())

    assert total == 894
