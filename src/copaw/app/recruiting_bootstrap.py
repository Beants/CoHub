# -*- coding: utf-8 -*-
"""Bootstrap recruiting assistant workspace state."""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


_ENV_KEYS = ("COPAW_WORKING_DIR", "COPAW_SECRET_DIR")
_AGENT_ID = "default"
_RECRUITING_SKILL_NAME = "recruiting_assistant"


@dataclass(frozen=True)
class RecruitingBootstrapResult:
    working_dir: Path
    secret_dir: Path
    workspace_dir: Path
    boss_profile_dir: Path
    zhaopin_profile_dir: Path
    liepin_profile_dir: Path
    synced_count: int
    skipped_count: int


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


@contextmanager
def _configured_bootstrap_paths(
    working_dir: Path,
    secret_dir: Path,
) -> Iterator[None]:
    previous_env = {key: os.environ.get(key) for key in _ENV_KEYS}
    os.environ["COPAW_WORKING_DIR"] = str(working_dir)
    os.environ["COPAW_SECRET_DIR"] = str(secret_dir)

    import copaw.constant as constant
    import copaw.config.config as config_models
    import copaw.config.utils as config_utils
    import copaw.envs.store as env_store

    previous_values = {
        "constant_working_dir": constant.WORKING_DIR,
        "constant_secret_dir": constant.SECRET_DIR,
        "config_working_dir": config_models.WORKING_DIR,
        "config_utils_working_dir": config_utils.WORKING_DIR,
        "env_store_working_dir": env_store._BOOTSTRAP_WORKING_DIR,
        "env_store_secret_dir": env_store._BOOTSTRAP_SECRET_DIR,
        "env_store_envs_json": env_store._ENVS_JSON,
        "env_store_legacy_candidates": (
            env_store._LEGACY_ENVS_JSON_CANDIDATES
        ),
    }

    constant.WORKING_DIR = working_dir
    constant.SECRET_DIR = secret_dir
    config_models.WORKING_DIR = working_dir
    config_utils.WORKING_DIR = working_dir
    env_store._BOOTSTRAP_WORKING_DIR = working_dir
    env_store._BOOTSTRAP_SECRET_DIR = secret_dir
    env_store._ENVS_JSON = secret_dir / "envs.json"
    env_store._LEGACY_ENVS_JSON_CANDIDATES = (
        Path(env_store.__file__).resolve().parent / "envs.json",
        working_dir / "envs.json",
    )

    try:
        yield
    finally:
        constant.WORKING_DIR = previous_values["constant_working_dir"]
        constant.SECRET_DIR = previous_values["constant_secret_dir"]
        config_models.WORKING_DIR = previous_values["config_working_dir"]
        config_utils.WORKING_DIR = previous_values[
            "config_utils_working_dir"
        ]
        env_store._BOOTSTRAP_WORKING_DIR = previous_values[
            "env_store_working_dir"
        ]
        env_store._BOOTSTRAP_SECRET_DIR = previous_values[
            "env_store_secret_dir"
        ]
        env_store._ENVS_JSON = previous_values["env_store_envs_json"]
        env_store._LEGACY_ENVS_JSON_CANDIDATES = previous_values[
            "env_store_legacy_candidates"
        ]
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
                continue
            os.environ[key] = value


