# -*- coding: utf-8 -*-
"""Tests for recruiting assistant match-reason generation."""

from types import SimpleNamespace

import pytest

from copaw.agents.skills.recruiting_assistant.config import MatchModelConfig
from copaw.agents.skills.recruiting_assistant.match_reasoner import (
    MatchReasoner,
)
from copaw.agents.skills.recruiting_assistant.models import (
    CandidateSummary,
    NormalizedSearchQuery,
)


def _candidate() -> CandidateSummary:
    return CandidateSummary(
        site="liepin",
        candidate_id="lp-1",
        display_name="张先生",
        headline="Agent开发 / 上海 / 6年 / 本科",
        city="上海",
        years_experience="6年",
        education="本科",
        detail_url="https://example.com/candidate/1",
        page=1,
        rank=1,
    )


@pytest.mark.asyncio
async def test_match_reasoner_returns_empty_result_when_disabled() -> None:
    """Disabled small-model config should skip generation entirely."""
    reasoner = MatchReasoner(MatchModelConfig())

    result = await reasoner.generate(
        query=NormalizedSearchQuery(keyword="agent开发"),
        candidate=_candidate(),
    )

    assert result.reasons == []
    assert result.note == ""


@pytest.mark.asyncio
async def test_match_reasoner_parses_json_response() -> None:
    """The reasoner should parse schema-constrained JSON output."""

    class FakeClient:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=self._create,
                ),
            )

        async def _create(self, **_: object) -> object:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                "```json\n"
                                '{"reasons":["现居上海","6年研发经验",'
                                '"岗位关键词命中","最近经历偏AI平台","额外信息"],'
                                '"note":"适合先看详情"}\n'
                                "```"
                            ),
                        ),
                    ),
                ],
            )

    reasoner = MatchReasoner(
        MatchModelConfig(
            provider="openai",
            model="gpt-4.1-mini",
            api_key="sk-test",
            base_url="https://example.com/v1",
            timeout_ms=12000,
        ),
        client_factory=FakeClient,
    )

    result = await reasoner.generate(
        query=NormalizedSearchQuery(keyword="agent开发", expected_city="上海"),
        candidate=_candidate(),
    )

    assert result.reasons == [
        "现居上海",
        "6年研发经验",
        "岗位关键词命中",
        "最近经历偏AI平台",
    ]
    assert result.note == "适合先看详情"


@pytest.mark.asyncio
async def test_match_reasoner_handles_model_errors_gracefully() -> None:
    """Model errors should degrade to an empty reasoning payload."""

    class FakeClient:
        def __init__(self, **_: object) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=self._create,
                ),
            )

        async def _create(self, **_: object) -> object:
            raise RuntimeError("boom")

    reasoner = MatchReasoner(
        MatchModelConfig(
            provider="openai",
            model="gpt-4.1-mini",
            api_key="sk-test",
        ),
        client_factory=FakeClient,
    )

    result = await reasoner.generate(
        query=NormalizedSearchQuery(keyword="agent开发"),
        candidate=_candidate(),
    )

    assert result.reasons == []
    assert result.note == ""
