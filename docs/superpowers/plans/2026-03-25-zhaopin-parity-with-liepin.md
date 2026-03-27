# Zhaopin Parity With Liepin Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Zhaopin adapter to functional parity with the existing Liepin adapter for structured filters, larger-result pagination behavior, and extraction reliability safeguards.

**Architecture:** Extend the existing `zhaopin_mcp` flow instead of refactoring it into Liepin's full shape. Add the smallest set of session helpers and service-layer branches needed to support recruiter-page filters, optional multi-page accumulation, and bounded reliability/debug handling while preserving the working live-browser flow already verified.

**Tech Stack:** Python, Pydantic, FastMCP, Playwright persistent browser sessions, pytest.

---

## Chunk 1: Structured Filters

### Task 1: Add failing tests for recruiter-page filters

**Files:**
- Modify: `tests/unit/skills/recruiting_assistant/test_zhaopin_session.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`

- [ ] Add tests proving Zhaopin applies recruiter-page filters for `expected_city`, `experience`, and `education`.
- [ ] Run the focused pytest commands and confirm the new assertions fail for the right reason.

### Task 2: Implement Zhaopin recruiter filter application

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/session.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`

- [ ] Add session helpers that can click visible filter options on the recruiter search page.
- [ ] Call those helpers from the service/search flow without changing the existing keyword-search behavior.
- [ ] Re-run focused tests and verify they pass.

## Chunk 2: Pagination Aggregation

### Task 3: Add failing tests for large result limits

**Files:**
- Modify: `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`

- [ ] Add a test proving `result_limit > current page cap` keeps paging until enough unique candidates are accumulated.
- [ ] Add a test proving `next_page()` advances from the last aggregated page end, not just `current page + 1`.
- [ ] Run the focused pytest commands and confirm the tests fail.

### Task 4: Implement multi-page accumulation for Zhaopin

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`

- [ ] Add a paginated search branch mirroring the Liepin behavior at the service layer.
- [ ] Preserve the existing default behavior of returning the current page in full when no larger explicit limit is requested.
- [ ] Re-run focused tests and verify they pass.

## Chunk 3: Reliability Guards

### Task 5: Add failing tests for extraction reliability handling

**Files:**
- Modify: `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`

- [ ] Add tests covering unreliable extraction handling and debug-dump hooks.
- [ ] Run the focused pytest commands and confirm the tests fail.

### Task 6: Implement bounded reliability/debug handling

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/extractors.py`

- [ ] Add candidate-batch reliability checks and an `extraction_unreliable` result path.
- [ ] Add minimal debug snapshot writing gated by configured dump dir.
- [ ] Re-run the Zhaopin and recruiting-assistant test suites and verify they pass.

## Chunk 4: Live Verification

### Task 7: Verify live recruiter behavior

**Files:**
- Modify: `/tmp/zhaopin_live_harness.py` if extra probe commands are needed

- [ ] Run live browser verification for filter application, page-2 aggregation, and detail links.
- [ ] Record the exact observed outcomes before declaring parity.
