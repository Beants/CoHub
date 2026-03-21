# Recruiting Assistant Design

- Date: 2026-03-21
- Status: Approved in conversation, pending implementation planning
- Scope: V1 recruiting assistant for CoPaw, starting with Liepin

## 1. Summary

V1 builds a recruiting assistant inside CoPaw for HR users. The user interacts in natural language, the assistant searches configured recruiting sites, returns a candidate summary list in CoPaw, and each result links back to the original recruiting site detail page.

The first site is Liepin. The architecture must support adding more recruiting sites later through reusable site adapters without changing the upper-layer user experience.

V1 explicitly does not execute recruiting-site actions such as favorite, note, or message. It only supports:

- natural-language search
- natural-language incremental refinement based on the last search
- candidate summary generation
- direct open to the original site detail page

## 2. Problem

HR users should not need to manually repeat the same search process on each recruiting site. They should be able to describe the search intent once in CoPaw, get a concise summary list, and continue refining the query through natural language until the result set is useful.

The design must also handle:

- recruiting-site login state and human verification
- per-site browser/session persistence
- site-specific field mapping and DOM extraction
- future expansion to multiple sites
- minimal change to existing CoPaw core architecture

## 3. Goals

- Provide one unified recruiting search entry in CoPaw.
- Search all user-enabled recruiting sites by default.
- Keep the user in natural-language interaction mode for both first search and follow-up refinements.
- Show concise candidate summaries in CoPaw with clickable links to original site detail pages.
- Reuse existing CoPaw environment-variable configuration UX.
- Keep recruiting-site logic isolated from CoPaw core.
- Support a separate small model for match-reason generation, independent from the main CoPaw model.

## 4. Non-goals

- No direct execution of favorite, note, or greeting actions in V1.
- No cross-site deduplication in V1.
- No cross-site reranking in V1.
- No permanent storage of recruiting-site credentials.
- No deep resume/body extraction in V1 beyond list-level and preview-level data.
- No custom CoPaw front-end card protocol in V1; standard markdown link rendering is sufficient.

## 5. Key Decisions

### 5.1 Platform / Skill / MCP boundary

CoPaw platform responsibilities:

- chat UI and session management
- markdown rendering and link opening
- environment-variable management UI
- model/provider management
- MCP registration and lifecycle management

`recruiting_assistant` skill responsibilities:

- understand user natural-language recruiting requests
- classify a turn as new search, incremental refinement, continue, or reset
- normalize user intent into a unified search query
- keep search context within the current conversation
- read recruiting-related configuration from CoPaw environment variables
- invoke one or more site MCPs
- merge site results into a user-facing response
- call a separate small model to generate candidate match reasons

Site MCP responsibilities, using `liepin-mcp` as the first adapter:

- maintain site-specific browser/session state
- verify login state
- ask for human intervention when login, CAPTCHA, or site verification is required
- map normalized search fields to site-specific filters
- execute site search and pagination
- extract candidate list data
- return site-native detail links and status information

### 5.2 Why MCP instead of generic browser tool only

The recruiting workflow is strongly site-specific and depends on persistent login/session behavior. A site MCP isolates this complexity and makes multi-site expansion manageable. CoPaw already supports MCP clients, so this approach fits the current architecture without pushing recruiting-site logic into the platform core.

### 5.3 One unified search entry

The user sees one recruiting assistant entry in CoPaw. By default, the assistant searches all enabled sites configured in the left-side environment-variable page. The user can still override this in natural language, for example "only search Liepin".

### 5.4 Natural-language incremental refinement

Follow-up user turns are treated as incremental modifications to the last search unless the user explicitly resets or starts a new search.

Examples:

- "Only Shanghai"
- "Change experience to 5 years+"
- "Open page 2"
- "Prefer AI platform background"
- "Search again for agent engineers"

The assistant should explain what changed in each follow-up run.

## 6. User Experience

### 6.1 V1 happy path

1. User asks in natural language for candidates.
2. Recruiting assistant normalizes the request.
3. Assistant loads enabled sites and behavior settings from environment variables.
4. Assistant calls each enabled site MCP in parallel.
5. Each site MCP reuses its local browser profile/session, verifies login, and performs the search.
6. Assistant optionally calls the match-reason small model for each candidate summary.
7. CoPaw returns a markdown-based candidate summary list.
8. User clicks a result to open the original site detail page.
9. User refines the search in natural language, and the assistant reruns with the updated query.

### 6.2 V1 response shape in CoPaw

Each candidate item should include:

