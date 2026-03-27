# -*- coding: utf-8 -*-
"""Tests for model formatter adaptations."""

from __future__ import annotations

import json

from agentscope.formatter import OpenAIChatFormatter

from copaw.agents.model_factory import _create_file_block_support_formatter


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
