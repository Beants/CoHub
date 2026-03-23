# Zhaopin MCP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full Zhaopin recruiter candidate-search MCP adapter to `recruiting_assistant`, including browser preparation, candidate search, pagination, continuation after manual verification, local setup wiring, docs, and unit tests.

**Architecture:** Follow the current BOSS adapter shape instead of cloning all of Liepin's site-specific logic. Keep all Zhaopin behavior inside a new `zhaopin_mcp` package, while reusing the shared recruiting query/result models and markdown renderer. Wire the new adapter into config, skill docs, example MCP config, and the local recruiting setup script without refactoring CoPaw core.

**Tech Stack:** Python, Pydantic, FastMCP, Playwright persistent browser sessions, pytest, shell-script string checks for local setup wiring.

---

## Chunk 1: Shared Wiring And Local Setup

### Task 1: Add Zhaopin runtime config fields

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/config.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
config = load_recruiting_config(
    {
        "RECRUITING_ENABLED_SITES": " liepin , zhaopin , liepin ",
        "ZHAOPIN_PROFILE_DIR": "/tmp/zhaopin-profile",
        "ZHAOPIN_DEBUG_DUMP_DIR": "/tmp/zhaopin-debug",
    },
)

assert config.enabled_sites == ["liepin", "zhaopin"]
assert config.zhaopin_profile_dir == "/tmp/zhaopin-profile"
assert config.zhaopin_debug_dump_dir == "/tmp/zhaopin-debug"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config.py -q`
Expected: FAIL because `RecruitingRuntimeConfig` does not define Zhaopin config fields yet.

- [ ] **Step 3: Write minimal implementation**

```python
class RecruitingRuntimeConfig(BaseModel):
    zhaopin_profile_dir: str | None = None
    zhaopin_debug_dump_dir: str | None = None
```

Also parse:

```python
zhaopin_profile_dir=(
    str(source.get("ZHAOPIN_PROFILE_DIR", "")).strip() or None
),
zhaopin_debug_dump_dir=(
    str(source.get("ZHAOPIN_DEBUG_DUMP_DIR", "")).strip() or None
),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_config.py src/copaw/agents/skills/recruiting_assistant/config.py
git commit -m "feat: add zhaopin recruiting runtime config"
```

### Task 2: Wire Zhaopin docs, skill instructions, and local setup script

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/setup.md`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json`
- Modify: `scripts/setup_recruiting_assistant_local.sh`
- Modify: `scripts/README.md`
- Modify: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`
- Create: `tests/unit/scripts/test_setup_recruiting_assistant_local.py`

- [ ] **Step 1: Write the failing tests**

```python
content = (Path(skill.path) / "SKILL.md").read_text(encoding="utf-8")

assert "zhaopin_prepare_browser" in content
assert "zhaopin_search_candidates" in content
assert "zhaopin_next_page" in content
assert "zhaopin_continue_last_search" in content
```

```python
script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

assert "ZHAOPIN_PROFILE_DIR" in script_text
assert "agent_config.mcp.clients['zhaopin']" in script_text
assert "copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server" in script_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_skill_bundle.py tests/unit/scripts/test_setup_recruiting_assistant_local.py -q`
Expected: FAIL because the skill bundle and local setup script do not mention Zhaopin yet.

- [ ] **Step 3: Write minimal implementation**

Update the skill instructions to add the Zhaopin workflow:

```markdown
- for Zhaopin, always use the Zhaopin MCP tools instead of generic browser tools
- start by calling `zhaopin_prepare_browser`
- run `zhaopin_search_candidates`
- prefer `zhaopin_next_page` for `下一页` / `再加一页`
- if manual verification is needed, continue with `zhaopin_continue_last_search`
```

Update local setup wiring:

```python
agent_config.mcp.clients['zhaopin'] = MCPClientConfig(
    name='zhaopin_mcp',
    description='Zhaopin recruiting adapter for CoPaw local development',
    enabled=True,
    transport='stdio',
    command=str(repo_root / '.venv' / 'bin' / 'python'),
    args=['-m', 'copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server'],
    env={'ZHAOPIN_PROFILE_DIR': zhaopin_profile_dir},
    cwd=str(repo_root),
)
```

Also seed `ZHAOPIN_PROFILE_DIR` in env defaults and document the new MCP server in setup references and `scripts/README.md`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_skill_bundle.py tests/unit/scripts/test_setup_recruiting_assistant_local.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_skill_bundle.py tests/unit/scripts/test_setup_recruiting_assistant_local.py src/copaw/agents/skills/recruiting_assistant/SKILL.md src/copaw/agents/skills/recruiting_assistant/references/setup.md src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json scripts/setup_recruiting_assistant_local.sh scripts/README.md
git commit -m "feat: wire zhaopin recruiting docs and local setup"
```

## Chunk 2: Zhaopin MCP Skeleton And Browser Session

### Task 3: Create the Zhaopin MCP package skeleton

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/models.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/server.py`
- Create: `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`

