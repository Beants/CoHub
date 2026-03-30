# -*- coding: utf-8 -*-
"""FastMCP entrypoint for BOSS recruiting search."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .service import BossService

mcp = FastMCP(
    name="boss-mcp",
    instructions=(
        "BOSS recruiting adapter for CoPaw. "
        "Uses a persistent local browser profile and may require "
        "human login or captcha completion."
    ),
)
_service = BossService()


@mcp.tool(
    name="boss_status",
    description="Check the current BOSS browser/session status.",
)
async def boss_status() -> dict[str, Any]:
    """Return the current BOSS session state."""
    return await _service.status()


@mcp.tool(
    name="boss_prepare_browser",
    description=(
        "Open BOSS with the configured persistent browser profile so "
        "the user can complete login or verification."
    ),
)
async def boss_prepare_browser() -> dict[str, Any]:
    """Prepare the persistent BOSS browser session."""
    return await _service.prepare_browser()


@mcp.tool(
    name="boss_search_candidates",
    description=(
        "Search BOSS candidates using a normalized query object or a "
        "plain keyword string."
    ),
)
async def boss_search_candidates(
    query: dict[str, Any] | str,
    page: int | None = None,
    result_limit: int | None = None,
) -> dict[str, Any]:
    """Search BOSS candidates and return the site result envelope."""
    return await _service.search_candidates(
        query,
        page=page,
        result_limit=result_limit,
    )


@mcp.tool(
    name="boss_next_page",
    description="Open the next page for the last successful BOSS candidate search.",
)
async def boss_next_page(
    result_limit: int | None = None,
) -> dict[str, Any]:
    """Continue to the next page for the latest successful BOSS search."""
    return await _service.next_page(result_limit=result_limit)


@mcp.tool(
    name="boss_continue_last_search",
    description=(
        "Resume the most recent BOSS search after the user finishes "
        "manual login or captcha verification."
    ),
)
async def boss_continue_last_search() -> dict[str, Any]:
    """Continue the last BOSS search run."""
    return await _service.continue_last_search()


@mcp.tool(
    name="boss_close_browser",
    description="Close the persistent BOSS browser session.",
)
async def boss_close_browser() -> dict[str, Any]:
    """Close the persistent BOSS browser session."""
    return await _service.close_browser()


def main() -> None:
    """Run the BOSS MCP server over stdio."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
