# -*- coding: utf-8 -*-
"""FastMCP entrypoint for Liepin recruiting search."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .service import LiepinService

mcp = FastMCP(
    name="liepin-mcp",
    instructions=(
        "Liepin recruiting adapter for CoPaw. "
        "Uses a persistent local browser profile and may require "
        "human login or captcha completion."
    ),
)
_service = LiepinService()


@mcp.tool(
    name="liepin_status",
    description="Check the current Liepin browser/session status.",
)
async def liepin_status() -> dict[str, Any]:
    """Return the current Liepin session state."""
    return await _service.status()


@mcp.tool(
    name="liepin_prepare_browser",
    description=(
        "Open Liepin with the configured persistent browser profile so "
        "the user can complete login or verification."
    ),
)
async def liepin_prepare_browser() -> dict[str, Any]:
    """Prepare the persistent Liepin browser session."""
    return await _service.prepare_browser()


@mcp.tool(
    name="liepin_search_candidates",
    description=(
        "Search Liepin candidates using a normalized query object or a "
        "plain keyword string."
    ),
)
async def liepin_search_candidates(
    query: dict[str, Any] | str,
    page: int | None = None,
    result_limit: int | None = None,
) -> dict[str, Any]:
    """Search Liepin candidates and return the site result envelope."""
    result = await _service.search_candidates(
        query,
        page=page,
        result_limit=result_limit,
    )
    return result.model_dump(mode="json")


@mcp.tool(
    name="liepin_next_page",
    description=(
        "Open the next page for the last successful Liepin candidate search."
    ),
)
async def liepin_next_page(
    result_limit: int | None = None,
) -> dict[str, Any]:
    """Continue to the next page for the latest successful Liepin search."""
    result = await _service.next_page(result_limit=result_limit)
    return result.model_dump(mode="json")


@mcp.tool(
    name="liepin_continue_last_search",
    description=(
        "Resume the most recent Liepin search after the user finishes "
        "manual login or captcha verification."
    ),
)
async def liepin_continue_last_search() -> dict[str, Any]:
    """Continue the last Liepin search run."""
    result = await _service.continue_last_search()
    return result.model_dump(mode="json")


@mcp.tool(
    name="liepin_close_browser",
    description="Close the persistent Liepin browser session.",
)
async def liepin_close_browser() -> dict[str, Any]:
    """Close the persistent Liepin browser session."""
    return await _service.close_browser()


def main() -> None:
    """Run the Liepin MCP server over stdio."""
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
