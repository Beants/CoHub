#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export COPAW_WORKING_DIR="${COPAW_WORKING_DIR:-$REPO_ROOT/.copaw-dev}"
export COPAW_SECRET_DIR="${COPAW_SECRET_DIR:-$REPO_ROOT/.copaw-dev.secret}"

log() {
    printf '[setup_recruiting_assistant_local] %s\n' "$*"
}

die() {
    printf '[setup_recruiting_assistant_local] %s\n' "$*" >&2
    exit 1
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        die "Missing required command: $1"
    fi
}

ensure_python_env() {
    log "Syncing Python dependencies with uv"
    (
        cd "$REPO_ROOT"
        uv sync --extra dev --frozen
    )
}

ensure_initialized() {
    if [ -f "$COPAW_WORKING_DIR/config.json" ]; then
        log "Using existing CoPaw working dir at $COPAW_WORKING_DIR"
        return 0
    fi

    log "Initializing repo-local CoPaw working dir at $COPAW_WORKING_DIR"
    (
        cd "$REPO_ROOT"
        uv run copaw init --defaults --accept-security
    )
}

configure_recruiting_local() {
    local default_workspace="$COPAW_WORKING_DIR/workspaces/default"
    local boss_profile_dir="$COPAW_WORKING_DIR/recruiting/boss-profile"
    local zhaopin_profile_dir="$COPAW_WORKING_DIR/recruiting/zhaopin-profile"
    local liepin_profile_dir="$COPAW_WORKING_DIR/recruiting/liepin-profile"

    mkdir -p "$boss_profile_dir"
    mkdir -p "$zhaopin_profile_dir"
    mkdir -p "$liepin_profile_dir"

    log "Syncing recruiting_assistant skill and recruiting MCP config"
    (
        cd "$REPO_ROOT"
        REPO_ROOT="$REPO_ROOT" \
        DEFAULT_WORKSPACE="$default_workspace" \
        BOSS_PROFILE_DIR="$boss_profile_dir" \
        ZHAOPIN_PROFILE_DIR="$zhaopin_profile_dir" \
        LIEPIN_PROFILE_DIR="$liepin_profile_dir" \
        uv run python -c "
import os
from pathlib import Path

from copaw.agents.skills_manager import sync_skills_to_working_dir
from copaw.config.config import MCPClientConfig, MCPConfig, load_agent_config, save_agent_config
from copaw.envs import load_envs, save_envs

workspace = Path(os.environ['DEFAULT_WORKSPACE'])
repo_root = Path(os.environ['REPO_ROOT'])
boss_profile_dir = os.environ['BOSS_PROFILE_DIR']
zhaopin_profile_dir = os.environ['ZHAOPIN_PROFILE_DIR']
liepin_profile_dir = os.environ['LIEPIN_PROFILE_DIR']

sync_skills_to_working_dir(
    workspace,
    skill_names=['recruiting_assistant'],
    force=True,
)

agent_config = load_agent_config('default')
if agent_config.mcp is None:
    agent_config.mcp = MCPConfig(clients={})

agent_config.mcp.clients['liepin'] = MCPClientConfig(
    name='liepin_mcp',
    description='Liepin recruiting adapter for CoPaw local development',
    enabled=True,
    transport='stdio',
    command=str(repo_root / '.venv' / 'bin' / 'python'),
    args=[
        '-m',
        'copaw.agents.skills.recruiting_assistant.liepin_mcp.server',
    ],
    env={
        'LIEPIN_PROFILE_DIR': liepin_profile_dir,
    },
    cwd=str(repo_root),
)
agent_config.mcp.clients['boss'] = MCPClientConfig(
    name='boss_mcp',
    description='BOSS recruiting adapter for CoPaw local development',
    enabled=True,
    transport='stdio',
    command=str(repo_root / '.venv' / 'bin' / 'python'),
    args=[
        '-m',
        'copaw.agents.skills.recruiting_assistant.boss_mcp.server',
    ],
    env={
        'BOSS_PROFILE_DIR': boss_profile_dir,
    },
    cwd=str(repo_root),
)
agent_config.mcp.clients['zhaopin'] = MCPClientConfig(
    name='zhaopin_mcp',
    description='Zhaopin recruiting adapter for CoPaw local development',
    enabled=True,
    transport='stdio',
    command=str(repo_root / '.venv' / 'bin' / 'python'),
    args=[
        '-m',
        'copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server',
    ],
    env={
        'ZHAOPIN_PROFILE_DIR': zhaopin_profile_dir,
    },
    cwd=str(repo_root),
)
save_agent_config('default', agent_config)

envs = load_envs()
envs.setdefault('RECRUITING_ENABLED_SITES', 'liepin')
envs.setdefault('RECRUITING_SITE_FAILURE_MODE', 'partial_success')
envs.setdefault('RECRUITING_DEFAULT_PAGE', '1')
envs.setdefault('RECRUITING_DEFAULT_RESULT_LIMIT', '20')
envs.setdefault('BOSS_PROFILE_DIR', boss_profile_dir)
envs.setdefault('ZHAOPIN_PROFILE_DIR', zhaopin_profile_dir)
envs.setdefault('LIEPIN_PROFILE_DIR', liepin_profile_dir)
save_envs(envs)
print(f'workspace={workspace}')
print(f'boss_profile_dir={boss_profile_dir}')
print(f'zhaopin_profile_dir={zhaopin_profile_dir}')
print(f'liepin_profile_dir={liepin_profile_dir}')
"
    )
}

main() {
    require_command uv

    ensure_python_env
    ensure_initialized
    configure_recruiting_local

    log "Done. Restart CoPaw or rerun scripts/start_copaw_local.sh if it is not already running."
}

main "$@"
