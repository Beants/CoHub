# -*- coding: utf-8 -*-
"""Installer logic for the CoHub recruiting plugin.

Handles workspace setup: SKILL.md sync, MCP client configuration,
and browser profile directory creation.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Result of a plugin installation."""
    workspace_dir: str = ""
    synced_count: int = 0
    skipped_count: int = 0
    mcp_clients_configured: list[str] = field(default_factory=list)
    boss_profile_dir: str = ""
    zhaopin_profile_dir: str = ""
    liepin_profile_dir: str = ""


def install_recruiting_plugin(
    *,
    workspace_dir: str | Path | None = None,
    runtime_root: str | Path | None = None,
    python_executable: str | None = None,
) -> InstallResult:
    """Install the recruiting assistant into a CoPaw workspace.

    This function:
    1. Syncs SKILL.md to active_skills/recruiting_assistant/
    2. Configures 3 MCP clients in the agent config
    3. Creates browser profile directories

    Args:
        workspace_dir: Path to the CoPaw workspace (e.g. ~/.copaw/workspaces/default)
        runtime_root: Path to the CoHub repository root (for MCP server paths)
        python_executable: Path to Python executable for MCP subprocess
    """
    # Resolve paths
    ws = Path(workspace_dir) if workspace_dir else _default_workspace_dir()
    rt = Path(runtime_root) if runtime_root else _guess_runtime_root()
    py_exe = python_executable or _guess_python_executable()

    result = InstallResult(workspace_dir=str(ws))

    # 1. Sync SKILL.md
    _sync_skill_md(ws, result)

    # 2. Configure MCP clients
    _configure_mcp_clients(ws, rt, py_exe, result)

    # 3. Create browser profile dirs
    _create_profile_dirs(ws, result)

    return result


def _default_workspace_dir() -> Path:
    """Return the default CoPaw workspace directory."""
    return Path.home() / ".copaw" / "workspaces" / "default"


def _guess_runtime_root() -> Path:
    """Try to find the CoHub runtime root."""
    # The plugin package is installed, so we can find our own package dir
    import cohub_recruiting
    pkg_dir = Path(cohub_recruiting.__file__).parent
    return pkg_dir


def _guess_python_executable() -> str:
    """Return the current Python executable."""
    import sys
    return sys.executable


def _sync_skill_md(workspace: Path, result: InstallResult) -> None:
    """Copy SKILL.md and references to the workspace active_skills directory."""
    from importlib.resources import files

    skill_source = files("cohub_recruiting") / "skill"
    target_dir = workspace / "active_skills" / "recruiting_assistant"
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy SKILL.md
    skill_md_source = skill_source / "SKILL.md"
    skill_md_target = target_dir / "SKILL.md"

    if hasattr(skill_md_source, 'read_text'):
        content = skill_md_source.read_text(encoding="utf-8")
        if skill_md_target.exists() and skill_md_target.read_text(encoding="utf-8") == content:
            result.skipped_count += 1
        else:
            skill_md_target.write_text(content, encoding="utf-8")
            result.synced_count += 1
            logger.info("Synced SKILL.md to %s", skill_md_target)

    # Copy references directory if it exists
    refs_source = skill_source / "references"
    refs_target = target_dir / "references"
    if hasattr(refs_source, 'iterdir'):
        refs_target.mkdir(parents=True, exist_ok=True)
        for ref_file in refs_source.iterdir():
            if hasattr(ref_file, 'read_text'):
                ref_target = refs_target / ref_file.name
                content = ref_file.read_text(encoding="utf-8")
                if ref_target.exists() and ref_target.read_text(encoding="utf-8") == content:
                    result.skipped_count += 1
                else:
                    ref_target.write_text(content, encoding="utf-8")
                    result.synced_count += 1


def _configure_mcp_clients(
    workspace: Path,
    runtime_root: Path,
    python_executable: str,
    result: InstallResult,
) -> None:
    """Add MCP client configurations to the agent config."""
    agent_config_path = workspace / "agent_config.json"

    if not agent_config_path.exists():
        logger.warning("Agent config not found at %s, skipping MCP config", agent_config_path)
        return

    config = json.loads(agent_config_path.read_text(encoding="utf-8"))
    mcp_clients = config.setdefault("mcp_clients", [])
    existing_names = {c.get("name") for c in mcp_clients if isinstance(c, dict)}

    for site in ("liepin", "boss", "zhaopin"):
        client_name = f"{site}_mcp"
        if client_name in existing_names:
            result.skipped_count += 1
            continue

        mcp_clients.append({
            "name": client_name,
            "transport": "stdio",
            "command": python_executable,
            "args": ["-m", f"cohub_recruiting.{site}_mcp"],
        })
        result.mcp_clients_configured.append(client_name)
        result.synced_count += 1
        logger.info("Configured MCP client: %s", client_name)

    agent_config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _create_profile_dirs(workspace: Path, result: InstallResult) -> None:
    """Create browser profile directories for each site."""
    base = Path.home() / ".copaw" / "recruiting"

    for site, attr in [
        ("liepin-profile", "liepin_profile_dir"),
        ("boss-profile", "boss_profile_dir"),
        ("zhaopin-profile", "zhaopin_profile_dir"),
    ]:
        profile_dir = base / site
        profile_dir.mkdir(parents=True, exist_ok=True)
        setattr(result, attr, str(profile_dir))
