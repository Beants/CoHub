# Recruiting Stop Short-Circuit Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the current CoPaw turn immediately after a Liepin MCP result returns `stop_current_turn=true`, so the model does not emit follow-up retry text or additional recruiting tool calls in the same turn.

**Architecture:** Keep the existing recruiting MCP, skill, and tool-guard architecture. Add one agent-layer short-circuit in `ToolGuardMixin._reasoning` that detects the current-turn recruiting stop context and returns a deterministic assistant message instead of invoking the model again. Cover the behavior with focused unit tests.

**Tech Stack:** Python, pytest, AgentScope message objects

---

### Task 1: Add failing tests for recruiting-turn short-circuit

**Files:**
- Modify: `tests/unit/agents/test_recruiting_tool_guard.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run the targeted pytest case and verify it fails for the expected reason**

### Task 2: Implement the minimal agent short-circuit

**Files:**
- Modify: `src/copaw/agents/tool_guard_mixin.py`
- Modify: `src/copaw/agents/recruiting_tool_guard.py`

- [ ] **Step 1: Add a helper that renders a deterministic assistant response for recruiting stop states**
- [ ] **Step 2: Short-circuit `_reasoning` when the current turn already has a recruiting stop context**
- [ ] **Step 3: Keep the existing runtime tool-call guard behavior unchanged**

### Task 3: Verify targeted regression coverage

**Files:**
- Modify: `tests/unit/agents/test_recruiting_tool_guard.py`

- [ ] **Step 1: Run the targeted recruiting guard pytest file**
- [ ] **Step 2: Run the broader recruiting-related pytest subset**
- [ ] **Step 3: Re-run the live console E2E to confirm no same-turn retry text/tool calls after `empty_result`**
