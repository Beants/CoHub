# Recruiting Assistant Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a V1 recruiting assistant for CoPaw that searches Liepin through a skill-local MCP server, returns candidate summary links in CoPaw, and keeps all new logic in additive, pluggable files rather than modifying existing CoPaw core behavior.

**Architecture:** Add one new built-in skill bundle under `src/copaw/agents/skills/recruiting_assistant/`. Put deterministic helper code and the stdio `liepin-mcp` server inside that skill bundle, and use the existing CoPaw environment-variable page plus existing MCP mounting UI for configuration. Do not modify existing `src/copaw` runtime modules unless an unexpected blocker appears during execution.

**Tech Stack:** CoPaw built-in skills, FastMCP stdio server, Playwright, pytest, existing CoPaw `execute_shell_command` tool, existing CoPaw MCP client support, environment-variable storage via `envs.json`.

---

## File Structure

### New skill bundle

- Create: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Create: `src/copaw/agents/skills/recruiting_assistant/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/setup.md`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/query-contract.md`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/manual-verification.md`

### New skill-local helper code

- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/config_loader.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/match_reason_cli.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/render_candidates.py`

### New skill-local Liepin MCP server

- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/models.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/errors.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/browser_session.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/search.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/extractors.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/server.py`

### New tests and fixtures

- Create: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`
- Create: `tests/unit/skills/recruiting_assistant/test_config_loader.py`
- Create: `tests/unit/skills/recruiting_assistant/test_match_reason_cli.py`
- Create: `tests/unit/skills/recruiting_assistant/test_render_candidates.py`
- Create: `tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py`
- Create: `tests/unit/skills/recruiting_assistant/test_liepin_extractors.py`
- Create: `tests/fixtures/recruiting/liepin/list_page.html`
- Create: `tests/fixtures/recruiting/liepin/preview_panel.html`

### Files intentionally left unchanged

- Do not modify: existing files under `src/copaw/app/`
- Do not modify: existing files under `src/copaw/agents/tools/`
- Do not modify: existing files under `console/src/`
- Do not modify: existing files under `website/public/docs/` unless product docs are explicitly requested later

## Chunk 1: Skill Bundle And Deterministic Helpers

### Task 1: Create The Skill Bundle Skeleton

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Create: `src/copaw/agents/skills/recruiting_assistant/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/setup.md`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/query-contract.md`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json`
- Create: `src/copaw/agents/skills/recruiting_assistant/references/manual-verification.md`
- Test: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import frontmatter


def test_recruiting_skill_bundle_has_required_files():
    skill_dir = Path("src/copaw/agents/skills/recruiting_assistant")
    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "__init__.py").is_file()
    assert (skill_dir / "references" / "setup.md").is_file()
    assert (skill_dir / "references" / "query-contract.md").is_file()
    assert (skill_dir / "references" / "mcp-config.example.json").is_file()


def test_recruiting_skill_frontmatter_is_valid():
    post = frontmatter.loads(
        Path("src/copaw/agents/skills/recruiting_assistant/SKILL.md")
        .read_text(encoding="utf-8")
    )
    assert post["name"] == "recruiting_assistant"
    assert "Liepin" in post.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_skill_bundle.py -v`
Expected: FAIL because the skill directory and files do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```markdown
---
name: recruiting_assistant
description: Help HR search configured recruiting sites and return candidate detail links.
---

# Recruiting Assistant

- Use configured recruiting MCP tools for site searches.
- Default to enabled sites from environment variables.
- Treat follow-up recruiting instructions as refinements unless the user resets.
- Use the helper scripts in `scripts/` only for deterministic formatting and match-reason generation.
```

```json
{
  "mcpServers": {
    "liepin-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.server"
      ]
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_skill_bundle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant \
  tests/unit/skills/recruiting_assistant/test_skill_bundle.py
git commit -m "feat: scaffold recruiting assistant skill bundle"
```

### Task 2: Implement Recruiting Env Parsing

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/config_loader.py`
- Test: `tests/unit/skills/recruiting_assistant/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

