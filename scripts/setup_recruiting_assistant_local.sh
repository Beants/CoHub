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
    # NOTE: Recruiting assistant has been migrated to an independent plugin
    # (cohub-recruiting-plugin). Install it with: pip install cohub-recruiting-plugin
    log "Recruiting assistant is now a plugin. Install with: pip install cohub-recruiting-plugin"
}

main() {
    require_command uv

    ensure_python_env
    ensure_initialized
    configure_recruiting_local

    log "Done. Restart CoPaw or rerun scripts/start_copaw_local.sh if it is not already running."
}

main "$@"