- [ ] **Step 1: Write the failing test**

```python
from copaw.agents.skills.recruiting_assistant.zhaopin_mcp import server

assert callable(server.zhaopin_status)
assert callable(server.zhaopin_prepare_browser)
assert callable(server.zhaopin_search_candidates)
assert callable(server.zhaopin_next_page)
assert callable(server.zhaopin_continue_last_search)
assert callable(server.zhaopin_close_browser)
```

```python
service = ZhaopinService()
assert await service.close_browser() == {"site": "zhaopin", "closed": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_service.py -q`
Expected: FAIL because the `zhaopin_mcp` package does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create the package and mirror the standard recruiting tool surface:

```python
@mcp.tool(name="zhaopin_status")
async def zhaopin_status() -> dict[str, Any]:
    return await _service.status()
```

Provide a minimal `ZhaopinService` with `close_browser()` and placeholder method signatures for the remaining operations.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_zhaopin_service.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/__init__.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/models.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/server.py
git commit -m "feat: scaffold zhaopin mcp adapter"
```

### Task 4: Implement browser launch, status detection, entry-page recovery, and paging helpers

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/session.py`
- Create: `tests/unit/skills/recruiting_assistant/test_zhaopin_session.py`

- [ ] **Step 1: Write the failing tests**

```python
assert (
    detect_zhaopin_status(
        "https://rd6.zhaopin.com/login",
        "请先登录后继续",
    )
    == "not_logged_in"
)
assert (
    detect_zhaopin_status(
        "https://rd6.zhaopin.com/talent/search",
        "请完成滑动验证",
    )
    == "captcha_required"
)
```

```python
page = await session.ensure_entry_page(fake_page)
assert fake_page.goto_calls == ["https://rd6.zhaopin.com/"]
```

```python
status = await session.search_phrase(page, "Python算法工程师", 2)
assert status == "ok"
assert page_target_calls == [2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_session.py -q`
Expected: FAIL because the session helpers and selectors do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
class ZhaopinBrowserSession:
    async def ensure_started(self) -> Any: ...
    async def check_status(self, page: Any | None = None) -> SiteStatus: ...
    async def ensure_entry_page(self, page: Any | None = None) -> Any: ...
    async def search_phrase(self, page: Any, phrase: str, page_number: int) -> SiteStatus: ...
```

Include:

- `resolve_browser_launch_config()` matching the existing BOSS adapter pattern
- Zhaopin recruiter-host detection
- best-effort visible search-input lookup
- stable `_goto_page_number()` support for page 2+

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_session.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_zhaopin_session.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/session.py
git commit -m "feat: add zhaopin browser session helpers"
```

## Chunk 3: Candidate Extraction And Search Service

### Task 5: Implement Zhaopin candidate extractors

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/extractors.py`
- Create: `tests/unit/skills/recruiting_assistant/test_zhaopin_extractors.py`

- [ ] **Step 1: Write the failing tests**

```python
summary = parse_candidate_card(
    {
        "candidate_id": "zp-1",
        "name": "张先生",
        "headline": "算法工程师 / 上海 / 8年 / 本科",
        "city": "上海",
        "experience": "8年",
        "education": "本科",
        "detail_url": "https://rd6.zhaopin.com/resume/1",
        "extra_attributes": {"最近活跃": "今日活跃"},
    },
    site="zhaopin",
    page=1,
    rank=1,
)

assert summary is not None
assert summary.site == "zhaopin"
assert summary.extra_attributes == {"最近活跃": "今日活跃"}
```

```python
assert parse_candidate_card({"name": "张先生"}, site="zhaopin", page=1, rank=1) is None
assert _coerce_positive_int("共278人") == 278
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_extractors.py -q`
Expected: FAIL because the extractor module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement the same extraction boundary used by BOSS:

```python
def parse_candidate_card(raw_card: dict[str, Any], *, site: str, page: int, rank: int) -> CandidateSummary | None:
    ...

async def extract_candidates_from_page(page: Any, page_number: int, max_cards: int) -> list[CandidateSummary]:
    ...

async def extract_total_from_page(page: Any) -> int:
    ...
```

Use Zhaopin-specific DOM selectors inside the evaluate script, but keep output normalized to shared fields plus `extra_attributes`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_extractors.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_zhaopin_extractors.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/extractors.py
git commit -m "feat: add zhaopin candidate extractors"
```

### Task 6: Implement search, browser-prepare, and manual-verification envelopes

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/server.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`

- [ ] **Step 1: Write the failing tests**

```python
result = await service.prepare_browser()

assert result["status"] == "captcha_required"
assert "zhaopin_continue_last_search" in result["message"]
assert result["avoid_reopen_browser"] is True
assert result["stop_current_turn"] is True
```

```python
result = await service.search_candidates({"keyword": "Python算法工程师"})

