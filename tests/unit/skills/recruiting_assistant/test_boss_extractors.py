# -*- coding: utf-8 -*-
"""Tests for BOSS candidate extraction helpers."""

from copaw.agents.skills.recruiting_assistant.boss_mcp.extractors import (
    extract_candidates_from_page,
    extract_total_from_page,
    parse_candidate_card,
)


def test_parse_candidate_card_extracts_core_and_extra_fields() -> None:
    """Parse a raw BOSS list card into the shared summary schema."""
    candidate = parse_candidate_card(
        {
            "name": "张先生",
            "headline": "Python开发 / 上海 / 6年 / 本科",
            "city": "上海",
            "experience": "6年",
            "education": "本科",
            "detail_url": "https://example.com/boss/1",
            "extra_attributes": {
                "活跃度": "今日活跃",
                "年龄": "32",
            },
        },
        site="boss",
        page=1,
        rank=1,
    )

    assert candidate is not None
    assert candidate.display_name == "张先生"
    assert candidate.headline == "Python开发 / 上海 / 6年 / 本科"
    assert candidate.city == "上海"
    assert candidate.years_experience == "6年"
    assert candidate.education == "本科"
    assert candidate.extra_attributes == {
        "活跃度": "今日活跃",
        "年龄": "32",
    }
    assert candidate.detail_url == "https://example.com/boss/1"


async def test_extract_candidates_from_page_uses_page_evaluate_results() -> None:
    """Convert evaluated BOSS list cards into shared candidate summaries."""

    class FakePage:
        async def evaluate(self, script, payload):
            _ = script
            assert payload == {"maxCards": 2}
            return [
                {
                    "candidate_id": "boss-1",
                    "name": "张先生",
                    "headline": "Python算法工程师 / 上海 / 8年 / 本科",
                    "city": "上海",
                    "experience": "8年",
                    "education": "本科",
                    "detail_url": "https://example.com/boss/1",
                    "extra_attributes": {"活跃度": "今日活跃"},
                },
                {
                    "candidate_id": "boss-2",
                    "name": "李女士",
                    "headline": "算法工程师 / 杭州 / 6年 / 硕士",
                    "city": "杭州",
                    "experience": "6年",
                    "education": "硕士",
                    "detail_url": "https://example.com/boss/2",
                    "extra_attributes": {"活跃度": "本周活跃"},
                },
            ]

    candidates = await extract_candidates_from_page(FakePage(), 3, 2)

    assert [candidate.candidate_id for candidate in candidates] == [
        "boss-1",
        "boss-2",
    ]
    assert candidates[0].page == 3
    assert candidates[0].rank == 1
    assert candidates[1].extra_attributes == {"活跃度": "本周活跃"}


async def test_extract_total_from_page_reads_numeric_total() -> None:
    """Read the frontend-visible total count from the page evaluation result."""

    class FakePage:
        async def evaluate(self, script):
            _ = script
            return 894

    total = await extract_total_from_page(FakePage())

    assert total == 894