```python
from copaw.agents.skills.recruiting_assistant.scripts.config_loader import (
    RecruitingConfig,
    load_recruiting_config,
)


def test_load_recruiting_config_parses_enabled_sites(monkeypatch):
    monkeypatch.setenv("RECRUITING_ENABLED_SITES", "liepin,boss")
    monkeypatch.setenv("RECRUITING_SITE_FAILURE_MODE", "partial_success")
    monkeypatch.setenv("RECRUITING_DEFAULT_PAGE", "1")
    cfg = load_recruiting_config()
    assert cfg.enabled_sites == ["liepin", "boss"]
    assert cfg.failure_mode == "partial_success"
    assert cfg.default_page == 1


def test_load_recruiting_config_parses_match_model_env(monkeypatch):
    monkeypatch.setenv("RECRUITING_MATCH_MODEL_PROVIDER", "openai")
    monkeypatch.setenv("RECRUITING_MATCH_MODEL", "gpt-4.1-mini")
    cfg = load_recruiting_config()
    assert cfg.match_model_provider == "openai"
    assert cfg.match_model == "gpt-4.1-mini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config_loader.py -v`
Expected: FAIL with import error because `config_loader.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
import os


@dataclass
class RecruitingConfig:
    enabled_sites: list[str]
    failure_mode: str
    default_page: int
    default_result_limit: int
    match_model_provider: str
    match_model: str
    match_api_key: str
    match_base_url: str
    match_timeout_ms: int


def load_recruiting_config() -> RecruitingConfig:
    enabled_sites = [
        item.strip()
        for item in os.getenv("RECRUITING_ENABLED_SITES", "liepin").split(",")
        if item.strip()
    ]
    return RecruitingConfig(
        enabled_sites=enabled_sites,
        failure_mode=os.getenv(
            "RECRUITING_SITE_FAILURE_MODE",
            "partial_success",
        ),
        default_page=int(os.getenv("RECRUITING_DEFAULT_PAGE", "1")),
        default_result_limit=int(
            os.getenv("RECRUITING_DEFAULT_RESULT_LIMIT", "20")
        ),
        match_model_provider=os.getenv(
            "RECRUITING_MATCH_MODEL_PROVIDER",
            "",
        ),
        match_model=os.getenv("RECRUITING_MATCH_MODEL", ""),
        match_api_key=os.getenv("RECRUITING_MATCH_API_KEY", ""),
        match_base_url=os.getenv("RECRUITING_MATCH_BASE_URL", ""),
        match_timeout_ms=int(
            os.getenv("RECRUITING_MATCH_TIMEOUT_MS", "8000")
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_config_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/__init__.py \
  src/copaw/agents/skills/recruiting_assistant/scripts/config_loader.py \
  tests/unit/skills/recruiting_assistant/test_config_loader.py
git commit -m "feat: add recruiting env parsing helpers"
```

### Task 3: Implement Match-Reason Helper CLI

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/match_reason_cli.py`
- Test: `tests/unit/skills/recruiting_assistant/test_match_reason_cli.py`

- [ ] **Step 1: Write the failing test**

```python
import json

from copaw.agents.skills.recruiting_assistant.scripts.match_reason_cli import (
    build_prompt_payload,
    parse_reason_response,
)


def test_build_prompt_payload_is_grounded():
    payload = build_prompt_payload(
        query={"keyword": "agent开发工程师", "current_city": "上海"},
        candidate={
            "headline": "Agent开发 / 上海 / 6年 / 本科",
            "city": "上海",
            "years_experience": "6年",
            "education": "本科",
        },
        site="liepin",
    )
    assert payload["site"] == "liepin"
    assert payload["query"]["keyword"] == "agent开发工程师"
    assert payload["candidate"]["city"] == "上海"