assert result.site == "zhaopin"
assert result.status == "not_logged_in"
assert result.continue_tool == "zhaopin_continue_last_search"
```

```python
result = await service.search_candidates({"title": "Python算法工程师"}, page=2, result_limit=5)

assert result.status == "ok"
assert result.page == 2
assert result.total == 28
assert "### 智联招聘" in result.summary_markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_service.py -q`
Expected: FAIL because the service does not orchestrate search, summary rendering, or manual-verification envelopes yet.

- [ ] **Step 3: Write minimal implementation**

Implement the BOSS-shaped service flow:

```python
class ZhaopinService:
    async def status(self) -> dict[str, Any]: ...
    async def prepare_browser(self) -> dict[str, Any]: ...
    async def search_candidates(
        self,
        query_input: Mapping[str, Any] | NormalizedSearchQuery | str,
        *,
        page: int | None = None,
        result_limit: int | None = None,
    ) -> SiteSearchResult: ...
```

Requirements:

- build the primary phrase from `position`, then `keyword`, then `company`
- set `_last_query` before attempting the browser flow
- return `unsupported_filter` when no usable phrase exists
- call the extractors only after `search_phrase()` returns `ok`
- populate `summary_markdown` with `render_search_results()`
- have `server.py` return JSON-safe dicts from search-like tools

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_zhaopin_service.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/server.py
git commit -m "feat: add zhaopin search service"
```

### Task 7: Implement `zhaopin_next_page` and `zhaopin_continue_last_search`

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py`
- Modify: `tests/unit/skills/recruiting_assistant/test_zhaopin_service.py`

- [ ] **Step 1: Write the failing tests**

```python
service._last_successful_query = NormalizedSearchQuery(keyword="Python算法工程师", page=1, page_size_limit=20)
result = await service.next_page(result_limit=10)

assert result.page == 2
```

```python
service._last_query = NormalizedSearchQuery(keyword="Python算法工程师", page=1, page_size_limit=20)
result = await service.continue_last_search()

assert result.status == "ok"
```

```python
result = await service.continue_last_search()
assert result.status == "internal_error"
assert "当前没有可继续的上一次搜索" in result.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_service.py -q`
Expected: FAIL because pagination and continuation state handling are incomplete.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
async def next_page(self, *, result_limit: int | None = None) -> SiteSearchResult:
    ...

async def continue_last_search(self) -> SiteSearchResult:
    ...
```

Rules:

- `next_page()` depends on `_last_successful_query`
- `continue_last_search()` depends on `_last_query`
- both methods should route back through `search_candidates()` after updating state
- if status remains `not_logged_in` or `captcha_required`, return that status again without reopening the browser flow

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_zhaopin_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/skills/recruiting_assistant/test_zhaopin_service.py src/copaw/agents/skills/recruiting_assistant/zhaopin_mcp/service.py
git commit -m "feat: add zhaopin pagination and continuation"
```

## Chunk 4: Regression, Sync, And Manual Verification

### Task 8: Run focused regression and sync the built-in skill

**Files:**
- Modify: none

- [ ] **Step 1: Run the focused Zhaopin test set**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config.py tests/unit/skills/recruiting_assistant/test_skill_bundle.py tests/unit/skills/recruiting_assistant/test_zhaopin_session.py tests/unit/skills/recruiting_assistant/test_zhaopin_extractors.py tests/unit/skills/recruiting_assistant/test_zhaopin_service.py tests/unit/scripts/test_setup_recruiting_assistant_local.py -q`
Expected: PASS.

- [ ] **Step 2: Run the recruiting assistant regression suite**

Run: `uv run pytest tests/unit/skills/recruiting_assistant -q`
Expected: PASS.

- [ ] **Step 3: Sync built-in skills into the repo-local workspace**

Run:

```bash
uv run python -c "from pathlib import Path; from copaw.agents.skills_manager import sync_skills_to_working_dir; workspace=Path('.copaw-dev/workspaces/default'); synced, skipped = sync_skills_to_working_dir(workspace, force=True); print({'synced': synced, 'skipped': skipped})"
```

Expected: sync summary showing the recruiting assistant skill was refreshed.

- [ ] **Step 4: Commit**

```bash
git add src/copaw/agents/skills/recruiting_assistant/ tests/unit/skills/recruiting_assistant/ tests/unit/scripts/test_setup_recruiting_assistant_local.py scripts/setup_recruiting_assistant_local.sh scripts/README.md
git commit -m "feat: complete zhaopin recruiting adapter"
```

- [ ] **Step 5: Manual verification checkpoint**

Using a logged-in Zhaopin recruiter browser session:

```text
1. Call zhaopin_prepare_browser and confirm the recruiter tab opens or reuses the existing window.
2. Search a natural-language query and confirm candidate rows render under "智联招聘".
3. If login or captcha appears, complete it in the same window and call zhaopin_continue_last_search.
4. Ask for 下一页 and confirm zhaopin_next_page returns a different page.
5. Open one returned detail URL and confirm it lands on the original Zhaopin candidate page.
```
