# BOSS MCP Design

## Goal

Add a BOSS 企业版人才搜索 MCP adapter to `recruiting_assistant` without changing CoPaw core architecture.

## Scope

- Support BOSS 招聘者/企业版人才搜索 only
- Reuse the user's default Chromium browser profile and existing login session
- Support search, pagination, verification continuation, and detail links
- Return recruiter frontend-visible candidate results as-is, without local second-pass filtering
- Display as many list-page fields as can be extracted reliably

## Non-Goals

- No multi-site orchestration in this iteration
- No favorite, greet, note, or other write actions
- No detail-page deep extraction
- No generic browser flow replacing the site MCP adapter

## Architecture

### Shared Layer

- Keep `NormalizedSearchQuery`, `SiteSearchResult`, and the recruiting renderer as the cross-site contract
- Extend `CandidateSummary` with `extra_attributes: dict[str, str]`
- Renderer outputs fixed shared columns first, then appends site-specific columns discovered from `extra_attributes`

### Site Adapter Layer

Add a new sibling package:

- `src/copaw/agents/skills/recruiting_assistant/boss_mcp/models.py`
- `src/copaw/agents/skills/recruiting_assistant/boss_mcp/session.py`
- `src/copaw/agents/skills/recruiting_assistant/boss_mcp/extractors.py`
- `src/copaw/agents/skills/recruiting_assistant/boss_mcp/service.py`
- `src/copaw/agents/skills/recruiting_assistant/boss_mcp/server.py`

Responsibilities:

- `session.py`: persistent browser/profile reuse, recruiter search entry, login/captcha detection, filter clicking, pagination
- `extractors.py`: convert BOSS list cards into `CandidateSummary`
- `service.py`: site-level search orchestration and `summary_markdown`
- `server.py`: FastMCP stdio entrypoint and tools

## Tool Surface

The BOSS adapter mirrors Liepin:

- `boss_status`
- `boss_prepare_browser`
- `boss_search_candidates`
- `boss_next_page`
- `boss_continue_last_search`
- `boss_close_browser`

## Query Rules

- Reuse the existing recruiting query contract
- V1 targets these stable filters first:
  - `keyword/position`
  - `current_city` / `expected_city` when BOSS recruiter UI supports them
  - `experience`
  - `education`
  - `page`
  - `page_size_limit`
- Unsupported but parsed fields should surface via `ignored_filters`

## Result Rules

- Candidate list output must follow recruiter frontend truth
- No local post-filtering after the page is already filtered by the recruiter UI
- Candidate rows should include all stable shared fields plus extracted BOSS-specific list fields under `extra_attributes`

## Config

Add BOSS-specific runtime config and local setup wiring:

- `BOSS_PROFILE_DIR`
- optional `BOSS_DEBUG_DUMP_DIR`

Update example MCP config and local setup script to mount the new BOSS MCP server.

## Validation

### Automated

- Unit tests for:
  - shared renderer fixed + dynamic columns
  - BOSS config parsing
  - BOSS extractor normalization
  - BOSS session login/captcha/search/pagination helpers
  - BOSS service search and continuation logic

### Manual

Using a logged-in BOSS 企业版 session:

1. Search the first page from natural language
2. Complete login/captcha in the same browser window if needed
3. Continue the last search successfully
4. Run `下一页` and verify page 2 differs from page 1
5. Confirm output table includes extracted BOSS-specific columns and original detail links
