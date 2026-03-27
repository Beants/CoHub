# CoPaw Local Startup Script Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-command local startup script that prepares this source checkout, starts CoPaw with a repo-local working directory, and opens the web console automatically.

**Architecture:** Keep the existing CoPaw CLI and package layout unchanged. Add a small shell script under `scripts/` that orchestrates frontend build, Python environment sync, first-run initialization, and app startup; isolate local runtime state in repo-local ignored directories so the checkout stays self-contained.

**Tech Stack:** Bash, `uv`, `npm`, pytest, existing CoPaw CLI commands

---

## Chunk 1: Bootstrap Script

### Task 1: Add a failing test for the local startup workflow

**Files:**
- Create: `tests/unit/scripts/test_start_copaw_local.py`
- Test: `tests/unit/scripts/test_start_copaw_local.py`

- [ ] **Step 1: Write the failing test**

```python
def test_start_script_bootstraps_repo_and_opens_console(tmp_path):
    ...
    assert result.returncode == 0
    assert (repo_root / "src/copaw/console/index.html").exists()
    assert (repo_root / ".copaw-dev/config.json").exists()
    assert "open:http://127.0.0.1:8088/" in log_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/scripts/test_start_copaw_local.py -v`
Expected: FAIL because `scripts/start_copaw_local.sh` does not exist yet.

### Task 2: Implement the startup script

**Files:**
- Create: `scripts/start_copaw_local.sh`
- Modify: `scripts/README.md`
- Test: `tests/unit/scripts/test_start_copaw_local.py`

- [ ] **Step 1: Write minimal implementation**

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=...
export COPAW_WORKING_DIR=...
export COPAW_SECRET_DIR=...

# build console, sync Python deps, init once, wait for backend, open browser
```

- [ ] **Step 2: Run the focused test**

Run: `uv run pytest tests/unit/scripts/test_start_copaw_local.py -v`
Expected: PASS

## Chunk 2: Local Runtime Hygiene

### Task 3: Ignore repo-local runtime state

**Files:**
- Modify: `.gitignore`
- Test: `tests/unit/scripts/test_start_copaw_local.py`

- [ ] **Step 1: Add local ignore rules**

```gitignore
.copaw-dev/
.copaw-dev.secret/
```

- [ ] **Step 2: Re-run focused verification**

Run: `uv run pytest tests/unit/scripts/test_start_copaw_local.py -v`
Expected: PASS

### Task 4: Run direct script verification

**Files:**
- Modify: `scripts/start_copaw_local.sh`

- [ ] **Step 1: Shell syntax check**

Run: `bash -n scripts/start_copaw_local.sh`
Expected: PASS with no output

- [ ] **Step 2: Run the script in the real repo**

Run: `bash scripts/start_copaw_local.sh`
Expected: frontend assets are built into `src/copaw/console/`, `.copaw-dev/config.json` is created on first run, CoPaw starts on `127.0.0.1:8088`, and the browser opens `http://127.0.0.1:8088/`
