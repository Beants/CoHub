# -*- coding: utf-8 -*-
"""Tool-guard mixin for CoPawAgent.

Provides ``_acting`` and ``_reasoning`` overrides that intercept
sensitive tool calls before execution, implementing the deny /
guard / approve flow.

Separated from ``react_agent.py`` to keep the main agent class
focused on lifecycle management.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any, Literal

from agentscope.message import Msg

from .recruiting_tool_guard import should_block_recruiting_tool_call
from .recruiting_tool_guard import (
    build_recruiting_stop_reply,
    find_latest_recruiting_tool_context,
    find_recruiting_stop_context,
)
from ..security.tool_guard.models import TOOL_GUARD_DENIED_MARK

logger = logging.getLogger(__name__)


class ToolGuardMixin:
    """Mixin that adds tool-guard interception to a ReActAgent.

    At runtime this class is always combined with
    ``agentscope.agent.ReActAgent`` via MRO, so ``super()._acting``
    and ``super()._reasoning`` resolve to the concrete agent methods.
    """

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _init_tool_guard(self) -> None:
        """Lazy-init tool-guard components (called once)."""
        from copaw.security.tool_guard.engine import get_guard_engine
        from copaw.app.approvals import get_approval_service

        self._tool_guard_engine = get_guard_engine()
        self._tool_guard_approval_service = get_approval_service()
        self._tool_guard_pending_info: dict | None = None

    def _ensure_tool_guard(self) -> None:
        if not hasattr(self, "_tool_guard_engine"):
            self._init_tool_guard()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _should_require_approval(self) -> bool:
        """``True`` when a ``session_id`` is available for approval."""
        return bool(self._request_context.get("session_id"))

    def _get_recruiting_runtime_block(self, tool_name: str):
        """Return a recruiting turn stop context when the call must be blocked."""
        memory_content = getattr(self.memory, "content", [])
        return should_block_recruiting_tool_call(memory_content, tool_name)

    def _get_recruiting_stop_context(self):
        """Return the current-turn recruiting stop context, if present."""
        memory_content = getattr(self.memory, "content", [])
        return find_recruiting_stop_context(memory_content)

    def _get_latest_recruiting_tool_context(self):
        """Return the latest recruiting tool context in the current user turn."""
        memory_content = getattr(self.memory, "content", [])
        return find_latest_recruiting_tool_context(memory_content)

    def _last_tool_response_is_denied(self) -> bool:
        """Check if the last message is a guard-denied tool result."""
        if not self.memory.content:
            return False
        msg, marks = self.memory.content[-1]
        return TOOL_GUARD_DENIED_MARK in marks and msg.role == "system"

    async def _cleanup_tool_guard_denied_messages(
        self,
        include_denial_response: bool = True,
    ) -> None:
        """Remove tool-guard denied messages from memory.

        Finds messages marked with ``TOOL_GUARD_DENIED_MARK`` and
        removes them.  When *include_denial_response* is ``True``,
        also removes the assistant message immediately following the
        last marked message (the LLM's denial explanation).
        """
        ids_to_delete: list[str] = []
        last_marked_idx = -1

        for i, (msg, marks) in enumerate(self.memory.content):
            if TOOL_GUARD_DENIED_MARK in marks:
                ids_to_delete.append(msg.id)
                last_marked_idx = i

        if (
            include_denial_response
            and last_marked_idx >= 0
            and last_marked_idx + 1 < len(self.memory.content)
        ):
            next_msg, _ = self.memory.content[last_marked_idx + 1]
            if next_msg.role == "assistant":
                ids_to_delete.append(next_msg.id)

        if ids_to_delete:
            removed = await self.memory.delete(ids_to_delete)
            logger.info(
                "Tool guard: cleaned up %d denied message(s)",
                removed,
            )

    # ------------------------------------------------------------------
    # _acting override
    # ------------------------------------------------------------------

    async def _acting(self, tool_call) -> dict | None:  # noqa: C901
        """Intercept sensitive tool calls before execution.

        1. If tool is in *denied_tools*, auto-deny unconditionally.
        2. Check for a one-shot pre-approval.
        3. If tool is in the guarded scope, run ToolGuardEngine.
        4. If findings exist, enter the approval flow.
        5. Otherwise, delegate to ``super()._acting``.
        """
        self._ensure_tool_guard()

        engine = self._tool_guard_engine
        tool_name: str = tool_call.get("name", "")
        tool_input: dict = tool_call.get("input", {})

        try:
            recruiting_block = self._get_recruiting_runtime_block(tool_name)
            if recruiting_block is not None:
                logger.warning(
                    "Recruiting guard: blocking tool '%s' after stop signal "
                    "(site=%s, status=%s, source_tool=%s)",
                    tool_name,
                    recruiting_block.site,
                    recruiting_block.status,
                    recruiting_block.source_tool,
                )
                return await self._acting_recruiting_blocked(
                    tool_call,
                    tool_name,
                    recruiting_block,
                )

            if tool_name and engine.enabled:
                if engine.is_denied(tool_name):
                    logger.warning(
                        "Tool guard: tool '%s' is in the denied "
                        "set, auto-denying",
                        tool_name,
                    )
                    result = engine.guard(tool_name, tool_input)
                    return await self._acting_auto_denied(
                        tool_call,
                        tool_name,
                        result,
                    )

                if engine.is_guarded(tool_name):
                    session_id = str(
                        self._request_context.get("session_id") or "",
                    )
                    if session_id:
                        svc = self._tool_guard_approval_service
                        consumed = await svc.consume_approval(
                            session_id,
                            tool_name,
                            tool_params=tool_input,
                        )
                        if consumed:
                            logger.info(
                                "Tool guard: pre-approved '%s' "
                                "(session %s), skipping",
                                tool_name,
                                session_id[:8],
                            )
                            self._tool_guard_pending_info = None
                            cleanup = self._cleanup_tool_guard_denied_messages
                            await cleanup(
                                include_denial_response=True,
                            )
                            return await super()._acting(  # type: ignore[misc]
                                tool_call,
                            )

                    result = engine.guard(tool_name, tool_input)
                    if result is not None and result.findings:
                        from copaw.security.tool_guard.utils import (
                            log_findings,
                        )

                        log_findings(tool_name, result)

                        if self._should_require_approval():
                            return await self._acting_with_approval(
                                tool_call,
                                tool_name,
                                result,
                            )
        except Exception as exc:
            logger.warning(
                "Tool guard check error (non-blocking): %s",
                exc,
                exc_info=True,
            )

        return await super()._acting(tool_call)  # type: ignore[misc]

    async def _acting_recruiting_blocked(
        self,
        tool_call: dict[str, Any],
        tool_name: str,
        stop_context,
    ) -> dict | None:
        """Return a hard denial when the recruiting flow says stop."""
        from agentscope.message import ToolResultBlock

        blocked_text = (
            "⛔ **Recruiting Flow Stopped / 招聘流程已停止**\n\n"
            f"- Tool / 工具: `{tool_name}`\n"
            f"- Site / 站点: `{stop_context.site}`\n"
            f"- Previous status / 上一状态: `{stop_context.status}`\n"
            f"- Source tool / 来源工具: `{stop_context.source_tool}`\n"
            f"- stop_current_turn={str(stop_context.stop_current_turn).lower()}\n\n"
            f"{stop_context.message}\n\n"
            + (
                "This turn already received a Liepin stop signal. Do not call "
                "`browser_use` or any `liepin_*` tool again until the user sends "
                "a new message.\n"
                "本轮已经收到猎聘 MCP 的停止信号。请保持当前猎聘窗口，不要切换"
                "到新的浏览器流程，等待用户下一条消息后再继续。"
                if stop_context.stop_current_turn
                else
                "This Liepin recruiting flow is already active in the current "
                "turn. Do not switch to `browser_use`; stay inside the Liepin "
                "MCP tools for this turn.\n"
                "当前轮次已经进入猎聘招聘流程。不要切换到 `browser_use`，"
                "请继续停留在 Liepin MCP 工具流里。"
            )
        )

        tool_res_msg = Msg(
            "system",
            [
                ToolResultBlock(
                    type="tool_result",
                    id=tool_call["id"],
                    name=tool_name,
                    output=[
                        {"type": "text", "text": blocked_text},
                    ],
                ),
            ],
            "system",
        )

        await self.print(tool_res_msg, True)
        await self.memory.add(tool_res_msg)
        return None

    # ------------------------------------------------------------------
    # Denied / Approval responses
    # ------------------------------------------------------------------

    async def _acting_auto_denied(
        self,
        tool_call: dict[str, Any],
        tool_name: str,
        guard_result=None,
    ) -> dict | None:
        """Auto-deny a tool call without offering approval."""
        from agentscope.message import ToolResultBlock
        from copaw.security.tool_guard.approval import (
            format_findings_summary,
        )

        if guard_result is not None and guard_result.findings:
            findings_text = format_findings_summary(guard_result)
            severity = guard_result.max_severity.value
            count = str(guard_result.findings_count)
        else:
            findings_text = "- Tool is in the denied list / 工具在禁止列表中"
            severity = "DENIED"
            count = "N/A"

        denied_text = (
            f"⛔ **Tool Blocked / 工具已拦截**\n\n"
            f"- Tool / 工具: `{tool_name}`\n"
            f"- Severity / 严重性: `{severity}`\n"
            f"- Findings / 发现: `{count}`\n\n"
            f"{findings_text}\n\n"
            f"This tool is blocked and cannot be approved.\n"
            f"该工具已被禁止，无法批准执行。"
        )

        tool_res_msg = Msg(
            "system",
            [
                ToolResultBlock(
                    type="tool_result",
                    id=tool_call["id"],
                    name=tool_name,
                    output=[
                        {"type": "text", "text": denied_text},
                    ],
                ),
            ],
            "system",
        )

        await self.print(tool_res_msg, True)
        await self.memory.add(tool_res_msg)
        return None

    async def _acting_with_approval(
        self,
        tool_call: dict[str, Any],
        tool_name: str,
        guard_result,
    ) -> dict | None:
        """Deny the tool call and record a pending approval."""
        from agentscope.message import ToolResultBlock
        from copaw.security.tool_guard.approval import (
            format_findings_summary,
        )

        channel = str(self._request_context.get("channel") or "")

        for msg, marks in reversed(self.memory.content):
            if msg.role == "assistant":
                if TOOL_GUARD_DENIED_MARK not in marks:
                    marks.append(TOOL_GUARD_DENIED_MARK)
                break

        await self._tool_guard_approval_service.create_pending(
            session_id=str(
                self._request_context.get("session_id") or "",
            ),
            user_id=str(
                self._request_context.get("user_id") or "",
            ),
            channel=channel,
            tool_name=tool_name,
            result=guard_result,
            extra={"tool_call": tool_call},
        )

        self._tool_guard_pending_info = {
            "tool_name": tool_name,
            "tool_input": tool_call.get("input", {}),
        }

        findings_text = format_findings_summary(guard_result)
        denied_text = (
            f"⚠️ **Risk Detected / 检测到风险**\n\n"
            f"- Tool / 工具: `{tool_name}`\n"
            f"- Severity / 严重性: "
            f"`{guard_result.max_severity.value}`\n"
            f"- Findings / 发现: "
            f"`{guard_result.findings_count}`\n\n"
            f"{findings_text}\n\n"
            f"Type `/approve` to approve, "
            f"or send any message to deny.\n"
            f"输入 `/approve` 批准执行，或发送任意消息拒绝。"
        )

        tool_res_msg = Msg(
            "system",
            [
                ToolResultBlock(
                    type="tool_result",
                    id=tool_call["id"],
                    name=tool_name,
                    output=[
                        {"type": "text", "text": denied_text},
                    ],
                ),
            ],
            "system",
        )

        await self.print(tool_res_msg, True)
        await self.memory.add(
            tool_res_msg,
            marks=TOOL_GUARD_DENIED_MARK,
        )
        return None

    # ------------------------------------------------------------------
    # _reasoning override (guard-aware)
    # ------------------------------------------------------------------

    async def _reasoning(
        self,
        tool_choice: (Literal["auto", "none", "required"] | None) = None,
    ) -> Msg:
        """Short-circuit reasoning when approval or recruiting stop is pending."""
        if self._last_tool_response_is_denied():
            pending = getattr(self, "_tool_guard_pending_info", None) or {}
            tool_name = pending.get("tool_name", "unknown")
            tool_input = pending.get("tool_input", {})

            params_text = _json.dumps(
                tool_input,
                ensure_ascii=False,
                indent=2,
            )
            msg = Msg(
                self.name,
                "⏳ Waiting for approval / 等待审批\n\n"
                f"- Tool / 工具: `{tool_name}`\n"
                f"- Parameters / 参数:\n"
                f"```json\n{params_text}\n```\n\n"
                "Type `/approve` to approve, "
                "or send any message to deny.\n"
                "输入 `/approve` 批准执行，"
                "或发送任意消息拒绝。",
                "assistant",
            )
            await self.print(msg, True)
            await self.memory.add(msg)
            return msg

        stop_context = self._get_recruiting_stop_context()
        if stop_context is not None:
            msg = Msg(
                self.name,
                build_recruiting_stop_reply(stop_context),
                "assistant",
            )
            await self.print(msg, True)
            await self.memory.add(msg)
            return msg

        latest_context = self._get_latest_recruiting_tool_context()
        if (
            latest_context is not None
            and latest_context.status == "ok"
            and latest_context.summary_markdown.strip()
        ):
            msg = Msg(
                self.name,
                latest_context.summary_markdown.strip(),
                "assistant",
            )
            await self.print(msg, True)
            await self.memory.add(msg)
            return msg

        return await super()._reasoning(  # type: ignore[misc]
            tool_choice=tool_choice,
        )
