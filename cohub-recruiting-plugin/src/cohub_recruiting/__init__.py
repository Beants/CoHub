# -*- coding: utf-8 -*-
"""CoHub Recruiting Plugin — entry point.

This plugin provides the recruiting assistant skill with 3 MCP servers
(Liepin, BOSS直聘, 智联招聘) for the CoHub/CoPaw personal AI assistant.
"""

from __future__ import annotations


def register_hooks() -> None:
    """Register all recruiting hooks with the CoHub hook system.

    Called automatically by CoHub when the plugin is discovered via
    the ``copaw.skills`` entry-point group.
    """
    from copaw.agents.skill_hooks import (
        register_blocked_text_hook,
        register_latest_context_hook,
        register_stop_context_hook,
        register_stop_reply_hook,
        register_summary_hook,
        register_tool_block_hook,
    )

    from .hooks import extract_recruiting_summary
    from .tool_guard import (
        blocked_text_hook,
        latest_context_hook,
        stop_context_hook,
        stop_reply_hook,
        tool_block_hook,
    )

    register_tool_block_hook(tool_block_hook)
    register_stop_context_hook(stop_context_hook)
    register_latest_context_hook(latest_context_hook)
    register_stop_reply_hook(stop_reply_hook)
    register_blocked_text_hook(blocked_text_hook)
    register_summary_hook(extract_recruiting_summary)
