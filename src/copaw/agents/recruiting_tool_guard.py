# -*- coding: utf-8 -*-
"""Runtime guards for recruiting-site tool flows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from agentscope.message import Msg


@dataclass(frozen=True)
class RecruitingFlowContext:
    """Structured Liepin flow state detected from the current recruiting turn."""

    site: str
    status: str
    stop_current_turn: bool
    source_tool: str
    message: str
    continue_tool: str = ""
    summary_markdown: str = ""


def find_recruiting_stop_context(
    memory_content: Sequence[tuple[Msg, list[str]]],
) -> RecruitingFlowContext | None:
    """Return the latest recruiting stop signal in the current user turn."""
    context = find_latest_recruiting_tool_context(memory_content)
    if context is not None and context.stop_current_turn:
        return context
    return None


def find_latest_recruiting_tool_context(
    memory_content: Sequence[tuple[Msg, list[str]]],
) -> RecruitingFlowContext | None:
    """Return the latest Liepin tool result in the current user turn."""
    for msg, _marks in reversed(memory_content):
        if getattr(msg, "role", None) == "user":
            break
        if getattr(msg, "role", None) != "system":
            continue
        context = _extract_flow_context_from_msg(msg)
        if context is not None:
            return context
    return None


def build_recruiting_stop_reply(context: RecruitingFlowContext) -> str:
    """Render a deterministic user-facing reply for stop-current-turn states."""
    if context.status == "empty_result":
        return (
            "本次在猎聘未找到符合当前条件的候选人。\n\n"
            "请确认是否放宽条件后我再继续，例如调整关键词、工作年限、学历或城市。"
        )

    if context.status == "not_logged_in":
        return (
            "当前需要你在同一个猎聘窗口完成登录。\n\n"
            "登录完成后给我发新消息，我会继续当前搜索。请不要关闭这个猎聘窗口。"
        )

    if context.status == "captcha_required":
        return (
            "当前需要你在同一个猎聘窗口完成人机验证。\n\n"
            "验证完成后给我发新消息，我会继续当前搜索。请不要关闭这个猎聘窗口。"
        )

    if context.status == "site_layout_changed":
        return (
            "猎聘招聘方页面结构与当前适配器不兼容，本轮自动搜索已停止。\n\n"
            "请保持当前已登录的猎聘窗口不要关闭，我会基于这个兼容性问题继续修复。"
        )

    if context.status == "extraction_unreliable":
        return (
            "猎聘候选人列表已打开，但当前页面抽取结果不可靠，本轮先停止。\n\n"
            "请保持当前已登录的猎聘窗口，我会继续修复抽取兼容性。"
        )

    message = context.message.strip()
    if message:
        return message

    return "当前猎聘流程已停止，请发送下一条消息后再继续。"


def should_block_recruiting_tool_call(
    memory_content: Sequence[tuple[Msg, list[str]]],
    tool_name: str,
) -> RecruitingFlowContext | None:
    """Block browser/Liepin retries after a stop signal in the same turn."""
    flow_context = find_latest_recruiting_tool_context(memory_content)
    if flow_context is None:
        return None

    if tool_name == "browser_use":
        return flow_context
    if tool_name.startswith("liepin_") and flow_context.stop_current_turn:
        return flow_context
    return None


def _extract_flow_context_from_msg(msg: Msg) -> RecruitingFlowContext | None:
    """Parse a tool-result message and extract the latest Liepin flow state."""
    content = getattr(msg, "content", None)
    if not isinstance(content, list):
        return None

    for block in reversed(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue
        source_tool = str(block.get("name") or "")
        payload = _extract_payload_from_tool_result(block)
        if payload is None:
            continue
        if payload.get("site") != "liepin":
            continue
        return RecruitingFlowContext(
            site=str(payload.get("site") or ""),
            status=str(payload.get("status") or ""),
            stop_current_turn=payload.get("stop_current_turn") is True,
            source_tool=source_tool,
            message=str(payload.get("message") or ""),
            continue_tool=str(payload.get("continue_tool") or ""),
            summary_markdown=str(payload.get("summary_markdown") or ""),
        )
    return None


def _extract_payload_from_tool_result(
    block: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract the first JSON payload from a tool-result output block."""
    output = block.get("output")
    if not isinstance(output, list):
        return None

    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = str(item.get("text") or "").strip()
        if not text.startswith("{"):
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None