def test_parse_reason_response_returns_short_reasons():
    reasons = parse_reason_response(
        json.dumps(
            {
                "highlights": ["现居上海", "6年研发经验"],
                "summary": "与岗位基础条件匹配"
            },
            ensure_ascii=False,
        )
    )
    assert reasons["highlights"] == ["现居上海", "6年研发经验"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_match_reason_cli.py -v`
Expected: FAIL because `match_reason_cli.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
import json


def build_prompt_payload(*, query: dict, candidate: dict, site: str) -> dict:
    return {
        "site": site,
        "query": query,
        "candidate": candidate,
        "instructions": [
            "Only use facts present in the input.",
            "Return 2-4 short highlights.",
            "Do not invent skills or experiences.",
        ],
    }


def parse_reason_response(raw: str) -> dict:
    data = json.loads(raw)
    return {
        "highlights": data.get("highlights", [])[:4],
        "summary": data.get("summary", ""),
    }
```

- [ ] **Step 4: Extend the implementation to real CLI behavior**

```python
def main() -> int:
    # Read JSON stdin, load match-model env config, call the configured model,
    # print JSON result, and return non-zero on config or API failure.
    ...
```

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_match_reason_cli.py -v`
Expected: PASS for pure helper functions before wiring the live model call.

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/match_reason_cli.py \
  tests/unit/skills/recruiting_assistant/test_match_reason_cli.py
git commit -m "feat: add match reason helper cli"
```

### Task 4: Implement Candidate Markdown Renderer

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/render_candidates.py`
- Test: `tests/unit/skills/recruiting_assistant/test_render_candidates.py`

- [ ] **Step 1: Write the failing test**

```python
from copaw.agents.skills.recruiting_assistant.scripts.render_candidates import (
    render_candidate_markdown,
)


def test_render_candidate_markdown_includes_detail_link():
    text = render_candidate_markdown(
        candidates=[
            {
                "site": "liepin",
                "display_name": "张先生",
                "headline": "Agent开发 / 上海 / 6年 / 本科",
                "highlights": ["现居上海", "6年研发经验"],
                "detail_url": "https://example.com/candidate/123",
            }
        ]
    )
    assert "张先生" in text
    assert "[打开猎聘详情](https://example.com/candidate/123)" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_render_candidates.py -v`
Expected: FAIL because `render_candidates.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def render_candidate_markdown(*, candidates: list[dict]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(candidates, start=1):
        lines.append(
            f"{idx}. {item['display_name']} | {item['headline']} | {item['site']}"
        )
        if item.get("highlights"):
            joined = "；".join(item["highlights"])
            lines.append(f"   命中点：{joined}")
        lines.append(f"   [打开猎聘详情]({item['detail_url']})")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_render_candidates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/render_candidates.py \
  tests/unit/skills/recruiting_assistant/test_render_candidates.py
git commit -m "feat: add recruiting markdown renderer"
```

## Chunk 2: Liepin MCP Server And Extraction

### Task 5: Define Liepin MCP Contracts

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/__init__.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/models.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/errors.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/server.py`
- Test: `tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py`

- [ ] **Step 1: Write the failing test**

```python
from copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.models import (
    CandidateSummary,
    SiteSearchResult,
)


def test_site_search_result_defaults():
    result = SiteSearchResult(site="liepin", status="ok", page=1, total=0)
    assert result.site == "liepin"
    assert result.candidates == []


def test_candidate_summary_requires_detail_url():
    item = CandidateSummary(
        site="liepin",
        candidate_id="abc",
        display_name="张先生",
        headline="Agent开发 / 上海 / 6年 / 本科",
        detail_url="https://example.com/candidate/abc",
    )
    assert item.detail_url.startswith("https://")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py -v`
Expected: FAIL because the models do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from pydantic import BaseModel, Field


class CandidateSummary(BaseModel):
    site: str
    candidate_id: str
    display_name: str
    headline: str
    detail_url: str
    highlights: list[str] = Field(default_factory=list)
    city: str = ""
    years_experience: str = ""
    education: str = ""
    page: int = 1
    rank: int = 0
    site_status: str = "ok"


class SiteSearchResult(BaseModel):
    site: str
    status: str
    page: int
    total: int
    ignored_filters: list[str] = Field(default_factory=list)
    candidates: list[CandidateSummary] = Field(default_factory=list)
```

```python
from fastmcp import FastMCP

mcp = FastMCP("liepin-mcp")


@mcp.tool
def health() -> dict:
    return {"ok": True, "site": "liepin"}


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp \
  tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py
git commit -m "feat: add liepin mcp contracts"
```

### Task 6: Implement Browser Profile And Session Reuse

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/browser_session.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/server.py`
- Test: `tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py`

- [ ] **Step 1: Write the failing test**

```python
from copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.browser_session import (
    build_launch_options,
)


def test_build_launch_options_uses_profile_dir(tmp_path):
    options = build_launch_options(profile_dir=str(tmp_path))
    assert options["user_data_dir"] == str(tmp_path)
    assert options["headless"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py -v`
Expected: FAIL because `browser_session.py` and `build_launch_options` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_launch_options(*, profile_dir: str) -> dict:
    return {
        "user_data_dir": profile_dir,
        "headless": False,
        "channel": None,
    }
```

```python
@mcp.tool
def check_session() -> dict:
    # Open persistent browser context using the configured profile dir,
    # inspect whether Liepin appears logged in, and return a structured status.
    return {"site": "liepin", "status": "not_logged_in"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/browser_session.py \
  src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/server.py \
  tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py
git commit -m "feat: add liepin persistent browser session"
```

### Task 7: Implement Search Request Mapping And Result Extraction

**Files:**
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/search.py`
- Create: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/extractors.py`
- Create: `tests/fixtures/recruiting/liepin/list_page.html`
- Create: `tests/fixtures/recruiting/liepin/preview_panel.html`
- Test: `tests/unit/skills/recruiting_assistant/test_liepin_extractors.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.extractors import (
    extract_candidates_from_list_html,
)


def test_extract_candidates_from_saved_liepin_fixture():
    html = Path("tests/fixtures/recruiting/liepin/list_page.html").read_text(
        encoding="utf-8"
    )
    results = extract_candidates_from_list_html(html)
    assert results
    assert results[0].site == "liepin"
    assert results[0].headline
    assert results[0].display_name
```

- [ ] **Step 2: Add sanitized fixtures and run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_extractors.py -v`
Expected: FAIL because the extractor does not exist yet or returns no candidates.

- [ ] **Step 3: Write minimal implementation**

```python
from bs4 import BeautifulSoup


def extract_candidates_from_list_html(html: str) -> list[CandidateSummary]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[CandidateSummary] = []
    for idx, node in enumerate(_candidate_nodes(soup), start=1):
        items.append(
            CandidateSummary(
                site="liepin",
                candidate_id=_candidate_id(node, idx),
                display_name=_display_name(node),
                headline=_headline(node),
                detail_url=_detail_url(node),
                city=_city(node),
                years_experience=_years(node),
                education=_education(node),
                rank=idx,
            )
        )
    return items
```

- [ ] **Step 4: Wire search execution to extractor**

```python
def search_candidates(query: dict) -> SiteSearchResult:
    # Fill Liepin filters from the normalized query,
    # wait for list page,
    # pass HTML to the extractor,
    # return SiteSearchResult.
    ...
```

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_extractors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/search.py \
  src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/extractors.py \
  tests/fixtures/recruiting/liepin \
  tests/unit/skills/recruiting_assistant/test_liepin_extractors.py
git commit -m "feat: add liepin candidate extraction"
```

### Task 8: Expose Liepin Search Tool Through FastMCP

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/server.py`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json`
- Test: `tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py`

- [ ] **Step 1: Write the failing test**

```python
from copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.server import (
    search_candidates_tool,
)


def test_search_candidates_tool_returns_site_result(monkeypatch):
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.server.search_candidates",
        lambda query: {"site": "liepin", "status": "ok", "page": 1, "total": 1, "ignored_filters": [], "candidates": []},
    )
    result = search_candidates_tool({"keyword": "agent开发工程师", "page": 1})
    assert result["site"] == "liepin"
    assert result["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py -v`
Expected: FAIL because the search tool is not exposed yet.

- [ ] **Step 3: Write minimal implementation**

```python
@mcp.tool(name="liepin_search_candidates")
def search_candidates_tool(query: dict) -> dict:
    return search_candidates(query)
```

```json
{
  "mcpServers": {
    "liepin-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.server"
      ]
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/scripts/liepin_mcp/server.py \
  src/copaw/agents/skills/recruiting_assistant/references/mcp-config.example.json \
  tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py
git commit -m "feat: expose liepin search mcp tool"
```

## Chunk 3: Skill Wiring And Manual Verification

### Task 9: Finalize Skill Instructions Around Natural-Language Refinement

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/query-contract.md`
- Test: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_skill_instructions_cover_refinement_and_v1_scope():
    text = Path(
        "src/copaw/agents/skills/recruiting_assistant/SKILL.md"
    ).read_text(encoding="utf-8")
    assert "incremental" in text.lower()
    assert "只做搜索结果摘要和详情链接" in text
    assert "收藏" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_skill_bundle.py -v`
Expected: FAIL until the full instructions are written.

- [ ] **Step 3: Write minimal implementation**

```markdown
## Refinement Rules

- Treat follow-up recruiting turns as refinements unless the user explicitly resets.
- Reuse the last normalized query in the conversation.
- Default to all enabled recruiting sites unless the user narrows the scope.
- V1 only supports search summaries and original-site detail links.
- If asked to favorite, note, or greet, explain that the action is not supported in V1.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/skills/recruiting_assistant/test_skill_bundle.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add \
  src/copaw/agents/skills/recruiting_assistant/SKILL.md \
  src/copaw/agents/skills/recruiting_assistant/references/query-contract.md \
  tests/unit/skills/recruiting_assistant/test_skill_bundle.py
git commit -m "feat: document recruiting refinement behavior"
```

### Task 10: Run The Full Automated Test Slice

**Files:**
- Test: `tests/unit/skills/recruiting_assistant/test_skill_bundle.py`
- Test: `tests/unit/skills/recruiting_assistant/test_config_loader.py`
- Test: `tests/unit/skills/recruiting_assistant/test_match_reason_cli.py`
- Test: `tests/unit/skills/recruiting_assistant/test_render_candidates.py`
- Test: `tests/unit/skills/recruiting_assistant/test_liepin_mcp_contract.py`
- Test: `tests/unit/skills/recruiting_assistant/test_liepin_extractors.py`

- [ ] **Step 1: Run the focused unit suite**

Run:

```bash
uv run pytest tests/unit/skills/recruiting_assistant -v
```

Expected: PASS

- [ ] **Step 2: If a test fails, fix the code before proceeding**

Run the smallest failing file first, for example:

```bash
uv run pytest tests/unit/skills/recruiting_assistant/test_liepin_extractors.py -v
```

Expected: PASS after the fix.

- [ ] **Step 3: Commit**

```bash
git add src/copaw/agents/skills/recruiting_assistant tests/unit/skills/recruiting_assistant tests/fixtures/recruiting/liepin
git commit -m "test: cover recruiting assistant skill bundle"
```

### Task 11: Run Manual Liepin Verification

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/manual-verification.md`

- [ ] **Step 1: Start the Liepin MCP server locally**

Run:

```bash
uv run python -m copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.server
```

Expected: MCP server starts on stdio without import errors.

- [ ] **Step 2: Import the MCP JSON into CoPaw**

Use:

```json
{
  "mcpServers": {
    "liepin-mcp": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "copaw.agents.skills.recruiting_assistant.scripts.liepin_mcp.server"
      ]
    }
  }
}
```

Expected: the MCP appears in the CoPaw MCP page and can be enabled.

- [ ] **Step 3: Configure recruiting env vars in the existing left-side environment page**

Set at minimum:

```text
RECRUITING_ENABLED_SITES=liepin
RECRUITING_SITE_FAILURE_MODE=partial_success
LIEPIN_PROFILE_DIR=/absolute/path/to/liepin-profile
RECRUITING_MATCH_MODEL_PROVIDER=<provider>
RECRUITING_MATCH_MODEL=<small-fast-model>
```

Expected: values persist and are visible after reload.

- [ ] **Step 4: Run the manual E2E flow**

Use these transcript checks:

- "帮我找上海的 agent 开发工程师"
- "只看 5 年以上"
- "换第二页"
- "不要再搜，重新开始搜北京的"

Expected:

- search returns Liepin candidate summaries
- each candidate includes a detail link
- follow-up turns refine the previous search
- reset wording starts a new search

- [ ] **Step 5: Record outcomes in the manual verification doc**

Add:

- exact env vars used
- whether login reuse worked
- whether human verification was required
- which selectors or extractors needed adjustment

### Task 12: Final Sanity Check On Scope

**Files:**
- Modify: `src/copaw/agents/skills/recruiting_assistant/SKILL.md`
- Modify: `src/copaw/agents/skills/recruiting_assistant/references/setup.md`

- [ ] **Step 1: Confirm that V1 still excludes direct site actions**

Check the final user-facing instructions and helper docs for:

- no favorite execution
- no note execution
- no greeting execution

Expected: the bundle still only supports search summaries and detail links.

- [ ] **Step 2: Confirm that no existing CoPaw core module behavior was changed**

Run:

```bash
git diff --stat origin/main...HEAD
```

Expected: only new files under the recruiting skill, tests, fixtures, and plan/spec docs appear unless an implementation blocker forced a small additive edit.

- [ ] **Step 3: Commit final polish**

```bash
git add src/copaw/agents/skills/recruiting_assistant docs/superpowers/specs/2026-03-21-recruiting-assistant-design.md docs/superpowers/plans/2026-03-21-recruiting-assistant.md
git commit -m "docs: finalize recruiting assistant rollout notes"
```
