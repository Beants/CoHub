# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_SOURCE = REPO_ROOT / "scripts" / "start_copaw_local.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    path.chmod(0o755)


def test_start_script_bootstraps_repo_and_opens_console(
    tmp_path: Path,
) -> None:
    assert (
        SCRIPT_SOURCE.is_file()
    ), "scripts/start_copaw_local.sh should exist"

    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    console_dir = repo_root / "console"
    package_dir = repo_root / "src" / "copaw"
    bin_dir = tmp_path / "bin"
    state_dir = tmp_path / "state"
    log_path = tmp_path / "calls.log"

    scripts_dir.mkdir(parents=True)
    console_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    bin_dir.mkdir()
    state_dir.mkdir()

    shutil.copy2(SCRIPT_SOURCE, scripts_dir / "start_copaw_local.sh")

    (console_dir / "package.json").write_text("{}", encoding="utf-8")

    _write_executable(
        bin_dir / "npm",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "npm:$*" >> "{log_path}"
        if [ "${{1:-}}" = "ci" ]; then
          mkdir -p node_modules
          exit 0
        fi
        if [ "${{1:-}}" = "run" ] && [ "${{2:-}}" = "build" ]; then
          mkdir -p dist
          printf '<!doctype html><html><body>console</body></html>' > dist/index.html
          exit 0
        fi
        exit 1
        """,
    )

    _write_executable(
        bin_dir / "uv",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "uv:$*" >> "{log_path}"
        if [ "${{1:-}}" = "sync" ]; then
          mkdir -p "$PWD/.venv"
          exit 0
        fi
        if [ "${{1:-}}" = "run" ] && [ "${{2:-}}" = "copaw" ] && [ "${{3:-}}" = "init" ]; then
          mkdir -p "${{COPAW_WORKING_DIR}}"
          mkdir -p "${{COPAW_WORKING_DIR}}/workspaces/default"
          printf '{{}}' > "${{COPAW_WORKING_DIR}}/config.json"
          exit 0
        fi
        if [ "${{1:-}}" = "run" ] && [ "${{2:-}}" = "python" ]; then
          mkdir -p "${{COPAW_WORKING_DIR}}/workspaces/default/active_skills/recruiting_assistant"
          printf '%s\\n' '---' 'name: recruiting_assistant' '---' > "${{COPAW_WORKING_DIR}}/workspaces/default/active_skills/recruiting_assistant/SKILL.md"
          exit 0
        fi
        if [ "${{1:-}}" = "run" ] && [ "${{2:-}}" = "copaw" ] && [ "${{3:-}}" = "app" ]; then
          touch "{state_dir}/app_started"
          sleep 0.2
          exit 0
        fi
        exit 1
        """,
    )

    _write_executable(
        bin_dir / "curl",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "curl:$*" >> "{log_path}"
        if [ -f "{state_dir}/app_started" ]; then
          exit 0
        fi
        exit 1
        """,
    )

    _write_executable(
        bin_dir / "open",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "open:$1" >> "{log_path}"
        exit 0
        """,
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["COPAW_START_WAIT_INTERVAL"] = "0.05"
    env["COPAW_START_WAIT_ATTEMPTS"] = "20"

    result = subprocess.run(
        ["bash", str(scripts_dir / "start_copaw_local.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert (repo_root / "src" / "copaw" / "console" / "index.html").is_file()
    assert (repo_root / ".copaw-dev" / "config.json").is_file()
    assert (
        repo_root
        / ".copaw-dev"
        / "workspaces"
        / "default"
        / "active_skills"
        / "recruiting_assistant"
        / "SKILL.md"
    ).is_file()

    log_text = log_path.read_text(encoding="utf-8")
    assert "npm:ci" in log_text
    assert "npm:run build" in log_text
    assert "uv:sync" in log_text
    assert "uv:run copaw init --defaults --accept-security" in log_text
    assert "uv:run python -c " in log_text
    assert "uv:run copaw app --host 127.0.0.1 --port 8088 --reload" in log_text
    assert "open:http://127.0.0.1:8088/" in log_text


def test_start_script_force_syncs_builtin_skills() -> None:
    """Restarting CoPaw should refresh builtin skill changes into workspace."""
    script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

    assert "sync_skills_to_working_dir(workspace, force=True)" in script_text


def test_start_script_uses_shared_recruiting_bootstrap_helper() -> None:
    """Local startup should note recruiting is now a plugin."""
    script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

    assert "cohub-recruiting-plugin" in script_text


def test_start_script_still_syncs_builtin_skills_when_app_is_already_running(
    tmp_path: Path,
) -> None:
    """An already-running CoPaw should still refresh active skill copies."""
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    console_dir = repo_root / "console"
    package_dir = repo_root / "src" / "copaw"
    bin_dir = tmp_path / "bin"
    log_path = tmp_path / "calls.log"

    scripts_dir.mkdir(parents=True)
    console_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    bin_dir.mkdir()

    shutil.copy2(SCRIPT_SOURCE, scripts_dir / "start_copaw_local.sh")
    (console_dir / "package.json").write_text("{}", encoding="utf-8")

    _write_executable(
        bin_dir / "uv",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "uv:$*" >> "{log_path}"
        if [ "${{1:-}}" = "run" ] && [ "${{2:-}}" = "python" ]; then
          mkdir -p "${{COPAW_WORKING_DIR}}/workspaces/default/active_skills/recruiting_assistant"
          printf '%s\\n' '---' 'name: recruiting_assistant' '---' > "${{COPAW_WORKING_DIR}}/workspaces/default/active_skills/recruiting_assistant/SKILL.md"
          exit 0
        fi
        if [ "${{1:-}}" = "run" ] && [ "${{2:-}}" = "copaw" ] && [ "${{3:-}}" = "init" ]; then
          mkdir -p "${{COPAW_WORKING_DIR}}/workspaces/default"
          printf '{{}}' > "${{COPAW_WORKING_DIR}}/config.json"
          exit 0
        fi
        exit 1
        """,
    )

    _write_executable(
        bin_dir / "curl",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "curl:$*" >> "{log_path}"
        exit 0
        """,
    )

    _write_executable(
        bin_dir / "open",
        f"""#!/usr/bin/env bash
        set -euo pipefail
        echo "open:$1" >> "{log_path}"
        exit 0
        """,
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        ["bash", str(scripts_dir / "start_copaw_local.sh")],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    log_text = log_path.read_text(encoding="utf-8")
    assert "uv:run python -c " in log_text
    assert "open:http://127.0.0.1:8088/" in log_text
    assert "uv:run copaw app --host 127.0.0.1 --port 8088 --reload" not in log_text
