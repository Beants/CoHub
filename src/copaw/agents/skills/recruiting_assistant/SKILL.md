---
name: recruiting_assistant
description: "Use this skill when the user wants to search candidates from recruiting sites through natural-language recruiting requests, refine the search iteratively, summarize result lists, or open the original recruiting-site detail pages. The first supported site is Liepin, and the skill is designed to expand to more recruiting sites through separate MCP adapters."
metadata: { "builtin_skill_version": "1.0" }
---

# Recruiting Assistant

Use this skill for HR recruiting workflows inside CoPaw.

## Scope

- understand natural-language recruiting requests
- normalize search intent into a shared query contract
- dispatch searches to enabled recruiting-site MCP adapters
- summarize candidate list results in CoPaw
- provide direct links back to the original recruiting-site detail pages

## Required tool workflow

- for BOSS, always use the BOSS MCP tools instead of generic browser tools
- start by calling `boss_prepare_browser` to open or reuse the persistent BOSS browser profile
- run `boss_search_candidates` with the normalized search query, page, and result limit
- if the user asks for `下一页`、`再加一页`、`继续翻` or similar in a BOSS flow, prefer `boss_next_page`
- if the site reports login, CAPTCHA, or other manual verification, ask the user to finish that step in the opened BOSS browser and then call `boss_continue_last_search`
- when the BOSS MCP result says to stay in the same window, do not call `browser_use` and do not call `boss_prepare_browser` again unless the user explicitly says the original BOSS window was closed
- for Zhaopin, always use the Zhaopin MCP tools instead of generic browser tools
- start by calling `zhaopin_prepare_browser` to open or reuse the persistent Zhaopin browser profile
- run `zhaopin_search_candidates` with the normalized search query, page, and result limit
- if the user asks for `下一页`、`再加一页`、`继续翻` or similar in a Zhaopin flow, prefer `zhaopin_next_page`
- if the site reports login, CAPTCHA, or other manual verification, ask the user to finish that step in the opened Zhaopin browser and then call `zhaopin_continue_last_search`
- when the Zhaopin MCP result says to stay in the same window, do not call `browser_use` and do not call `zhaopin_prepare_browser` again unless the user explicitly says the original Zhaopin window was closed
- for Liepin, always use the Liepin MCP tools instead of generic browser tools
- start by calling `liepin_prepare_browser` to open or reuse the persistent Liepin browser profile
- run `liepin_search_candidates` with the normalized search query, page, and result limit
- if the user asks for `下一页`、`再加一页`、`继续翻` or similar, prefer `liepin_next_page` instead of rebuilding the query and guessing the next page number
- if the site reports login, CAPTCHA, or other manual verification, ask the user to finish that step in the opened Liepin browser and then call `liepin_continue_last_search`
- after the user says verification is complete, call `liepin_continue_last_search` first
- if `liepin_continue_last_search` still returns `captcha_required` or `not_logged_in`, stop in that turn and ask the user to continue in the same existing Liepin window; do not reopen the flow
- if a Liepin MCP result includes `stop_current_turn=true`, do not call `liepin_status`, `liepin_prepare_browser`, `browser_use`, or any other Liepin tool again in that same turn
- if the Liepin MCP result status is `site_layout_changed`, never switch to `browser_use`; keep the user in the same logged-in Liepin window, report the recruiter-page compatibility issue, and stop in that turn
- if the Liepin MCP result status is `extraction_unreliable`, never switch to `browser_use`; report that the recruiter candidate list was extracted unreliably, treat the run as failed, and stop in that turn
- when the MCP result says to stay in the same window, do not call `browser_use` and do not call `liepin_prepare_browser` again unless the user explicitly says the original Liepin window was closed
- if a recruiting MCP result includes `summary_markdown`, use that summary first in the user-facing reply and do not rewrite it into tables
- use candidate detail URLs returned by the MCP result as the links shown in CoPaw
- do not use `browser_use` for recruiting-site login, search, pagination, or session reuse unless the user explicitly asks for a separate debugging session outside the recruiting MCP flow
- 不要再次调用 `liepin_prepare_browser` 来重复打开验证流程，除非用户明确说原来的猎聘窗口已经关闭

## Query normalization rules

- follow-up turns are refinements by default; inherit the previous successful title scope unless the user explicitly replaces it
- do not silently broaden a specific title into a generic parent title
- example: `HR产品经理` must not be rewritten to `产品经理` unless the user clearly asks to broaden the search
- when the user says `现在在青岛` or similar, populate `current_city`
- when the user says `能来青岛`、`期望青岛` or similar, populate `expected_city`
- when the user says `能来青岛或者现在在青岛都行`, populate both `expected_city=青岛` and `current_city=青岛`
- prefer recruiter frontend truth: if Liepin recruiter page already shows the candidate list after filters are applied, do not invent stricter local reinterpretations in the user-facing reply
- if the user asks for `第一页`, keep `page=1` unless they explicitly request another page
- if the user asks for a large batch such as `100人`, pass `result_limit=100`; the MCP should accumulate across pages until it fills the batch or exhausts the search

## V1 constraints

- V1 supports search, iterative refinement, and open-detail only
- V1 does not favorite, greet, or add notes on recruiting sites
- V1 currently supports Liepin, BOSS, and Zhaopin, and can expand later through additional site adapters

## References

- `references/setup.md`
- `references/query-contract.md`
- `references/mcp-config.example.json`
- `references/manual-verification.md`
