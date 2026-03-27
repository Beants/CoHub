# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_SOURCE = REPO_ROOT / "scripts" / "setup_recruiting_assistant_local.sh"


def test_setup_script_wires_zhaopin_mcp_client() -> None:
    """The recruiting setup script should mount the Zhaopin MCP server."""
    script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

    assert "ZHAOPIN_PROFILE_DIR" in script_text
    assert "agent_config.mcp.clients['zhaopin']" in script_text
    assert (
        "copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server"
        in script_text
    )


def test_setup_script_seeds_zhaopin_profile_env_default() -> None:
    """Local setup should seed the Zhaopin profile env var."""
    script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

    assert "envs.setdefault('ZHAOPIN_PROFILE_DIR'" in script_text
