# -*- coding: utf-8 -*-
"""Tests for recruiting assistant markdown rendering."""

from cohub_recruiting.models import (
    CandidateSummary,
    SiteSearchResult,
)
from cohub_recruiting.renderer import (
    render_search_results,
)


def test_render_search_results_groups_sites_and_respects_display_limit() -> None:
    """Render site-grouped markdown tables with links, highlights, and failures."""
    markdown = render_search_results(
        [
            SiteSearchResult(
                site="liepin",
                status="ok",
                page=1,
                total=139,
                candidates=[
                    CandidateSummary(
                        site="liepin",
                        candidate_id="lp-1",
                        display_name="张先生",
                        headline="Agent开发 / 上海 / 6年 / 本科",
                        city="上海",
                        expected_city="上海",
                        years_experience="6年",
                        education="本科",
                        current_company="海尔",
                        current_title="Agent开发工程师",
                        expected_title="Agent开发",
                        expected_salary="30-40K",
                        highlights=["现居上海", "6年研发经验"],
                        detail_url="https://example.com/candidate/1",
                        page=1,
                        rank=1,
                    ),
                    CandidateSummary(
                        site="liepin",
                        candidate_id="lp-2",
                        display_name="李女士",
                        headline="AI平台开发 / 北京 / 5年 / 硕士",
                        city="北京",
                        years_experience="5年",
                        education="硕士",
                        current_company="某公司",
                        current_title="AI平台开发",
                        expected_title="AI平台开发",
                        expected_salary="25-35K",
                        detail_url="https://example.com/candidate/2",
                        page=1,
                        rank=2,
                    ),
                ],
            ),
            SiteSearchResult(
                site="zhaopin",
                status="not_logged_in",
                page=1,
                total=0,
                ignored_filters=["management_experience"],
                candidates=[],
            ),
        ],
        display_limit=1,
    )

    assert "### 猎聘" in markdown
    assert "| 序号 | 姓名 | 摘要 | 城市 | 期望城市 | 经验 | 学历 | 当前公司 | 当前职位 | 期望职位 | 期望薪资 | 命中点 | 详情 |" in markdown
    assert "| 1 | 张先生 | Agent开发 / 上海 / 6年 / 本科 | 上海 | 上海 | 6年 | 本科 | 海尔 | Agent开发工程师 | Agent开发 | 30-40K | 现居上海；6年研发经验 | [打开猎聘详情](https://example.com/candidate/1) |" in markdown
    assert "[打开猎聘详情](https://example.com/candidate/1)" in markdown
    assert "李女士" not in markdown
    assert "已按显示上限展示 1 位候选人。" in markdown
    assert "### 智联招聘" in markdown
    assert "状态：not_logged_in" in markdown
    assert "忽略筛选：management_experience" in markdown


def test_render_search_results_uses_placeholders_for_missing_candidate_fields() -> None:
    """Render a complete markdown table row even when candidate fields are missing."""
    markdown = render_search_results(
        [
            SiteSearchResult(
                site="liepin",
                status="ok",
                candidates=[
                    CandidateSummary(
                        site="liepin",
                        candidate_id="lp-3",
                        display_name="王先生",
                        headline="算法工程师 / 上海",
                        detail_url="https://example.com/candidate/3",
                    ),
                ],
            ),
        ],
    )

    assert "| 1 | 王先生 | 算法工程师 / 上海 | - | - | - | - | - | - | - | - | - | [打开猎聘详情](https://example.com/candidate/3) |" in markdown


def test_render_search_results_appends_site_specific_extra_columns() -> None:
    """Render site-specific fields as additional markdown table columns."""
    markdown = render_search_results(
        [
            SiteSearchResult(
                site="boss",
                status="ok",
                candidates=[
                    CandidateSummary(
                        site="boss",
                        candidate_id="boss-1",
                        display_name="赵先生",
                        headline="Python开发 / 上海",
                        detail_url="https://example.com/boss/1",
                        extra_attributes={
                            "年龄": "32",
                            "活跃度": "今日活跃",
                        },
                    ),
                    CandidateSummary(
                        site="boss",
                        candidate_id="boss-2",
                        display_name="钱女士",
                        headline="算法工程师 / 杭州",
                        detail_url="https://example.com/boss/2",
                        extra_attributes={
                            "活跃度": "本周活跃",
                        },
                    ),
                ],
            ),
        ],
    )

    assert "| 年龄 | 活跃度 |" in markdown
    assert "| 1 | 赵先生 | Python开发 / 上海 | - | - | - | - | - | - | - | - | - | [打开BOSS直聘详情](https://example.com/boss/1) | 32 | 今日活跃 |" in markdown
    assert "| 2 | 钱女士 | 算法工程师 / 杭州 | - | - | - | - | - | - | - | - | - | [打开BOSS直聘详情](https://example.com/boss/2) | - | 本周活跃 |" in markdown
