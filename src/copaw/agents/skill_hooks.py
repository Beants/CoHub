# -*- coding: utf-8 -*-
"""Generic skill hook registry.

Skills register callbacks at import time (via entry-points or explicit
``register_*`` calls).  The agent framework invokes these hooks at the
appropriate points without knowing anything about specific skills.

Hook execution order follows registration order.  The first hook that
returns a non-``None`` / non-empty result wins; later hooks are skipped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence, Union

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Shared flow-context dataclass
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SkillFlowContext:
    """Opaque context produced by a skill-specific flow guard.

    Plugins populate this with whatever metadata their guard logic
    needs.  The agent framework reads only the well-known fields
    below; everything else travels in *extra*.
    """

    skill: str = ""
    site: str = ""
    status: str = ""
    stop_current_turn: bool = False
    source_tool: str = ""
    message: str = ""
    continue_tool: str = ""
    summary_markdown: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------
# Hook type aliases
# ------------------------------------------------------------------

# (memory_content, tool_name) -> SkillFlowContext | None
ToolBlockHook = Callable[[Sequence[Any], str], SkillFlowContext | None]

# (memory_content) -> SkillFlowContext | None
StopContextHook = Callable[[Sequence[Any]], SkillFlowContext | None]

# (memory_content) -> SkillFlowContext | None
LatestContextHook = Callable[[Sequence[Any]], SkillFlowContext | None]

# (context) -> str
StopReplyHook = Callable[[SkillFlowContext], str]

# (context, tool_name) -> str
BlockedTextHook = Callable[[SkillFlowContext, str], str]

# (tool_output: str | list[dict]) -> str  (empty string = no match)
SummaryHook = Callable[[Union[str, list[dict[str, Any]]]], str]

# ------------------------------------------------------------------
# Internal registry
# ------------------------------------------------------------------

_tool_block_hooks: list[ToolBlockHook] = []
_stop_context_hooks: list[StopContextHook] = []
_latest_context_hooks: list[LatestContextHook] = []
_stop_reply_hooks: list[StopReplyHook] = []
_blocked_text_hooks: list[BlockedTextHook] = []
_summary_hooks: list[SummaryHook] = []

# ------------------------------------------------------------------
# Registration helpers
# ------------------------------------------------------------------


def register_tool_block_hook(hook: ToolBlockHook) -> None:
    """Register a hook that may block a tool call for a given turn."""
    _tool_block_hooks.append(hook)


def register_stop_context_hook(hook: StopContextHook) -> None:
    """Register a hook that detects a skill stop signal."""
    _stop_context_hooks.append(hook)


def register_latest_context_hook(hook: LatestContextHook) -> None:
    """Register a hook that finds the latest skill tool context."""
    _latest_context_hooks.append(hook)


def register_stop_reply_hook(hook: StopReplyHook) -> None:
    """Register a hook that builds a user-facing stop reply."""
    _stop_reply_hooks.append(hook)


def register_blocked_text_hook(hook: BlockedTextHook) -> None:
    """Register a hook that builds the blocked-tool response text."""
    _blocked_text_hooks.append(hook)


def register_summary_hook(hook: SummaryHook) -> None:
    """Register a hook that extracts a pre-rendered summary from tool output."""
    _summary_hooks.append(hook)


# ------------------------------------------------------------------
# Execution helpers (first-match-wins)
# ------------------------------------------------------------------


def run_tool_block_hooks(
    memory_content: Sequence[Any],
    tool_name: str,
) -> SkillFlowContext | None:
    """Return the first blocking context, or ``None`` to allow."""
    for hook in _tool_block_hooks:
        try:
            result = hook(memory_content, tool_name)
            if result is not None:
                return result
        except Exception:
            logger.warning("tool_block hook %r raised", hook, exc_info=True)
    return None


def run_stop_context_hooks(
    memory_content: Sequence[Any],
) -> SkillFlowContext | None:
    """Return the first stop context detected, or ``None``."""
    for hook in _stop_context_hooks:
        try:
            result = hook(memory_content)
            if result is not None:
                return result
        except Exception:
            logger.warning("stop_context hook %r raised", hook, exc_info=True)
    return None


def run_latest_context_hooks(
    memory_content: Sequence[Any],
) -> SkillFlowContext | None:
    """Return the latest skill tool context, or ``None``."""
    for hook in _latest_context_hooks:
        try:
            result = hook(memory_content)
            if result is not None:
                return result
        except Exception:
            logger.warning(
                "latest_context hook %r raised", hook, exc_info=True
            )
    return None


def run_stop_reply_hooks(context: SkillFlowContext) -> str:
    """Build a stop reply from *context*.  Falls back to a generic message."""
    for hook in _stop_reply_hooks:
        try:
            reply = hook(context)
            if reply:
                return reply
        except Exception:
            logger.warning("stop_reply hook %r raised", hook, exc_info=True)
    # Generic fallback
    msg = context.message.strip()
    return msg if msg else "The current skill flow has stopped. Please send a new message."


def run_blocked_text_hooks(
    context: SkillFlowContext,
    tool_name: str,
) -> str:
    """Build the blocked-tool response text.  Falls back to a generic message."""
    for hook in _blocked_text_hooks:
        try:
            text = hook(context, tool_name)
            if text:
                return text
        except Exception:
            logger.warning(
                "blocked_text hook %r raised", hook, exc_info=True
            )
    # Generic fallback
    return (
        f"⛔ **Skill Flow Blocked**\n\n"
        f"- Tool: `{tool_name}`\n"
        f"- Skill: `{context.skill}`\n"
        f"- Site: `{context.site}`\n"
        f"- Status: `{context.status}`\n"
        f"- Source tool: `{context.source_tool}`\n\n"
        f"{context.message}\n\n"
        "This tool call was blocked by the skill flow guard. "
        "Please wait for the user's next message before retrying."
    )


def run_summary_hooks(
    output: str | list[dict[str, Any]],
) -> str:
    """Extract a pre-rendered summary from tool output.  Returns ``""`` if none."""
    for hook in _summary_hooks:
        try:
            summary = hook(output)
            if summary:
                return summary
        except Exception:
            logger.warning("summary hook %r raised", hook, exc_info=True)
    return ""


# ------------------------------------------------------------------
# Bulk registration convenience
# ------------------------------------------------------------------


def clear_all_hooks() -> None:
    """Remove all registered hooks.  Useful for testing."""
    _tool_block_hooks.clear()
    _stop_context_hooks.clear()
    _latest_context_hooks.clear()
    _stop_reply_hooks.clear()
    _blocked_text_hooks.clear()
    _summary_hooks.clear()
