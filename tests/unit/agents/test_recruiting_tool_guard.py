# -*- coding: utf-8 -*-
"""Tests for recruiting-specific runtime tool guards."""

from __future__ import annotations

import json

import pytest
from agentscope.message import Msg

from copaw.agents.recruiting_tool_guard import (
    find_recruiting_stop_context,
    should_block_recruiting_tool_call,
)
from copaw.agents.tool_guard_mixin import ToolGuardMixin


def _user_msg(text: str = "search liepin") -> Msg:
    return Msg("user", text, "user")


def _assistant_msg(text: str = "working") -> Msg:
    return Msg("Friday", text, "assistant")


def _liepin_stop_msg(
    *,
    tool_name: str = "liepin_search_candidates",
    status: str = "site_layout_changed",
    message: str = (
        "猎聘招聘方页面结构发生变化。请保持当前已登录的猎聘窗口，不要打开"
        "新的浏览器窗口，不要切换到 browser_use，也不要继续调用其他猎聘工具。"
        "当前轮次到此为止。"
    ),
) -> Msg:
    payload = {
        "site": "liepin",
        "status": status,
        "page": 1,
        "total": 0,
        "message": message,
        "continue_tool": "",
        "reuse_same_browser_window": True,
        "avoid_reopen_browser": True,
        "stop_current_turn": True,
        "ignored_filters": [],
        "candidates": [],
    }
    return Msg(
        "system",
        [
            {
                "type": "tool_result",
                "id": "call_liepin",
                "name": tool_name,
                "output": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    },
                ],
            },
        ],
        "system",
    )


def _liepin_ok_msg(
    *,
    tool_name: str = "liepin_search_candidates",
    status: str = "ok",
    message: str = "",
    summary_markdown: str = (
        "### 猎聘\n"
        "1. 张先生 | Python算法工程师 / 上海 / 6年 / 本科 | 猎聘\n"
        "   [打开猎聘详情](https://example.com/candidate/1)"
    ),
) -> Msg:
    payload = {
        "site": "liepin",
        "status": status,
        "page": 1,
        "total": 1,
        "message": message,
        "continue_tool": "",
        "reuse_same_browser_window": False,
        "avoid_reopen_browser": False,
        "stop_current_turn": False,
        "ignored_filters": [],
        "summary_markdown": summary_markdown,
        "candidates": [
            {
                "site": "liepin",
                "candidate_id": "lp-1",
                "display_name": "张先生",
                "headline": "Python算法工程师 / 上海 / 6年 / 本科",
                "detail_url": "https://example.com/candidate/1",
            },
        ],
    }
    return Msg(
        "system",
        [
            {
                "type": "tool_result",
                "id": "call_liepin_ok",
                "name": tool_name,
                "output": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, ensure_ascii=False),
                    },
                ],
            },
        ],
        "system",
    )


class _MemoryStub:
    def __init__(self, entries: list[tuple[Msg, list[str]]]) -> None:
        self.content = list(entries)

    async def add(self, msg: Msg, marks=None) -> None:
        if marks is None:
            normalized_marks: list[str] = []
        elif isinstance(marks, str):
            normalized_marks = [marks]
        else:
            normalized_marks = list(marks)
        self.content.append((msg, normalized_marks))


class _GuardEngineStub:
    enabled = False

    def is_denied(self, tool_name: str) -> bool:
        return False

    def is_guarded(self, tool_name: str) -> bool:
        return False


class _ActingBase:
    async def _acting(self, tool_call) -> dict | None:
        self.super_calls.append(tool_call)
        return {"delegated": True}


class _ReasoningBase:
    async def _reasoning(self, tool_choice=None) -> Msg:
        self.reasoning_super_calls.append(tool_choice)
        return Msg("Friday", "super reasoning called", "assistant")


class _DummyAgent(ToolGuardMixin, _ActingBase):
    def __init__(self, entries: list[tuple[Msg, list[str]]]) -> None:
        self.memory = _MemoryStub(entries)
        self._tool_guard_engine = _GuardEngineStub()
        self._tool_guard_approval_service = object()
        self._request_context = {}
        self.printed: list[Msg] = []
        self.super_calls: list[dict] = []

    async def print(self, msg: Msg, _is_last: bool) -> None:
        self.printed.append(msg)


class _DummyReasoningAgent(ToolGuardMixin, _ReasoningBase):
    def __init__(self, entries: list[tuple[Msg, list[str]]]) -> None:
        self.memory = _MemoryStub(entries)
        self._tool_guard_engine = _GuardEngineStub()
        self._tool_guard_approval_service = object()
        self._request_context = {}
        self.printed: list[Msg] = []
        self.reasoning_super_calls: list[object | None] = []
        self.name = "Friday"

    async def print(self, msg: Msg, _is_last: bool) -> None:
        self.printed.append(msg)


def test_should_find_liepin_stop_signal_in_current_turn() -> None:
    """The current turn should retain the latest Liepin stop instruction."""
    memory_entries = [
        (_user_msg(), []),
        (_assistant_msg(), []),
        (_liepin_stop_msg(), []),
    ]

    stop_context = find_recruiting_stop_context(memory_entries)

    assert stop_context is not None
    assert stop_context.site == "liepin"
    assert stop_context.status == "site_layout_changed"
    assert stop_context.stop_current_turn is True
    assert stop_context.source_tool == "liepin_search_candidates"


