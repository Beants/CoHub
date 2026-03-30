# Recruiting Assistant Setup

## Goal

Configure recruiting search in CoPaw without changing core architecture.

## Environment variables

Set recruiting-related variables in CoPaw's left-side environment-variable UI:

- `RECRUITING_ENABLED_SITES`
- `RECRUITING_SITE_FAILURE_MODE`
- `RECRUITING_DEFAULT_PAGE`
- `RECRUITING_DEFAULT_RESULT_LIMIT`
- `RECRUITING_MATCH_MODEL_PROVIDER`
- `RECRUITING_MATCH_MODEL`
- `RECRUITING_MATCH_API_KEY`
- `RECRUITING_MATCH_BASE_URL`
- `RECRUITING_MATCH_TIMEOUT_MS`
- `BOSS_PROFILE_DIR`
- `ZHAOPIN_PROFILE_DIR`
- `LIEPIN_PROFILE_DIR`

## V1 shape

- CoPaw platform owns chat UI, env UI, MCP lifecycle, and model configuration
- `recruiting_assistant` owns recruiting intent understanding, context, and result rendering
- site MCP adapters own browser session reuse, login checks, search execution, and candidate extraction
- recruiting-site actions must stay inside the site MCP adapters; do not replace them with generic `browser_use` flows during normal recruiting runs

## Recruiting MCP entrypoints

Mount the site MCP servers with:

```bash
uv run python -m copaw.agents.skills.recruiting_assistant.boss_mcp.server
uv run python -m copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server
uv run python -m copaw.agents.skills.recruiting_assistant.liepin_mcp.server
```

The first V1 tool set is:

- `boss_status`
- `boss_prepare_browser`
- `boss_search_candidates`
- `boss_next_page`
- `boss_continue_last_search`
- `boss_close_browser`
- `zhaopin_status`
- `zhaopin_prepare_browser`
- `zhaopin_search_candidates`
- `zhaopin_next_page`
- `zhaopin_continue_last_search`
- `zhaopin_close_browser`
- `liepin_status`
- `liepin_prepare_browser`
- `liepin_search_candidates`
- `liepin_next_page`
- `liepin_continue_last_search`
- `liepin_close_browser`
