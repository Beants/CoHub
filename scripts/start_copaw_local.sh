#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

HOST="${COPAW_APP_HOST:-127.0.0.1}"
PORT="${COPAW_APP_PORT:-8088}"
APP_URL="http://${HOST}:${PORT}/"
HEALTH_URL="http://${HOST}:${PORT}/api/version"
WAIT_INTERVAL="${COPAW_START_WAIT_INTERVAL:-1}"
WAIT_ATTEMPTS="${COPAW_START_WAIT_ATTEMPTS:-60}"

export COPAW_WORKING_DIR="${COPAW_WORKING_DIR:-$REPO_ROOT/.copaw-dev}"
export COPAW_SECRET_DIR="${COPAW_SECRET_DIR:-$REPO_ROOT/.copaw-dev.secret}"

OPENER_PID=""

cleanup() {
    if [ -n "$OPENER_PID" ]; then
        kill "$OPENER_PID" >/dev/null 2>&1 || true
    fi
}

log() {
    printf '[start_copaw_local] %s\n' "$*"
}

die() {
    printf '[start_copaw_local] %s\n' "$*" >&2
    exit 1
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        die "Missing required command: $1"
    fi
}

is_app_ready() {
    curl -fsS --max-time 1 "$HEALTH_URL" >/dev/null 2>&1
}

open_browser() {
    if command -v open >/dev/null 2>&1; then
        open "$APP_URL" >/dev/null 2>&1 || true
        return 0
    fi

    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$APP_URL" >/dev/null 2>&1 || true
        return 0
    fi

    log "Browser auto-open is unavailable on this system. Open ${APP_URL} manually."
}

open_when_ready() {
    local attempts="$WAIT_ATTEMPTS"

    while [ "$attempts" -gt 0 ]; do
        if is_app_ready; then
            log "Opening ${APP_URL}"
            open_browser
            return 0
        fi
        attempts=$((attempts - 1))
        sleep "$WAIT_INTERVAL"
    done

    log "Timed out waiting for CoPaw at ${APP_URL}. Open it manually after startup."
}

needs_console_install() {
    local console_dir="$REPO_ROOT/console"
    local node_modules_dir="$console_dir/node_modules"
    local package_lock="$console_dir/package-lock.json"
    local node_lock="$node_modules_dir/.package-lock.json"

    if [ ! -d "$node_modules_dir" ]; then
        return 0
    fi

    if [ -f "$package_lock" ] && [ ! -f "$node_lock" ]; then
        return 0
    fi

    if [ -f "$package_lock" ] && [ "$package_lock" -nt "$node_lock" ]; then
        return 0
    fi

    return 1
}

ensure_console_assets() {
    local console_dir="$REPO_ROOT/console"
    local console_dist="$console_dir/dist"
    local console_dest="$REPO_ROOT/src/copaw/console"

    [ -f "$console_dir/package.json" ] || die "Console source not found at $console_dir"

    require_command npm

    if needs_console_install; then
        log "Installing console dependencies with npm ci"
        (
            cd "$console_dir"
            npm ci
        )
    fi

    log "Building console frontend"
    (
        cd "$console_dir"
        npm run build
    )

    [ -f "$console_dist/index.html" ] || die "Console build did not produce $console_dist/index.html"

    log "Syncing console assets into src/copaw/console"
    rm -rf "$console_dest"
    mkdir -p "$console_dest"
    cp -R "$console_dist/." "$console_dest/"
}

ensure_python_env() {
    require_command uv

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

sync_builtin_skills() {
    local default_workspace="$COPAW_WORKING_DIR/workspaces/default"

    if [ ! -d "$default_workspace" ]; then
        return 0
    fi

    log "Syncing builtin skills into $default_workspace"
    (
        cd "$REPO_ROOT"
        uv run python -c "
from pathlib import Path
from copaw.agents.skills_manager import sync_skills_to_working_dir

workspace = Path(r'''$default_workspace''')
synced, skipped = sync_skills_to_working_dir(workspace, force=True)
print(f'synced={synced} skipped={skipped}')
"
    )
}

start_app() {
    log "Starting CoPaw on ${APP_URL}"
    (
        cd "$REPO_ROOT"
        uv run copaw app --host "$HOST" --port "$PORT" --reload
    )
}

main() {
    require_command curl

    if is_app_ready; then
        log "CoPaw is already running at ${APP_URL}"
        ensure_initialized
        sync_builtin_skills
        open_browser
        return 0
    fi

    ensure_console_assets
    ensure_python_env
    ensure_initialized
    sync_builtin_skills

    open_when_ready &
    OPENER_PID="$!"
    trap cleanup EXIT INT TERM

    start_app
    wait "$OPENER_PID" || true
    OPENER_PID=""
}

main "$@"
