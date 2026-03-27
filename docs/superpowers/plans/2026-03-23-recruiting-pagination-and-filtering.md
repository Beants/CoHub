# Recruiting Pagination And Filtering Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stable multi-page candidate aggregation, a dedicated next-page MCP tool, and explicit-conflict filtering for Liepin recruiting searches.

**Architecture:** Keep all behavior inside the recruiting assistant and Liepin MCP adapter. Refactor the service to reuse single-page search logic for both normal search and auto-pagination, then expose a thin `liepin_next_page` server entrypoint backed by cached successful query state.

**Tech Stack:** Python, FastMCP, Playwright-based Liepin session adapter, pytest

---

## Chunk 1: Filtering Semantics

### Task 1: Lock explicit-conflict filtering with tests

**Files:**
- Modify: `tests/unit/skills/recruiting_assistant/test_liepin_service.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/liepin_mcp/service.py`

- [ ] **Step 1: Write failing tests for explicit title conflicts and structured mismatches**
- [ ] **Step 2: Run the targeted tests and verify they fail**
- [ ] **Step 3: Implement minimal filtering changes so explicit mismatches are removed while missing fields remain allowed**
- [ ] **Step 4: Re-run the targeted tests and verify they pass**

## Chunk 2: Multi-page Aggregation

### Task 2: Lock cross-page accumulation with tests

**Files:**
- Modify: `tests/unit/skills/recruiting_assistant/test_liepin_service.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/liepin_mcp/service.py`

- [ ] **Step 1: Write failing tests for `result_limit > page capacity`**
- [ ] **Step 2: Run the targeted tests and verify they fail**
- [ ] **Step 3: Implement multi-page aggregation, dedupe, and safety stop conditions**
- [ ] **Step 4: Re-run the targeted tests and verify they pass**

## Chunk 3: Dedicated Next-page Tool

### Task 3: Expose stable follow-up pagination

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/liepin_mcp/server.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/liepin_mcp/service.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_liepin_service.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/setup.md`

- [ ] **Step 1: Write failing tests for `liepin_next_page` behavior**
- [ ] **Step 2: Run the targeted tests and verify they fail**
- [ ] **Step 3: Implement `next_page` service method and MCP tool**
- [ ] **Step 4: Update skill docs so the model prefers `liepin_next_page` for `下一页/再加一页`**
- [ ] **Step 5: Re-run the targeted tests and verify they pass**

## Chunk 4: Final Verification

### Task 4: Verify the recruiting bundle end to end

**Files:**
- Modify: `tests/unit/skills/recruiting_assistant/test_liepin_service.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`

- [ ] **Step 1: Run `uv run pytest tests/unit/skills/recruiting_assistant -q`**
- [ ] **Step 2: Run skill sync into `.copaw-dev/workspaces/default`**
- [ ] **Step 3: Summarize any live-validation steps still needing the user's logged-in browser**
