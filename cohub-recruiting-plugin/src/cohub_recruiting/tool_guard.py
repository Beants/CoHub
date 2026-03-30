# -*- coding: utf-8 -*-
"""Recruiting-specific tool guard hooks.

This module provides hook functions that integrate with CoHub's
generic skill hook system to control recruiting tool execution flow.

Supports three recruiting sites: Liepin (猎聘), BOSS (BOSS直聘),
and Zhaopin (智联招聘).
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from agentscope.message import Msg
from copaw.agents.skill_hooks import SkillFlowContext

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUPPORTED_SITES = {"liepin", "boss", "zhaopin"}
_SITE_TOOL_PREFIXES = {"liepin_", "boss_", "zhaopin_"}
_SITE_LABELS = {"liepin": "猎聘", "boss": "BOSS直聘", "zhaopin": "智联招聘"}


def _site_label(site: str) -> str:
    return _SITE_LABELS.get(site, site)


# ---------------------------------------------------------------------------
# Public hook functions
# ---------------------------------------------------------------------------


def tool_block_hook(memory_content, tool_name) -> SkillFlowContext | None:
    """Check if a tool call should be blocked by recruiting flow state."""
    ctx = _find_latest_recruiting_tool_context(memory_content)
    if ctx is None:
        return None
    # Block browser_use after any recruiting tool
    if tool_name == "browser_use":
        return ctx
    # Block same-site tools after stop signal
    if ctx.stop_current_turn:
        for prefix in _SITE_TOOL_PREFIXES:
            if tool_name.startswith(prefix):
                return ctx
    return None


def stop_context_hook(memory_content) -> SkillFlowContext | None:
    """Detect a recruiting stop signal in memory."""
    ctx = _find_latest_recruiting_tool_context(memory_content)
    if ctx is not None and ctx.stop_current_turn:
        return ctx
    return None


def latest_context_hook(memory_content) -> SkillFlowContext | None:
    """Find the latest recruiting tool context in memory."""
    return _find_latest_recruiting_tool_context(memory_content)


def stop_reply_hook(context: SkillFlowContext) -> str:
    """Build a user-facing stop reply for recruiting flows."""
    label = _site_label(context.site)

    if context.status == "empty_result":
        return (
            f"本次在{label}未找到符合当前条件的候选人。\n\n"
            "请确认是否放宽条件后我再继续，例如调整关键词、工作年限、学历或城市。"
        )

    if context.status == "not_logged_in":
        return (
            f"当前需要你在同一个{label}窗口完成登录。\n\n"
            f"登录完成后给我发新消息，我会继续当前搜索。请不要关闭这个{label}窗口。"
        )

    if context.status == "captcha_required":
        return (
            f"当前需要你在同一个{label}窗口完成人机验证。\n\n"
            f"验证完成后给我发新消息，我会继续当前搜索。请不要关闭这个{label}窗口。"
        )

    if context.status == "site_layout_changed":
        return (
            f"{label}招聘方页面结构与当前适配器不兼容，本轮自动搜索已停止。\n\n"
            f"请保持当前已登录的{label}窗口不要关闭，我会基于这个兼容性问题继续修复。"
        )

    if context.status == "extraction_unreliable":
        return (
            f"{label}候选人列表已打开，但当前页面抽取结果不可靠，本轮先停止。\n\n"
            f"请保持当前已登录的{label}窗口，我会继续修复抽取兼容性。"
        )

    message = context.message.strip()
    if message:
        return message

    return f"当前{label}流程已停止，请发送下一条消息后再继续。"


def blocked_text_hook(context: SkillFlowContext, tool_name: str) -> str:
    """Build the blocked-tool response text for recruiting flows."""
    text = (
        f"⛔ **Recruiting Flow Stopped / 招聘流程已停止**\n\n"
        f"- Tool: `{tool_name}`\n"
        f"- Site: `{context.site}`\n"
        f"- Status: `{context.status}`\n"
        f"- Source tool: `{context.source_tool}`\n"
        f"- stop_current_turn={str(context.stop_current_turn).lower()}\n\n"
        f"{context.message}\n\n"
    )
    if context.stop_current_turn:
        text += (
            "This turn already received a stop signal. Do not call "
            "`browser_use` or any recruiting tool again until the "
            "user sends a new message.\n"
        )
    else:
        text += (
            "This recruiting flow is already active in the current "
            "turn. Do not switch to `browser_use`; stay inside the "
            "MCP tools for this turn.\n"
        )
    return text


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_latest_recruiting_tool_context(
    memory_content: Sequence[tuple[Msg, list[str]]],
) -> SkillFlowContext | None:
    """Return the latest recruiting tool result in the current user turn."""
    for msg, _marks in reversed(memory_content):
        if getattr(msg, "role", None) == "user":
            break
        if getattr(msg, "role", None) != "system":
            continue
        context = _extract_flow_context_from_msg(msg)
        if context is not None:
            return context
    return None


def _extract_flow_context_from_msg(msg: Msg) -> SkillFlowContext | None:
    """Parse a tool-result message and extract the latest recruiting flow state."""
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
        site = payload.get("site", "")
        if site not in _SUPPORTED_SITES:
            continue
        return SkillFlowContext(
            skill="recruiting",
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
