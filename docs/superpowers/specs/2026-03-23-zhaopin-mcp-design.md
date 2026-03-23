# Zhaopin MCP Design

- Date: 2026-03-23
- Status: Approved in conversation
- Scope: Add a full Zhaopin recruiter candidate-search MCP adapter modeled after the existing Liepin and BOSS adapters

## Summary

The recruiting assistant already has full adapters for Liepin and BOSS, while `zhaopin` only exists as an enabled-site enum and renderer label. This design adds a complete `zhaopin_mcp` package with the same operational surface as the existing site adapters: persistent browser reuse, manual verification continuation, first-page search, next-page search, shared result envelopes, local setup wiring, and unit-test coverage.

The implementation should match the current repository shape rather than introducing a new cross-site base class. Shared recruiting models, rendering, and site labels stay unchanged except for adding Zhaopin-specific configuration and docs wiring.

## Goals

- Add a complete Zhaopin recruiter MCP adapter under `recruiting_assistant`.
- Keep the tool surface aligned with Liepin and BOSS so upper layers do not need special handling.
- Reuse the shared recruiting query/result contracts and renderer.
- Support browser preparation, search, pagination, manual-verification continuation, and close-browser flows.
- Return recruiter-visible candidate list results as `CandidateSummary` rows with optional site-specific attributes.
- Cover the new adapter with focused unit tests and local setup/docs updates.

## Non-goals

- No refactor of the recruiting assistant into a generic adapter framework.
- No redesign of CoPaw core architecture or model orchestration.
- No write actions on recruiting sites such as greet, favorite, note, or invite.
- No deep detail-page scraping beyond stable list-page fields needed for candidate summaries.
- No generic `browser_use` replacement for normal recruiting-site flows.

## Architecture

### Shared Layer

Keep using the existing shared recruiting contracts:

- `NormalizedSearchQuery`
- `CandidateSummary`
- `SiteSearchResult`
- `render_search_results()`

The renderer already supports `zhaopin` labels and site-specific extra columns through `extra_attributes`, so the Zhaopin work should stay additive and site-local.

### Site Adapter Layer

Add a new sibling package:

- `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/__init__.py`
- `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/models.py`
- `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/session.py`
- `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/extractors.py`
- `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`
- `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/server.py`

Responsibilities:

- `session.py`: persistent browser/profile reuse, recruiter entry-page recovery, login/captcha detection, search submission, and pagination.
- `extractors.py`: convert Zhaopin recruiter list cards into `CandidateSummary` plus total-count extraction.
- `service.py`: site-level orchestration, query normalization, last-query state, last-successful-query state, and summary rendering.
- `server.py`: FastMCP stdio entrypoint exposing the standard recruiting tool surface.
- `models.py`: local browser-launch config and any adapter-local constants/types.

This iteration should not extract a shared browser-session base class. Zhaopin should follow the current BOSS shape more than cloning the full Liepin implementation, because BOSS already reflects the newer, lighter adapter boundary.

## Tool Surface

The Zhaopin adapter should expose the same lifecycle shape as the existing site adapters:

- `zhaopin_status`
- `zhaopin_prepare_browser`
- `zhaopin_search_candidates`
- `zhaopin_next_page`
- `zhaopin_continue_last_search`
- `zhaopin_close_browser`

Upper layers should be able to treat these tools exactly like `liepin_*` and `boss_*`.

## Search And State Flow

### Browser Preparation

`zhaopin_prepare_browser` should:

- open or reuse a persistent Zhaopin browser profile
- prefer a stable Zhaopin recruiter entry page
- detect `ok`, `not_logged_in`, or `captcha_required`
- return the standard same-window continuation hints

When login or verification is still required, the result must tell the caller to keep using the same Zhaopin window and continue with `zhaopin_continue_last_search`.

### Search

`zhaopin_search_candidates` should:

- accept the existing shared recruiting query contract
- normalize the primary search phrase from `position`, then `keyword`, then `company`
- use `session.py` for all browser actions
- use `extractors.py` only for page-data extraction
- return a shared `SiteSearchResult`
- populate `summary_markdown` through `render_search_results()`

If the query cannot produce a usable Zhaopin search phrase, the adapter should return `unsupported_filter`.

### Next Page

`zhaopin_next_page` should:

- depend on the latest successful normalized query
- increment `page`
- reuse the same search pipeline instead of making the model rebuild the query or guess page numbers

This matches the existing dedicated next-page behavior already used for Liepin and BOSS.

### Continue Last Search

`zhaopin_continue_last_search` should:

- depend on the latest attempted query, not only the latest successful one
- re-check the current Zhaopin page status first
- return `not_logged_in` or `captcha_required` again if the user has not completed manual steps yet
- resume the original query unchanged once status returns to `ok`

## Error Handling

Zhaopin should use the existing site-status vocabulary rather than adding new status types:

- `ok`
- `not_logged_in`
- `captcha_required`
- `site_layout_changed`
- `extraction_unreliable`
- `unsupported_filter`
- `empty_result`
- `internal_error`

Rules:

- If the adapter cannot find the core Zhaopin recruiter search surface after the page is loaded, return `site_layout_changed`.
- If extracted cards are missing critical identity fields such as candidate name or detail link at a rate that makes the page unreliable, return `extraction_unreliable` instead of emitting partial garbage.
- If the site asks for manual login or human verification, return the same-window continuation guidance and stop that turn.
- If no candidates are found after a successful search action, return `empty_result`.

## Config And Docs

Add Zhaopin-specific runtime wiring without changing the shared config structure:

- `ZHAOPIN_PROFILE_DIR`
- `ZHAOPIN_DEBUG_DUMP_DIR`

Update:

- `src/copaw/agents/skills/recruiting_assistant/config.py`
- `src/copaw/agents/skills/recruiting_assistant/references/setup.md`
- `src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json`
- `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- `scripts/setup_recruiting_assistant_local.sh`

The local setup script should mount the new `zhaopin_mcp` server and seed the matching environment variable so local CoPaw development can enable the adapter without manual JSON edits.

## Validation

### Automated

Add or update focused tests for:

- `tests/unit/skills/recruiting_assistant/test_config.py`
  - parse `ZHAOPIN_PROFILE_DIR`
  - parse `ZHAOPIN_DEBUG_DUMP_DIR`
- `tests/unit/skills/recruiting_assistant/test_zhaopin_session.py`
  - browser launch config resolution
  - login/captcha detection
  - entry-page recovery
  - visible search-input usage
  - stable page advancement
- `tests/unit/skills/recruiting_assistant/test_zhaopin_extractors.py`
  - candidate-card normalization
  - total-count extraction
  - unreliable/invalid extraction cases
- `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`
  - prepare-browser envelope
  - manual verification flow
  - successful search envelope
  - `zhaopin_next_page`
  - `zhaopin_continue_last_search`
  - close-browser behavior

### Manual

Using a logged-in Zhaopin recruiter session:

1. Open or reuse the recruiter browser profile.
2. Trigger a candidate search from natural language.
3. Complete login or captcha in the same window if required.
4. Continue the last search successfully.
5. Run `下一页` and verify the second page differs from the first.
6. Confirm the rendered markdown includes original Zhaopin detail links and any extracted site-specific columns.

## Implementation Boundary

This change should deliver a full usable Zhaopin adapter, not just a placeholder package. That includes MCP tools, runtime config, docs, and tests. It should not turn into a broad recruiting-system refactor.
