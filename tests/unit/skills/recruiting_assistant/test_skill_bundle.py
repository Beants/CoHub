# -*- coding: utf-8 -*-
"""Tests for the recruiting assistant built-in skill bundle."""

from pathlib import Path

from copaw.agents.skills_manager import SkillService


def test_recruiting_assistant_builtin_skill_is_discoverable(
    tmp_path: Path,
) -> None:
    """The built-in recruiting assistant skill should be listed."""
    skill_service = SkillService(tmp_path)

    skills = {
        skill.name: skill for skill in skill_service.list_all_skills()
    }

    assert "recruiting_assistant" in skills

    skill = skills["recruiting_assistant"]
    assert skill.source == "builtin"
    assert "recruiting" in skill.description.lower()
    assert (Path(skill.path) / "__init__.py").exists()


def test_recruiting_assistant_skill_exposes_reference_bundle(
    tmp_path: Path,
) -> None:
    """The skill should ship the reference docs needed for V1 rollout."""
    skill_service = SkillService(tmp_path)

    skills = {
        skill.name: skill for skill in skill_service.list_all_skills()
    }
    skill = skills["recruiting_assistant"]

    assert skill.references == {
        "manual-verification.md": None,
        "mcp-config.example.json": None,
        "query-contract.md": None,
        "setup.md": None,
    }


def test_recruiting_assistant_skill_requires_recruiting_mcp_workflows(
    tmp_path: Path,
) -> None:
    """The skill instructions should steer the agent to site MCP tools."""
    skill_service = SkillService(tmp_path)
    skills = {
        skill.name: skill for skill in skill_service.list_all_skills()
    }
    skill = skills["recruiting_assistant"]

    content = (Path(skill.path) / "SKILL.md").read_text(encoding="utf-8")

    assert "boss_prepare_browser" in content
    assert "boss_search_candidates" in content
    assert "boss_next_page" in content
    assert "boss_continue_last_search" in content
    assert "zhaopin_prepare_browser" in content
    assert "zhaopin_search_candidates" in content
    assert "zhaopin_next_page" in content
    assert "zhaopin_continue_last_search" in content
    assert "liepin_prepare_browser" in content
    assert "liepin_search_candidates" in content
    assert "liepin_next_page" in content
    assert "liepin_continue_last_search" in content
    assert "browser_use" in content
    assert "不要再次调用 `liepin_prepare_browser`" in content
    assert "stop_current_turn=true" in content
    assert "do not call `liepin_status`" in content
    assert "site_layout_changed" in content
    assert "extraction_unreliable" in content
    assert "never switch to `browser_use`" in content
    assert "再加一页" in content
