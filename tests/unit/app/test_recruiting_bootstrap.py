# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from copaw.app.recruiting_bootstrap import (
    bootstrap_recruiting_assistant_workspace,
)
from copaw.config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    AgentsConfig,
    Config,
    MCPClientConfig,
    MCPConfig,
)
from copaw.config.utils import save_config
from copaw.envs import save_envs


def test_bootstrap_recruiting_assistant_workspace_seeds_mcp_and_envs(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / ".copaw"
    secret_dir = tmp_path / ".copaw.secret"
    runtime_root = tmp_path / "runtime"
    python_executable = runtime_root / ".venv" / "bin" / "python"

    result = bootstrap_recruiting_assistant_workspace(
        working_dir=working_dir,
        secret_dir=secret_dir,
        runtime_root=runtime_root,
        python_executable=python_executable,
    )

    skill_md = (
        working_dir
        / "workspaces"
        / "default"
        / "active_skills"
        / "recruiting_assistant"
        / "SKILL.md"
    )
    assert skill_md.is_file()

    agent_config_path = working_dir / "workspaces" / "default" / "agent.json"
    agent_config = json.loads(agent_config_path.read_text(encoding="utf-8"))
    clients = agent_config["mcp"]["clients"]

    assert clients["liepin"]["command"] == str(python_executable)
    assert clients["liepin"]["args"] == [
        "-m",
        "copaw.agents.skills.recruiting_assistant.liepin_mcp.server",
    ]
    assert clients["liepin"]["env"]["LIEPIN_PROFILE_DIR"] == str(
        result.liepin_profile_dir,
    )
    assert clients["boss"]["env"]["BOSS_PROFILE_DIR"] == str(
        result.boss_profile_dir,
    )
    assert clients["zhaopin"]["args"] == [
        "-m",
        "copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server",
    ]
    assert clients["zhaopin"]["cwd"] == str(runtime_root)

    envs_path = secret_dir / "envs.json"
    envs = json.loads(envs_path.read_text(encoding="utf-8"))

    assert envs["RECRUITING_ENABLED_SITES"] == "liepin"
    assert envs["RECRUITING_SITE_FAILURE_MODE"] == "partial_success"
    assert envs["RECRUITING_DEFAULT_PAGE"] == "1"
    assert envs["RECRUITING_DEFAULT_RESULT_LIMIT"] == "20"
    assert envs["BOSS_PROFILE_DIR"] == str(result.boss_profile_dir)
    assert envs["ZHAOPIN_PROFILE_DIR"] == str(result.zhaopin_profile_dir)
    assert envs["LIEPIN_PROFILE_DIR"] == str(result.liepin_profile_dir)


def test_bootstrap_recruiting_assistant_workspace_preserves_existing_settings(
    tmp_path: Path,
) -> None:
    working_dir = tmp_path / ".copaw"
    secret_dir = tmp_path / ".copaw.secret"
    workspace_dir = working_dir / "workspaces" / "default"
    runtime_root = tmp_path / "runtime"
    python_executable = runtime_root / ".venv" / "bin" / "python"

    save_config(
        Config(
            agents=AgentsConfig(
                active_agent="default",
                profiles={
                    "default": AgentProfileRef(
                        id="default",
                        workspace_dir=str(workspace_dir),
                    ),
                },
            ),
        ),
        working_dir / "config.json",
    )

    workspace_dir.mkdir(parents=True, exist_ok=True)
    agent_config = AgentProfileConfig(
        id="default",
        name="Default",
        workspace_dir=str(workspace_dir),
        mcp=MCPConfig(
            clients={
                "custom": MCPClientConfig(
                    name="custom_mcp",
                    transport="stdio",
                    command="/usr/bin/custom-python",
                    args=["-m", "custom.server"],
                ),
            },
        ),
    )
    (workspace_dir / "agent.json").write_text(
        agent_config.model_dump_json(exclude_none=True, indent=2),
        encoding="utf-8",
    )
    save_envs(
        {
            "RECRUITING_ENABLED_SITES": "boss",
            "CUSTOM_ENV": "keep",
        },
        secret_dir / "envs.json",
    )

    bootstrap_recruiting_assistant_workspace(
        working_dir=working_dir,
        secret_dir=secret_dir,
        workspace_dir=workspace_dir,
        runtime_root=runtime_root,
        python_executable=python_executable,
    )

    agent_config_data = json.loads(
        (workspace_dir / "agent.json").read_text(encoding="utf-8"),
    )
    clients = agent_config_data["mcp"]["clients"]

    assert "custom" in clients
    assert clients["custom"]["command"] == "/usr/bin/custom-python"
    assert "liepin" in clients
    assert "boss" in clients
    assert "zhaopin" in clients

    envs = json.loads((secret_dir / "envs.json").read_text(encoding="utf-8"))
    assert envs["RECRUITING_ENABLED_SITES"] == "boss"
    assert envs["CUSTOM_ENV"] == "keep"
    assert envs["ZHAOPIN_PROFILE_DIR"].endswith("zhaopin-profile")