- source site
- display name, possibly masked if the site masks it
- headline summary such as role / city / years / education
- 2 to 4 short match reasons, when available
- direct detail link back to the original recruiting site

Example:

```md
1. 张先生 | Agent开发 | 上海 | 6年 | 本科 | 猎聘
   命中点：现居上海；6年研发经验；岗位关键词命中；最近经历偏 AI 平台
   [打开猎聘详情](https://example.com/candidate/123)
```

### 6.3 V1 out-of-scope actions

If the user asks to favorite, note, or greet, the assistant should explain that V1 only supports search and open-detail actions.

## 7. Configuration

All recruiting-assistant product configuration in V1 should live in CoPaw's existing left-side environment-variable page. The MCP page should only be used to mount the MCP service itself, not as the main product configuration entry.

### 7.1 Recommended environment variables

Core recruiting configuration:

- `RECRUITING_ENABLED_SITES=liepin,boss,zhaopin`
- `RECRUITING_SITE_FAILURE_MODE=partial_success`
- `RECRUITING_DEFAULT_PAGE=1`
- `RECRUITING_DEFAULT_RESULT_LIMIT=20`

Match-reason small model configuration:

- `RECRUITING_MATCH_MODEL_PROVIDER`
- `RECRUITING_MATCH_MODEL`
- `RECRUITING_MATCH_API_KEY`
- `RECRUITING_MATCH_BASE_URL`
- `RECRUITING_MATCH_TIMEOUT_MS`

Per-site browser/session configuration:

- `LIEPIN_PROFILE_DIR`
- future examples: `BOSS_PROFILE_DIR`, `ZHAOPIN_PROFILE_DIR`

### 7.2 Failure mode options

Supported values:

- `partial_success`
- `strict_all_sites`

Default:

- `partial_success`

Behavior:

- `partial_success`: return successful site results and clearly mark failed sites
- `strict_all_sites`: fail the whole search when any enabled site fails

## 8. Architecture

### 8.1 Components

`recruiting_assistant` skill:

- query intent parser
- search-context manager
- site dispatcher
- result merger
- match-reason generator
- response renderer

`liepin-mcp`:

- profile/session manager
- login-state checker
- human-verification notifier
- field mapper
- page executor
- candidate extractor
- result serializer

Small match-reason model client:

- invoked by the recruiting assistant, not by site MCPs
- shared across all recruiting sites
- only accepts structured candidate data and structured query context

### 8.2 Session and browser strategy

V1 should not attempt to attach to an arbitrary already-open browser window. Instead, each site MCP should use a configurable browser profile directory.

Recommended behavior:

- default to a site-specific dedicated profile directory
- allow advanced users to point the profile dir to an existing browser profile if they explicitly want to reuse that session
- never store site account passwords
- rely on local browser session/cookies for persistence

This preserves login state across runs without making the platform depend on hijacking a live browser window.

## 9. Data Contracts

### 9.1 Normalized search query

Suggested normalized query shape:

```json
{
  "sites": [],
  "keyword": "",
  "position": "",
  "company": "",
  "current_city": "",
  "expected_city": "",
  "experience": "",
  "education": "",
  "current_industry": "",
  "expected_industry": "",
  "current_function": "",
  "expected_function": "",
  "current_salary": "",
  "expected_salary": "",
  "school": "",
  "major": "",
  "active_status": "",
  "job_status": "",
  "management_experience": "",
  "page": 1,
  "page_size_limit": 20
}
```

Rules:

- only populate fields clearly implied by the user
- do not invent filters the user did not ask for
- let each site adapter ignore unsupported fields and report `ignored_filters`

### 9.2 Candidate summary schema

Suggested unified candidate summary:

```json
{
  "site": "liepin",
  "candidate_id": "site-native-id-or-handle",
  "display_name": "张先生",
  "headline": "Agent开发 / 上海 / 6年 / 本科",
  "city": "上海",
  "years_experience": "6年",
  "education": "本科",
  "current_company": "",
  "current_title": "",
  "expected_title": "",
  "expected_salary": "",
  "highlights": [],
  "detail_url": "https://...",
  "page": 1,
  "rank": 3,
  "site_status": "ok"
}
```

### 9.3 Site result envelope

Suggested site response:

```json
{
  "site": "liepin",
  "status": "ok",
  "page": 1,
  "total": 139,
  "ignored_filters": [],
  "candidates": []
}
```

Possible `status` values:

- `ok`
- `not_logged_in`
- `captcha_required`
- `rate_limited`
- `site_layout_changed`
- `unsupported_filter`
- `empty_result`
- `internal_error`

