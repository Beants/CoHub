# -*- coding: utf-8 -*-
"""Unit tests for copaw.agents.skill_hooks."""

from __future__ import annotations

import logging
from typing import Any, Sequence

import pytest

from copaw.agents.skill_hooks import (
    SkillFlowContext,
    clear_all_hooks,
    register_blocked_text_hook,
    register_latest_context_hook,
    register_stop_context_hook,
    register_stop_reply_hook,
    register_summary_hook,
    register_tool_block_hook,
    run_blocked_text_hooks,
    run_latest_context_hooks,
    run_stop_context_hooks,
    run_stop_reply_hooks,
    run_summary_hooks,
    run_tool_block_hooks,
)


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Ensure every test starts and ends with a clean hook registry."""
    clear_all_hooks()
    yield
    clear_all_hooks()


# ------------------------------------------------------------------ #
# SkillFlowContext dataclass
# ------------------------------------------------------------------ #


class TestSkillFlowContext:
    def test_defaults(self):
        ctx = SkillFlowContext()
        assert ctx.skill == ""
        assert ctx.site == ""
        assert ctx.status == ""
        assert ctx.stop_current_turn is False
        assert ctx.source_tool == ""
        assert ctx.message == ""
        assert ctx.continue_tool == ""
        assert ctx.summary_markdown == ""
        assert ctx.extra == {}

    def test_extra_defaults_to_empty_dict(self):
        ctx1 = SkillFlowContext()
        ctx2 = SkillFlowContext()
        assert ctx1.extra is not ctx2.extra  # separate dict instances

    def test_frozen(self):
        ctx = SkillFlowContext(skill="s")
        with pytest.raises(AttributeError):
            ctx.skill = "other"  # type: ignore[misc]

    def test_custom_fields(self):
        ctx = SkillFlowContext(
            skill="deploy",
            site="prod",
            status="running",
            stop_current_turn=True,
            source_tool="cli",
            message="done",
            continue_tool="next",
            summary_markdown="# ok",
            extra={"key": 42},
        )
        assert ctx.skill == "deploy"
        assert ctx.site == "prod"
        assert ctx.status == "running"
        assert ctx.stop_current_turn is True
        assert ctx.source_tool == "cli"
        assert ctx.message == "done"
        assert ctx.continue_tool == "next"
        assert ctx.summary_markdown == "# ok"
        assert ctx.extra == {"key": 42}

    def test_equality(self):
        a = SkillFlowContext(skill="a", site="b")
        b = SkillFlowContext(skill="a", site="b")
        assert a == b

    def test_hashable(self):
        # frozen dataclass with default_factory dict is NOT hashable
        # because dict is unhashable, which is expected behaviour.
        ctx = SkillFlowContext()
        with pytest.raises(TypeError):
            hash(ctx)


# ------------------------------------------------------------------ #
# Registration
# ------------------------------------------------------------------ #


class TestRegistration:
    """Hooks get appended to the internal lists in registration order."""

    def test_register_tool_block_hook(self):
        calls: list[str] = []

        def h1(mc: Sequence[Any], tn: str):
            calls.append("h1")
            return None

        def h2(mc: Sequence[Any], tn: str):
            calls.append("h2")
            return None

        register_tool_block_hook(h1)
        register_tool_block_hook(h2)
        run_tool_block_hooks([], "t")
        assert calls == ["h1", "h2"]

    def test_register_stop_context_hook(self):
        calls: list[str] = []

        def h(mc):
            calls.append("h")
            return None

        register_stop_context_hook(h)
        run_stop_context_hooks([])
        assert calls == ["h"]

    def test_register_latest_context_hook(self):
        calls: list[str] = []

        def h(mc):
            calls.append("h")
            return None

        register_latest_context_hook(h)
        run_latest_context_hooks([])
        assert calls == ["h"]

    def test_register_stop_reply_hook(self):
        calls: list[str] = []

        def h(ctx):
            calls.append("h")
            return ""

        register_stop_reply_hook(h)
        run_stop_reply_hooks(SkillFlowContext())
        assert calls == ["h"]

    def test_register_blocked_text_hook(self):
        calls: list[str] = []

        def h(ctx, tn):
            calls.append("h")
            return ""

        register_blocked_text_hook(h)
        run_blocked_text_hooks(SkillFlowContext(), "t")
        assert calls == ["h"]

    def test_register_summary_hook(self):
        calls: list[str] = []

        def h(output):
            calls.append("h")
            return ""

        register_summary_hook(h)
        run_summary_hooks("data")
        assert calls == ["h"]


# ------------------------------------------------------------------ #
# No hooks registered – return defaults
# ------------------------------------------------------------------ #


class TestNoHooksRegistered:
    def test_tool_block_returns_none(self):
        assert run_tool_block_hooks([], "tool") is None

    def test_stop_context_returns_none(self):
        assert run_stop_context_hooks([]) is None

    def test_latest_context_returns_none(self):
        assert run_latest_context_hooks([]) is None

    def test_stop_reply_returns_generic_message(self):
        result = run_stop_reply_hooks(SkillFlowContext())
        assert result == "The current skill flow has stopped. Please send a new message."

    def test_stop_reply_returns_context_message_when_present(self):
        ctx = SkillFlowContext(message="custom msg")
        assert run_stop_reply_hooks(ctx) == "custom msg"

    def test_stop_reply_strips_whitespace_message(self):
        ctx = SkillFlowContext(message="   ")
        result = run_stop_reply_hooks(ctx)
        assert result == "The current skill flow has stopped. Please send a new message."

    def test_blocked_text_returns_generic_fallback(self):
        ctx = SkillFlowContext(
            skill="sk", site="st", status="blocked",
            source_tool="src", message="msg",
        )
        result = run_blocked_text_hooks(ctx, "my_tool")
        assert "⛔ **Skill Flow Blocked**" in result
        assert "`my_tool`" in result
        assert "`sk`" in result
        assert "`st`" in result
        assert "`blocked`" in result
        assert "`src`" in result
        assert "msg" in result

    def test_summary_returns_empty_string(self):
        assert run_summary_hooks("anything") == ""

    def test_summary_returns_empty_string_for_list_input(self):
        assert run_summary_hooks([{"key": "val"}]) == ""


# ------------------------------------------------------------------ #
# First-match-wins semantics
# ------------------------------------------------------------------ #


class TestFirstMatchWins:
    def test_tool_block_first_match_wins(self):
        ctx_a = SkillFlowContext(skill="a")
        ctx_b = SkillFlowContext(skill="b")
        register_tool_block_hook(lambda mc, tn: ctx_a)
        register_tool_block_hook(lambda mc, tn: ctx_b)
        assert run_tool_block_hooks([], "t") is ctx_a

    def test_stop_context_first_match_wins(self):
        ctx = SkillFlowContext(skill="first")
        register_stop_context_hook(lambda mc: ctx)
        register_stop_context_hook(lambda mc: SkillFlowContext(skill="second"))
        assert run_stop_context_hooks([]) is ctx

    def test_latest_context_first_match_wins(self):
        ctx = SkillFlowContext(skill="first")
        register_latest_context_hook(lambda mc: ctx)
        register_latest_context_hook(lambda mc: SkillFlowContext(skill="second"))
        assert run_latest_context_hooks([]) is ctx

    def test_stop_reply_first_match_wins(self):
        register_stop_reply_hook(lambda ctx: "first")
        register_stop_reply_hook(lambda ctx: "second")
        assert run_stop_reply_hooks(SkillFlowContext()) == "first"

    def test_blocked_text_first_match_wins(self):
        register_blocked_text_hook(lambda ctx, tn: "first")
        register_blocked_text_hook(lambda ctx, tn: "second")
        assert run_blocked_text_hooks(SkillFlowContext(), "t") == "first"

    def test_summary_first_match_wins(self):
        register_summary_hook(lambda o: "first")
        register_summary_hook(lambda o: "second")
        assert run_summary_hooks("data") == "first"

    def test_second_hook_skipped_when_first_matches(self):
        """Ensure the second hook is never called."""
        called = []
        register_tool_block_hook(lambda mc, tn: SkillFlowContext(skill="hit"))

        def second(mc, tn):
            called.append(True)
            return SkillFlowContext(skill="miss")

        register_tool_block_hook(second)
        run_tool_block_hooks([], "t")
        assert called == []


# ------------------------------------------------------------------ #
# Multiple hooks – fallthrough when first returns None / empty
# ------------------------------------------------------------------ #


class TestMultipleHooksFallthrough:
    def test_tool_block_skips_none(self):
        ctx = SkillFlowContext(skill="winner")
        register_tool_block_hook(lambda mc, tn: None)
        register_tool_block_hook(lambda mc, tn: ctx)
        assert run_tool_block_hooks([], "t") is ctx

    def test_stop_context_skips_none(self):
        ctx = SkillFlowContext(skill="winner")
        register_stop_context_hook(lambda mc: None)
        register_stop_context_hook(lambda mc: ctx)
        assert run_stop_context_hooks([]) is ctx

    def test_latest_context_skips_none(self):
        ctx = SkillFlowContext(skill="winner")
        register_latest_context_hook(lambda mc: None)
        register_latest_context_hook(lambda mc: ctx)
        assert run_latest_context_hooks([]) is ctx

    def test_stop_reply_skips_empty_string(self):
        register_stop_reply_hook(lambda ctx: "")
        register_stop_reply_hook(lambda ctx: "winner")
        assert run_stop_reply_hooks(SkillFlowContext()) == "winner"

    def test_blocked_text_skips_empty_string(self):
        register_blocked_text_hook(lambda ctx, tn: "")
        register_blocked_text_hook(lambda ctx, tn: "winner")
        assert run_blocked_text_hooks(SkillFlowContext(), "t") == "winner"

    def test_summary_skips_empty_string(self):
        register_summary_hook(lambda o: "")
        register_summary_hook(lambda o: "winner")
        assert run_summary_hooks("data") == "winner"

    def test_all_none_returns_none(self):
        register_tool_block_hook(lambda mc, tn: None)
        register_tool_block_hook(lambda mc, tn: None)
        assert run_tool_block_hooks([], "t") is None


# ------------------------------------------------------------------ #
# Error isolation – exceptions are caught and logged
# ------------------------------------------------------------------ #


class TestErrorIsolation:
    @pytest.fixture(autouse=True)
    def _enable_propagation(self):
        """Temporarily enable propagation so caplog can capture records."""
        copaw_logger = logging.getLogger("copaw")
        orig = copaw_logger.propagate
        copaw_logger.propagate = True
        yield
        copaw_logger.propagate = orig

    def test_tool_block_hook_exception_caught(self, caplog):
        def bad(mc, tn):
            raise ValueError("boom")

        ctx = SkillFlowContext(skill="ok")
        register_tool_block_hook(bad)
        register_tool_block_hook(lambda mc, tn: ctx)

        with caplog.at_level(logging.WARNING, logger="copaw.agents.skill_hooks"):
            result = run_tool_block_hooks([], "t")

        assert result is ctx
        assert "tool_block hook" in caplog.text
        assert "boom" in caplog.text

    def test_stop_context_hook_exception_caught(self, caplog):
        ctx = SkillFlowContext(skill="ok")
        register_stop_context_hook(lambda mc: (_ for _ in ()).throw(RuntimeError("err")))
        register_stop_context_hook(lambda mc: ctx)

        with caplog.at_level(logging.WARNING, logger="copaw.agents.skill_hooks"):
            result = run_stop_context_hooks([])

        assert result is ctx

    def test_latest_context_hook_exception_caught(self, caplog):
        ctx = SkillFlowContext(skill="ok")

        def bad(mc):
            raise TypeError("oops")

        register_latest_context_hook(bad)
        register_latest_context_hook(lambda mc: ctx)

        with caplog.at_level(logging.WARNING, logger="copaw.agents.skill_hooks"):
            result = run_latest_context_hooks([])

        assert result is ctx
        assert "latest_context hook" in caplog.text

    def test_stop_reply_hook_exception_falls_through(self, caplog):
        register_stop_reply_hook(lambda ctx: (_ for _ in ()).throw(Exception("err")))

        with caplog.at_level(logging.WARNING, logger="copaw.agents.skill_hooks"):
            result = run_stop_reply_hooks(SkillFlowContext(message="fallback"))

        assert result == "fallback"

    def test_blocked_text_hook_exception_falls_through(self, caplog):
        register_blocked_text_hook(lambda ctx, tn: (_ for _ in ()).throw(Exception("err")))

        with caplog.at_level(logging.WARNING, logger="copaw.agents.skill_hooks"):
            result = run_blocked_text_hooks(SkillFlowContext(), "t")

        assert "⛔ **Skill Flow Blocked**" in result

    def test_summary_hook_exception_falls_through(self, caplog):
        def bad(output):
            raise KeyError("x")

        register_summary_hook(bad)

        with caplog.at_level(logging.WARNING, logger="copaw.agents.skill_hooks"):
            result = run_summary_hooks("data")

        assert result == ""
        assert "summary hook" in caplog.text

    def test_exception_does_not_prevent_later_hooks(self):
        """After an exception, subsequent hooks still execute."""
        results: list[str] = []

        def bad(mc, tn):
            raise RuntimeError("fail")

        def good(mc, tn):
            results.append("ran")
            return SkillFlowContext(skill="good")

        register_tool_block_hook(bad)
        register_tool_block_hook(good)
        ctx = run_tool_block_hooks([], "t")
        assert ctx is not None
        assert ctx.skill == "good"
        assert results == ["ran"]


# ------------------------------------------------------------------ #
# clear_all_hooks
# ------------------------------------------------------------------ #


class TestClearAllHooks:
    def test_clears_all_registries(self):
        register_tool_block_hook(lambda mc, tn: SkillFlowContext())
        register_stop_context_hook(lambda mc: SkillFlowContext())
        register_latest_context_hook(lambda mc: SkillFlowContext())
        register_stop_reply_hook(lambda ctx: "x")
        register_blocked_text_hook(lambda ctx, tn: "x")
        register_summary_hook(lambda o: "x")

        clear_all_hooks()

        assert run_tool_block_hooks([], "t") is None
        assert run_stop_context_hooks([]) is None
        assert run_latest_context_hooks([]) is None
        # stop_reply falls back to generic
        assert "stopped" in run_stop_reply_hooks(SkillFlowContext())
        # blocked_text falls back to generic
        assert "⛔" in run_blocked_text_hooks(SkillFlowContext(), "t")
        # summary returns empty
        assert run_summary_hooks("x") == ""

    def test_clear_is_idempotent(self):
        clear_all_hooks()
        clear_all_hooks()  # no error


# ------------------------------------------------------------------ #
# Fallback messages – detailed assertions
# ------------------------------------------------------------------ #


class TestFallbackMessages:
    def test_stop_reply_generic_message_exact(self):
        result = run_stop_reply_hooks(SkillFlowContext())
        assert result == "The current skill flow has stopped. Please send a new message."

    def test_stop_reply_prefers_context_message(self):
        ctx = SkillFlowContext(message="  Please restart.  ")
        result = run_stop_reply_hooks(ctx)
        assert result == "Please restart."

    def test_blocked_text_generic_contains_all_fields(self):
        ctx = SkillFlowContext(
            skill="my_skill",
            site="my_site",
            status="my_status",
            source_tool="my_source",
            message="my_message",
        )
        result = run_blocked_text_hooks(ctx, "my_tool")
        for expected in [
            "⛔ **Skill Flow Blocked**",
            "Tool: `my_tool`",
            "Skill: `my_skill`",
            "Site: `my_site`",
            "Status: `my_status`",
            "Source tool: `my_source`",
            "my_message",
            "This tool call was blocked by the skill flow guard.",
        ]:
            assert expected in result, f"Missing: {expected!r}"

    def test_summary_returns_empty_on_no_hooks(self):
        assert run_summary_hooks("text") == ""
        assert run_summary_hooks([]) == ""


# ------------------------------------------------------------------ #
# Hook arguments are passed correctly
# ------------------------------------------------------------------ #


class TestHookArguments:
    def test_tool_block_hook_receives_args(self):
        received: list[tuple] = []

        def hook(mc, tn):
            received.append((list(mc), tn))
            return None

        register_tool_block_hook(hook)
        run_tool_block_hooks(["a", "b"], "my_tool")
        assert received == [(["a", "b"], "my_tool")]

    def test_stop_context_hook_receives_args(self):
        received = []

        def hook(mc):
            received.append(list(mc))
            return None

        register_stop_context_hook(hook)
        run_stop_context_hooks([1, 2, 3])
        assert received == [[1, 2, 3]]

    def test_latest_context_hook_receives_args(self):
        received = []

        def hook(mc):
            received.append(list(mc))
            return None

        register_latest_context_hook(hook)
        run_latest_context_hooks(["x"])
        assert received == [["x"]]

    def test_stop_reply_hook_receives_context(self):
        received = []
        ctx = SkillFlowContext(skill="s")

        def hook(c):
            received.append(c)
            return "ok"

        register_stop_reply_hook(hook)
        run_stop_reply_hooks(ctx)
        assert received == [ctx]

    def test_blocked_text_hook_receives_args(self):
        received: list[tuple] = []
        ctx = SkillFlowContext(skill="s")

        def hook(c, tn):
            received.append((c, tn))
            return "ok"

        register_blocked_text_hook(hook)
        run_blocked_text_hooks(ctx, "tool")
        assert received == [(ctx, "tool")]

    def test_summary_hook_receives_string_output(self):
        received = []

        def hook(o):
            received.append(o)
            return ""

        register_summary_hook(hook)
        run_summary_hooks("hello")
        assert received == ["hello"]

    def test_summary_hook_receives_list_output(self):
        received = []
        data = [{"a": 1}]

        def hook(o):
            received.append(o)
            return ""

        register_summary_hook(hook)
        run_summary_hooks(data)
        assert received == [data]