def bootstrap_recruiting_assistant_workspace(
    *,
    working_dir: str | Path | None = None,
    secret_dir: str | Path | None = None,
    workspace_dir: str | Path | None = None,
    runtime_root: str | Path | None = None,
    python_executable: str | Path | None = None,
    agent_id: str = _AGENT_ID,
) -> RecruitingBootstrapResult:
    """Ensure recruiting assistant skill, MCP clients, and env defaults.

    This helper is designed for one-shot startup bootstrap flows where we
    need the same recruiting setup in local dev and packaged desktop builds.
    """

    resolved_working_dir = _resolve_path(
        working_dir or os.environ.get("COPAW_WORKING_DIR", "~/.copaw"),
    )
    resolved_secret_dir = _resolve_path(
        secret_dir
        or os.environ.get("COPAW_SECRET_DIR", f"{resolved_working_dir}.secret"),
    )
    resolved_workspace_dir = _resolve_path(
        workspace_dir or resolved_working_dir / "workspaces" / agent_id,
    )
    resolved_runtime_root = _resolve_path(runtime_root or Path.cwd())
    resolved_python_executable = _resolve_path(
        python_executable or Path(sys.executable),
    )

    boss_profile_dir = resolved_working_dir / "recruiting" / "boss-profile"
    zhaopin_profile_dir = (
        resolved_working_dir / "recruiting" / "zhaopin-profile"
    )
    liepin_profile_dir = resolved_working_dir / "recruiting" / "liepin-profile"

    resolved_workspace_dir.mkdir(parents=True, exist_ok=True)
    boss_profile_dir.mkdir(parents=True, exist_ok=True)
    zhaopin_profile_dir.mkdir(parents=True, exist_ok=True)
    liepin_profile_dir.mkdir(parents=True, exist_ok=True)

    with _configured_bootstrap_paths(
        resolved_working_dir,
        resolved_secret_dir,
    ):
        from copaw.agents.skills_manager import sync_skills_to_working_dir
        from copaw.config.config import (
            AgentProfileRef,
            MCPClientConfig,
            MCPConfig,
            load_agent_config,
            save_agent_config,
        )
        from copaw.config.utils import load_config, save_config
        from copaw.envs import load_envs, save_envs

        config_path = resolved_working_dir / "config.json"
        config = load_config(config_path)
        config.agents.profiles[agent_id] = AgentProfileRef(
            id=agent_id,
            workspace_dir=str(resolved_workspace_dir),
            enabled=True,
        )
        if config.agents.active_agent not in config.agents.profiles:
            config.agents.active_agent = agent_id
        save_config(config, config_path)

        synced_count, skipped_count = sync_skills_to_working_dir(
            resolved_workspace_dir,
            skill_names=[_RECRUITING_SKILL_NAME],
            force=True,
        )

        agent_config = load_agent_config(agent_id)
        if agent_config.mcp is None:
            agent_config.mcp = MCPConfig(clients={})

        agent_config.mcp.clients["liepin"] = MCPClientConfig(
            name="liepin_mcp",
            description="Liepin recruiting adapter for CoPaw",
            enabled=True,
            transport="stdio",
            command=str(resolved_python_executable),
            args=[
                "-m",
                "copaw.agents.skills.recruiting_assistant.liepin_mcp.server",
            ],
            env={
                "LIEPIN_PROFILE_DIR": str(liepin_profile_dir),
            },
            cwd=str(resolved_runtime_root),
        )
        agent_config.mcp.clients["boss"] = MCPClientConfig(
            name="boss_mcp",
            description="BOSS recruiting adapter for CoPaw",
            enabled=True,
            transport="stdio",
            command=str(resolved_python_executable),
            args=[
                "-m",
                "copaw.agents.skills.recruiting_assistant.boss_mcp.server",
            ],
            env={
                "BOSS_PROFILE_DIR": str(boss_profile_dir),
            },
            cwd=str(resolved_runtime_root),
        )
        agent_config.mcp.clients["zhaopin"] = MCPClientConfig(
            name="zhaopin_mcp",
            description="Zhaopin recruiting adapter for CoPaw",
            enabled=True,
            transport="stdio",
            command=str(resolved_python_executable),
            args=[
                "-m",
                "copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server",
            ],
            env={
                "ZHAOPIN_PROFILE_DIR": str(zhaopin_profile_dir),
            },
            cwd=str(resolved_runtime_root),
        )
        save_agent_config(agent_id, agent_config)

        envs = load_envs()
        envs.setdefault("RECRUITING_ENABLED_SITES", "liepin")
        envs.setdefault("RECRUITING_SITE_FAILURE_MODE", "partial_success")
        envs.setdefault("RECRUITING_DEFAULT_PAGE", "1")
        envs.setdefault("RECRUITING_DEFAULT_RESULT_LIMIT", "20")
        envs.setdefault("BOSS_PROFILE_DIR", str(boss_profile_dir))
        envs.setdefault("ZHAOPIN_PROFILE_DIR", str(zhaopin_profile_dir))
        envs.setdefault("LIEPIN_PROFILE_DIR", str(liepin_profile_dir))
        save_envs(envs)

    return RecruitingBootstrapResult(
        working_dir=resolved_working_dir,
        secret_dir=resolved_secret_dir,
        workspace_dir=resolved_workspace_dir,
        boss_profile_dir=boss_profile_dir,
        zhaopin_profile_dir=zhaopin_profile_dir,
        liepin_profile_dir=liepin_profile_dir,
        synced_count=synced_count,
        skipped_count=skipped_count,
    )


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    result = bootstrap_recruiting_assistant_workspace()
    print(f"Recruiting bootstrap done: synced={result.synced_count}, "
          f"skipped={result.skipped_count}")
    print(f"  working_dir: {result.working_dir}")
    print(f"  workspace:   {result.workspace_dir}")