def test_should_not_reuse_previous_turn_stop_signal() -> None:
    """A new user turn should clear the previous Liepin stop state."""
    memory_entries = [
        (_user_msg("turn 1"), []),
        (_liepin_stop_msg(), []),
        (_assistant_msg("asked user to verify"), []),
        (_user_msg("turn 2"), []),
        (_assistant_msg("resume"), []),
    ]

    assert find_recruiting_stop_context(memory_entries) is None
    assert should_block_recruiting_tool_call(memory_entries, "browser_use") is None


def test_should_block_browser_use_after_liepin_stop_signal() -> None:
    """Generic browser fallback must be blocked after Liepin says stop."""
    memory_entries = [
        (_user_msg(), []),
        (_liepin_stop_msg(), []),
        (_assistant_msg("trying again"), []),
    ]

    stop_context = should_block_recruiting_tool_call(
        memory_entries,
        "browser_use",
    )

    assert stop_context is not None
    assert stop_context.status == "site_layout_changed"


def test_should_block_browser_use_after_any_liepin_tool_in_same_turn() -> None:
    """Browser fallback should stay blocked even after an apparently ok Liepin call."""
    memory_entries = [
        (_user_msg(), []),
        (_liepin_ok_msg(), []),
        (_assistant_msg("let me inspect in browser"), []),
    ]

    stop_context = should_block_recruiting_tool_call(
        memory_entries,
        "browser_use",
    )

    assert stop_context is not None
    assert stop_context.status == "ok"


def test_should_block_follow_up_liepin_tools_in_same_turn() -> None:
    """Further Liepin tool calls must also be blocked in the same turn."""
    memory_entries = [
        (_user_msg(), []),
        (_liepin_stop_msg(status="captcha_required"), []),
        (_assistant_msg("checking status again"), []),
    ]

    stop_context = should_block_recruiting_tool_call(
        memory_entries,
        "liepin_status",
    )

    assert stop_context is not None
    assert stop_context.status == "captcha_required"


def test_should_block_follow_up_liepin_retry_after_empty_result_stop() -> None:
    """Empty-result stops should prevent same-turn query relaxation retries."""
    memory_entries = [
        (_user_msg(), []),
        (
            _liepin_stop_msg(
                status="empty_result",
                message=(
                    "当前条件下未找到候选人。请直接告诉用户暂无结果，并等待用户"
                    "确认是否放宽条件。不要自动放宽条件，不要继续调用其他"
                    "liepin_* 工具。当前轮次到此为止。"
                ),
            ),
            [],
        ),
        (_assistant_msg("let me try a broader query"), []),
    ]

    stop_context = should_block_recruiting_tool_call(
        memory_entries,
        "liepin_search_candidates",
    )

    assert stop_context is not None
    assert stop_context.status == "empty_result"
    assert stop_context.stop_current_turn is True


@pytest.mark.asyncio
async def test_tool_guard_mixin_blocks_browser_use_after_liepin_stop() -> None:
    """Mixin should deny browser fallback and avoid delegating to super."""
    agent = _DummyAgent(
        [
            (_user_msg(), []),
            (_liepin_stop_msg(), []),
            (_assistant_msg("let me inspect with browser_use"), []),
        ],
    )

    result = await agent._acting(
        {
            "id": "call_browser",
            "name": "browser_use",
            "input": {"action": "open", "url": "https://www.liepin.com/"},
        },
    )

    assert result is None
    assert agent.super_calls == []
    tool_msg, _ = agent.memory.content[-1]
    tool_block = tool_msg.content[0]
    text = tool_block["output"][0]["text"]
    assert tool_block["name"] == "browser_use"
    assert "stop_current_turn=true" in text
    assert "browser_use" in text


@pytest.mark.asyncio
async def test_tool_guard_mixin_short_circuits_reasoning_after_empty_result_stop() -> None:
    """Reasoning should stop immediately after an empty-result Liepin stop."""
    agent = _DummyReasoningAgent(
        [
            (_user_msg(), []),
            (
                _liepin_stop_msg(
                    status="empty_result",
                    message=(
                        "当前条件下未找到候选人。请直接告诉用户暂无结果，并等待用户"
                        "确认是否放宽条件。不要自动放宽条件，不要继续调用其他"
                        "liepin_* 工具。当前轮次到此为止。"
                    ),
                ),
                [],
            ),
        ],
    )

    result = await agent._reasoning()

    assert agent.reasoning_super_calls == []
    assert result.role == "assistant"
    assert "未找到符合当前条件的候选人" in result.content
    assert "请确认是否放宽条件" in result.content
    assert agent.printed[-1].content == result.content
    stored_msg, _ = agent.memory.content[-1]
    assert stored_msg.content == result.content


@pytest.mark.asyncio
async def test_tool_guard_mixin_short_circuits_reasoning_with_recruiting_summary() -> None:
    """Successful recruiting results should reply with the pre-rendered summary."""
    agent = _DummyReasoningAgent(
        [
            (_user_msg(), []),
            (_liepin_ok_msg(), []),
        ],
    )

    result = await agent._reasoning()

    assert agent.reasoning_super_calls == []
    assert result.role == "assistant"
    assert result.content.startswith("### 猎聘")
    assert "[打开猎聘详情](https://example.com/candidate/1)" in result.content
    assert agent.printed[-1].content == result.content
    stored_msg, _ = agent.memory.content[-1]
    assert stored_msg.content == result.content
