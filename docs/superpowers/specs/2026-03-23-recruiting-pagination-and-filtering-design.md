# Recruiting Pagination And Filtering Design

- Date: 2026-03-23
- Status: Approved in conversation
- Scope: Liepin recruiting MCP pagination, follow-up paging, and stricter candidate relevance handling

## Summary

The current Liepin MCP has three behavioral gaps:

1. `result_limit` only controls how many cards to extract from the current page; it does not aggregate across pages.
2. Follow-up requests like `再加一页` depend on the model remembering to pass `page=2`, which is unreliable.
3. Recruiter-frontend truth is currently trusted too broadly, so explicitly conflicting candidates can leak into the final list.

This design adds server-side multi-page aggregation, a dedicated next-page tool, and a stricter relevance policy that still tolerates missing recruiter fields.

## Goals

- Support natural-language requests for large batches such as `给我 100 人`.
- Support stable follow-up pagination through a dedicated MCP tool instead of model-inferred page math.
- Keep candidates that are recruiter-visible but only missing structured fields.
- Remove candidates that explicitly contradict user constraints such as city, degree, experience, or title.
- Keep changes isolated to the recruiting assistant and Liepin MCP adapter.

## Non-goals

- No redesign of CoPaw core architecture.
- No new cross-site behavior.
- No automatic relaxation of user constraints.
- No resume-detail scraping beyond existing list behavior.

## Design

### 1. Multi-page aggregation

`liepin_search_candidates` keeps `page` as the starting page. When `result_limit` exceeds the current-page capacity, the service keeps advancing pages and merges candidates until:

- enough candidates are collected
- there is no next page
- the site total is exhausted
- or a safety page cap is reached

Deduplication uses the existing candidate identity key.

### 2. Dedicated next-page tool

Add `liepin_next_page` to the MCP server. It reuses the last successful normalized query, increments the page, and returns the next page without requiring the model to rebuild the whole query or remember page numbers.

This tool becomes the preferred action for follow-up requests like:

- `下一页`
- `再加一页`
- `继续翻`

### 3. Explicit-conflict filtering

The recruiter page remains the source list, but final presentation must still honor explicit user intent.

Policy:

- If a structured field is missing on a candidate card, keep the card.
- If the field is present and explicitly conflicts with the query, drop the card.
- Title intent is always enforced against available title/headline fields.

This keeps recruiter-visible but partially sparse cards, while removing obvious mismatches such as `Java / 南京 / 9年 / 本科` for `上海 Python算法工程师 6年以上 本科`.

## Files

- Modify `src/copaw/agents/skills/recruiting_assistant/liepin_mcp/service.py`
- Modify `src/copaw/agents/skills/recruiting_assistant/liepin_mcp/server.py`
- Modify `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Modify `src/copaw/agents/skills/recruiting_assistant/references/setup.md`
- Modify `tests/unit/skills/recruiting_assistant/test_liepin_service.py`
- Modify `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`

## Verification

- Unit-test multi-page aggregation and next-page behavior.
- Unit-test explicit-conflict filtering versus missing-field tolerance.
- Re-run `tests/unit/skills/recruiting_assistant`.
- Re-sync built-in skills into `.copaw-dev/workspaces/default`.