## 10. Match-reason generation

V1 match reasons should be generated by a separate small model, not by the main CoPaw model and not by rule-based templates.

Input:

- normalized user query
- one candidate's structured fields
- source site label

Output:

- 2 to 4 short match reasons
- 1 short overall note, optional

Constraints:

- only summarize evidence present in the input fields
- do not hallucinate unavailable skills, projects, or achievements
- return deterministic, short, schema-constrained output

Fallback behavior:

- if the match-reason model is unavailable or times out, return the candidate summary without match reasons
- do not silently fall back to the main CoPaw model

V1 should prioritize list-level and preview-level evidence. Deep detail-page reasoning is deferred to a later version.

## 11. Multi-site behavior

### 11.1 Enabled sites

By default, search all enabled sites defined in `RECRUITING_ENABLED_SITES`.

If the user explicitly narrows the scope in natural language, the assistant should override the default for that request, for example:

- "Only search Liepin"
- "Do not search Boss today"

### 11.2 Merge strategy

V1 should keep the merge logic conservative:

- do not force cross-site deduplication
- do not rerank candidates across sites
- preserve site-local ordering
- group or clearly label results by site

Reason:

- recruiting sites often mask names and expose incomplete fields, so V1 cross-site dedupe is high risk

## 12. Paging and refinement behavior

Default behavior:

- search page 1 on each enabled site

Override behavior:

- if the user asks for another page, apply that page to all active sites for that run
- if the user asks for a top-N view, apply it as a CoPaw display limit instead of assuming site-native page size behavior

The assistant should remember the last search context during the conversation, including:

- normalized query
- enabled/overridden site scope
- page
- result limit
- user refinement history

Turn classification:

- new search
- refinement of prior search
- continue after human verification
- explicit reset

## 13. Human verification and failure handling

Human intervention is a first-class state in this design.

When a site MCP detects that the user must act, it should return a structured status instead of failing silently.

Human-intervention cases:

- login required
- CAPTCHA required
- additional site verification required
- site forces a blocking prompt that automation cannot safely complete

User-facing behavior:

- CoPaw clearly states which site needs action
- CoPaw preserves the current recruiting search context
- after the user completes the action, they can reply with "continue" or give a refinement instruction

### 13.1 Security posture

- do not ask for or store recruiting-site passwords
- rely on browser session/profile reuse
- keep long-lived credentials out of product logic

## 14. Telemetry and product feedback data

The user explicitly requested record-keeping for future product suggestions. V1 should record operational data, but remain conservative with sensitive resume content.

Recommended logs:

- original user recruiting request
- normalized query
- refinement history
- enabled sites for the run
- per-site latency
- per-site result counts
- ignored filters
- site status and failure reasons
- match-reason generation latency and status

Recommended result metadata:

- returned candidate IDs or stable handles
- site
- page
- rank
- detail link emitted or not emitted

Do not store by default:

- full resume body
- entire raw HTML page dumps
- recruiting-site account credentials

If deep debugging is needed later, add an explicit debug flag for short-lived snapshots.

## 15. Testing strategy

### 15.1 Unit tests

- natural-language search normalization
- refinement merge logic
- turn classification
- failure-mode selection
- match-reason response validation

### 15.2 MCP contract tests

- each site MCP must return the agreed result envelope
- error states must be structured and stable

### 15.3 Extraction regression tests

- saved Liepin list-page fixtures
- saved preview-state fixtures
- assertions for key field extraction stability

### 15.4 Manual end-to-end tests

- logged-in search succeeds
- candidate summary list renders in CoPaw
- detail link opens original site page
- user can refine the previous search in natural language
- human verification can pause and resume the same search context

## 16. Rollout sequence

Recommended implementation order:

1. normalized search-query and search-context logic in the recruiting assistant
2. `liepin-mcp` search and extraction flow with persistent profile support
3. markdown summary response rendering with direct detail links
4. separate small-model match-reason generation
5. telemetry and regression tests

## 17. Future versions

Likely V2 directions:

- detail-page-based richer match reasons
- favorite / note / greet actions
- cross-site dedupe
- cross-site reranking
- support for Boss and Zhaopin adapters
- optional recruiter-defined JD templates for stronger matching guidance

## 18. Final decision summary

V1 should be implemented as:

- one CoPaw recruiting assistant entry
- one unified natural-language search experience
- one shared match-reason small-model configuration
- one site MCP adapter per recruiting site
- Liepin first
- summary list plus open-detail links only
- environment-variable-based product configuration through the existing left-side CoPaw settings page
