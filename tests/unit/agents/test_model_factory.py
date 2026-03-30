# -*- coding: utf-8 -*-
"""Tests for model formatter adaptations."""

from __future__ import annotations

import json
from typing import Any, Union

import pytest
from agentscope.formatter import OpenAIChatFormatter

from copaw.agents.model_factory import _create_file_block_support_formatter
from copaw.agents.skill_hooks import clear_all_hooks, register_summary_hook

# ------------------------------------------------------------------
# Summary hook adapter (same logic previously hardcoded in model_factory)
# ------------------------------------------------------------------

_SITE_NAMES = {"liepin", "boss", "zhaopin"}


def _recruiting_summary_hook(output: Union[str, list[dict[str, Any]]]) -> str:
    """Extract pre-rendered summary_markdown from recruiting tool output."""
    raw: str | None = None
    if isinstance(output, str):
        raw = output
    elif isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and item.get("type") == "text":
                raw = item.get("text")
                if raw:
                    break
    if not raw or not isinstance(raw, str):
        return ""
    text = raw.strip()
    if not text.startswith("{"):
        return ""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    if payload.get("site") not in _SITE_NAMES:
        return ""
    summary = payload.get("summary_markdown", "")
    if not isinstance(summary, str) or not summary:
        return ""
    return f"招聘搜索结果摘要：\n{summary}"


@pytest.fixture(autouse=True)
def _register_summary_hooks():
    """Register the recruiting summary hook before each test, clear after."""
    register_summary_hook(_recruiting_summary_hook)
    yield
    clear_all_hooks()


def test_formatter_prefers_recruiting_summary_markdown_for_tool_results() -> None:
    """Recruiting tool results should give the model a stable summary template."""
    formatter_class = _create_file_block_support_formatter(
        OpenAIChatFormatter,
    )

    text, multimodal_data = formatter_class.convert_tool_result_to_string(
        [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "site": "liepin",
                        "status": "ok",
                        "summary_markdown": (
                            "### 猎聘\n"
                            "1. 张** | 算法工程师 / 上海 / 8年 / 本科 | 猎聘\n"
                            "   [打开猎聘详情](https://example.com/candidate/1)"
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )

    assert text.startswith("招聘搜索结果摘要：\n")
    assert "### 猎聘" in text
    assert "[打开猎聘详情](https://example.com/candidate/1)" in text
    assert multimodal_data == []


def test_formatter_keeps_non_recruiting_tool_text_unchanged() -> None:
    """Only recruiting payloads should receive the summary specialization."""
    formatter_class = _create_file_block_support_formatter(
        OpenAIChatFormatter,
    )

    text, multimodal_data = formatter_class.convert_tool_result_to_string(
        [{"type": "text", "text": '{"hello":"world"}'}],
    )

    assert text == '{"hello":"world"}'
    assert multimodal_data == []
