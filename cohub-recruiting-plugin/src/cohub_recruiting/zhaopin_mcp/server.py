# -*- coding: utf-8 -*-
"""FastMCP entrypoint for Zhaopin recruiting search."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .service import ZhaopinService

mcp = FastMCP(
    name="zhaopin-mcp",
    instructions=(
        "Zhaopin recruiting adapter for CoPaw. "
        "Uses a persistent local browser profile and may require "
        "human login or captcha completion."
    ),
)
_service = ZhaopinService()


@mcp.tool(
    name="zhaopin_status",
    description="Check the current Zhaopin browser/session status.",
)
async def zhaopin_status() -> dict[str, Any]:
    """Return the current Zhaopin session state."""
    return await _service.status()


@mcp.tool(
    name="zhaopin_prepare_browser",
    description=(
        "Open Zhaopin with the configured persistent browser profile so "
        "the user can complete login or verification."
    ),
)
async def zhaopin_prepare_browser() -> dict[str, Any]:
    """Prepare the persistent Zhaopin browser session."""
    return await _service.prepare_browser()


@mcp.tool(
    name="zhaopin_search_candidates",
    description=(
        "Search Zhaopin candidates using a normalized query object or a "
        "plain keyword string."
    ),
)
async def zhaopin_search_candidates(
    query: dict[str, Any] | str,
    page: int | None = None,
    result_limit: int | None = None,
) -> dict[str, Any]:
    """Search Zhaopin candidates and return the site result envelope."""
    result = await _service.search_candidates(
        query,
        page=page,
        result_limit=result_limit,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="zhaopin_next_page",
    description=(
        "Open the next page for the last successful Zhaopin candidate search."
    ),
)
async def zhaopin_next_page(
    result_limit: int | None = None,
) -> dict[str, Any]:
    """Continue to the next page for the latest successful Zhaopin search."""
    result = await _service.next_page(result_limit=result_limit)
    return result.model_dump(mode="json")


@mcp.tool(
    name="zhaopin_continue_last_search",
    description=(
        "Resume the most recent Zhaopin search after the user finishes "
        "manual login or captcha verification."
    ),
)
async def zhaopin_continue_last_search() -> dict[str, Any]:
    """Continue the last Zhaopin search run."""
    result = await _service.continue_last_search()
    return result.model_dump(mode="json")


@mcp.tool(
    name="zhaopin_close_browser",
    description="Close the persistent Zhaopin browser session.",
)
async def zhaopin_close_browser() -> dict[str, Any]:
    """Close the persistent Zhaopin browser session."""
    return await _service.close_browser()


def main() -> None:
    """Run the Zhaopin MCP server over stdio."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
