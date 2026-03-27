# BOSS MCP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a BOSS 企业版人才搜索 MCP adapter that reuses the user's browser session, returns recruiter-visible candidate lists, and renders BOSS-specific fields in CoPaw.

**Architecture:** Extend the shared recruiting models/renderer with a site-specific attribute map, then add a new `boss_mcp` package mirroring the existing Liepin adapter. Keep search execution inside the site MCP adapter and preserve recruiter frontend truth without local post-filtering.

**Tech Stack:** Python, Pydantic, FastMCP, Playwright persistent browser sessions, pytest.

---

## Chunk 1: Shared Contracts And Rendering

### Task 1: Extend shared candidate model

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/models.py`
- Test: `tests/unit/skills/recruiting_assistant/test_renderer.py`

- [ ] **Step 1: Write the failing test**

Add coverage asserting that candidate rows can render dynamic site-specific fields from `extra_attributes`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_renderer.py -q`
Expected: FAIL because `CandidateSummary` has no `extra_attributes` support.

- [ ] **Step 3: Write minimal implementation**

Add `extra_attributes: dict[str, str] = Field(default_factory=dict)` to `CandidateSummary`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_renderer.py -q`
Expected: PASS for the new model shape.

### Task 2: Render fixed and dynamic markdown table columns

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/renderer.py`
- Test: `tests/unit/skills/recruiting_assistant/test_renderer.py`

- [ ] **Step 1: Write the failing test**

Add/adjust tests to expect fixed columns plus dynamic site-specific columns when `extra_attributes` is present.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_renderer.py -q`
Expected: FAIL because the renderer does not append dynamic columns yet.

- [ ] **Step 3: Write minimal implementation**

Update the renderer to:
- collect all `extra_attributes` keys for a site's visible candidates
- append them to the markdown table columns in stable order
- fill missing values with `-`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_renderer.py -q`
Expected: PASS.

## Chunk 2: BOSS MCP Skeleton And Config

### Task 3: Add BOSS runtime config and docs wiring

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/config.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/setup.md`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json`
- Modify: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Modify: `scripts/setup_recruiting_assistant_local.sh`
- Test: `tests/unit/skills/recruiting_assistant/test_config.py` (create if missing)

- [ ] **Step 1: Write the failing test**

Add config parsing coverage for `BOSS_PROFILE_DIR`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config.py -q`
Expected: FAIL because BOSS config is not parsed yet.

- [ ] **Step 3: Write minimal implementation**

Add BOSS profile/debug config fields and document/setup them.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config.py -q`
Expected: PASS.

### Task 4: Add BOSS MCP package skeleton

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/models.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/session.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/extractors.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/service.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/server.py`
- Test: `tests/unit/skills/recruiting_assistant/test_boss_service.py`

- [ ] **Step 1: Write the failing test**

Add a smoke test that imports the BOSS service and expects the MCP tools to exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_service.py -q`
Expected: FAIL because the package does not exist.

- [ ] **Step 3: Write minimal implementation**

Create the package and expose the tool names mirroring Liepin.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_service.py -q`
Expected: PASS.

## Chunk 3: BOSS Search Flow

### Task 5: Implement BOSS session status and browser preparation

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/session.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/service.py`
- Test: `tests/unit/skills/recruiting_assistant/test_boss_session.py`

- [ ] **Step 1: Write the failing test**

Add tests for BOSS recruiter login/captcha status detection and persistent browser prepare behavior.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_session.py -q`
Expected: FAIL because status detection and prepare behavior are missing.

- [ ] **Step 3: Write minimal implementation**

Implement:
- persistent browser launch config
- BOSS recruiter URL detection
- `check_status`
- `ensure_entry_page`
- `prepare_browser`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_session.py -q`
Expected: PASS.

### Task 6: Implement first-page search and extraction

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/session.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/extractors.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/service.py`
- Test: `tests/unit/skills/recruiting_assistant/test_boss_extractors.py`
- Test: `tests/unit/skills/recruiting_assistant/test_boss_service.py`

- [ ] **Step 1: Write the failing test**

Add tests for:
- phrase search entry on the recruiter talent page
- list-card extraction into shared fields plus `extra_attributes`
- `summary_markdown` generation from BOSS results

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_extractors.py tests/unit/skills/recruiting_assistant/test_boss_service.py -q`
Expected: FAIL because search/extraction are not implemented.

- [ ] **Step 3: Write minimal implementation**

Implement search entry, first-page extraction, and BOSS result rendering without local post-filtering.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_extractors.py tests/unit/skills/recruiting_assistant/test_boss_service.py -q`
Expected: PASS.

### Task 7: Implement continuation and pagination

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/session.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/boss_mcp/service.py`
- Test: `tests/unit/skills/recruiting_assistant/test_boss_session.py`
- Test: `tests/unit/skills/recruiting_assistant/test_boss_service.py`

- [ ] **Step 1: Write the failing test**

Add tests for:
- `boss_continue_last_search`
- `boss_next_page`
- page 2 being distinct from page 1 at the session/service level

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_session.py tests/unit/skills/recruiting_assistant/test_boss_service.py -q`
Expected: FAIL because continuation/pagination are incomplete.

- [ ] **Step 3: Write minimal implementation**

Implement continuation state, pagination state, and stable page advancement logic.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_boss_session.py tests/unit/skills/recruiting_assistant/test_boss_service.py -q`
Expected: PASS.

## Chunk 4: Verification And Sync

### Task 8: Run recruiting regression and sync skills

**Files:**
- Modify: none

- [ ] **Step 1: Run focused regression**

Run: `uv run pytest tests/unit/skills/recruiting_assistant -q`
Expected: PASS.

- [ ] **Step 2: Sync builtin skills**

Run:

```bash
uv run python -c "from pathlib import Path; from copaw.agents.skills_manager import sync_skills_to_working_dir; workspace=Path('.copaw-dev/workspaces/default'); synced, skipped = sync_skills_to_working_dir(workspace, force=True); print({'synced': synced, 'skipped': skipped})"
```

Expected: synced result summary.

- [ ] **Step 3: Manual live verification checkpoint**

Use a logged-in BOSS recruiter browser session to verify:
- first page search
- manual login/captcha continuation
- next page behavior
- detail links
- expanded table columns from `extra_attributes`
