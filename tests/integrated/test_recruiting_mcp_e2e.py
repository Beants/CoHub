# -*- coding: utf-8 -*-
"""End-to-end integration tests for Liepin and Zhaopin MCP recruiting services.

These tests require live browser sessions with valid recruiter logins.
They exercise search → next_page → summary for a realistic query
("6年Python开发工程师") and validate returned candidate link formats.

Run with:
    .venv/bin/python -m pytest tests/integrated/test_recruiting_mcp_e2e.py -v -s

Prerequisites:
    - Liepin recruiter login active in browser profile
    - Zhaopin recruiter login active in browser profile
"""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

import pytest

SEARCH_QUERY = "6年Python开发工程师"


def _validate_liepin_url(url: str) -> bool:
    """Return True if the URL looks like a valid Liepin candidate detail link."""
    parsed = urlparse(url)
    return (
        parsed.scheme in ("http", "https")
        and "liepin.com" in parsed.hostname
        and bool(parsed.path)
    )


def _validate_zhaopin_url(url: str) -> bool:
    """Return True if the URL looks like a valid Zhaopin candidate link."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.hostname or not parsed.hostname.endswith("zhaopin.com"):
        return False
    if "/resume/" in parsed.path or "/candidate/" in parsed.path:
        return True
    if parsed.path == "/app/search":
        qs = parse_qs(parsed.query)
        return bool(qs.get("resumeNumber"))
    return bool(parsed.path)


# ---------------------------------------------------------------------------
# Liepin E2E tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_liepin_search_returns_candidates() -> None:
    """Search Liepin for Python devs and verify we get real candidates."""
    from copaw.agents.skills.recruiting_assistant.liepin_mcp.service import LiepinService

    service = LiepinService()
    try:
        result = await service.search_candidates(SEARCH_QUERY)
        rd = result.model_dump(mode="json")

        if rd["status"] == "not_logged_in":
            pytest.skip("Liepin session not logged in")
        if rd["status"] == "captcha_required":
            pytest.skip("Liepin requires captcha verification")

        assert rd["status"] == "ok", f"Unexpected status: {rd['status']}"
        candidates = rd.get("candidates", [])
        assert len(candidates) > 0, "Expected at least one candidate"

        for c in candidates:
            assert c["display_name"], "Candidate name should not be empty"
            assert c["detail_url"], "Candidate detail_url should not be empty"
            assert _validate_liepin_url(c["detail_url"]), (
                f"Invalid Liepin URL: {c['detail_url']}"
            )
    finally:
        await service.close_browser()


@pytest.mark.asyncio
async def test_liepin_next_page_returns_page2() -> None:
    """After a search, next_page should return page 2 candidates."""
    from copaw.agents.skills.recruiting_assistant.liepin_mcp.service import LiepinService

    service = LiepinService()
    try:
        first = await service.search_candidates(SEARCH_QUERY)
        fd = first.model_dump(mode="json")
        if fd["status"] != "ok":
            pytest.skip(f"Liepin initial search failed: {fd['status']}")

        result = await service.next_page()
        rd = result.model_dump(mode="json")

        assert rd["status"] == "ok", f"Next page failed: {rd['status']}"
        assert rd.get("page", 1) >= 2, "Page number should be >= 2"
        candidates = rd.get("candidates", [])
        assert len(candidates) > 0, "Expected candidates on page 2"

        for c in candidates:
            assert _validate_liepin_url(c["detail_url"]), (
                f"Invalid page 2 URL: {c['detail_url']}"
            )
    finally:
        await service.close_browser()


@pytest.mark.asyncio
async def test_liepin_summary_is_valid_markdown() -> None:
    """Search result summary should be well-formed markdown with links."""
    from copaw.agents.skills.recruiting_assistant.liepin_mcp.service import LiepinService

    service = LiepinService()
    try:
        result = await service.search_candidates(SEARCH_QUERY)
        rd = result.model_dump(mode="json")
        if rd["status"] != "ok":
            pytest.skip(f"Liepin search failed: {rd['status']}")

        summary = rd.get("summary_markdown", "")
        assert summary, "Summary markdown should not be empty"

        assert "---" in summary, "Summary should contain markdown table separators"
        link_pattern = re.compile(r"\[.+?\]\(https?://.+?liepin\.com.+?\)")
        links = link_pattern.findall(summary)
        assert len(links) > 0, "Summary should contain liepin.com markdown links"
    finally:
        await service.close_browser()


# ---------------------------------------------------------------------------
# Zhaopin E2E tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zhaopin_search_returns_candidates() -> None:
    """Search Zhaopin for Python devs and verify we get real candidates."""
    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import ZhaopinService

    service = ZhaopinService()
    try:
        result = await service.search_candidates(SEARCH_QUERY)
        rd = result.model_dump(mode="json")

        if rd["status"] == "not_logged_in":
            pytest.skip("Zhaopin session not logged in")
        if rd["status"] == "captcha_required":
            pytest.skip("Zhaopin requires captcha verification")

        assert rd["status"] == "ok", f"Unexpected status: {rd['status']}"
        candidates = rd.get("candidates", [])
        assert len(candidates) > 0, "Expected at least one candidate"

        for c in candidates:
            assert c["display_name"], "Candidate name should not be empty"
            assert c["detail_url"], "Candidate detail_url should not be empty"
            assert _validate_zhaopin_url(c["detail_url"]), (
                f"Invalid Zhaopin URL: {c['detail_url']}"
            )
    finally:
        await service.close_browser()


@pytest.mark.asyncio
async def test_zhaopin_next_page_returns_page2() -> None:
    """After a search, next_page should return page 2 candidates."""
    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import ZhaopinService

    service = ZhaopinService()
    try:
        first = await service.search_candidates(SEARCH_QUERY)
        fd = first.model_dump(mode="json")
        if fd["status"] != "ok":
            pytest.skip(f"Zhaopin initial search failed: {fd['status']}")

        result = await service.next_page()
        rd = result.model_dump(mode="json")

        assert rd["status"] == "ok", f"Next page failed: {rd['status']}"
        assert rd.get("page", 1) >= 2, "Page number should be >= 2"
        candidates = rd.get("candidates", [])
        assert len(candidates) > 0, "Expected candidates on page 2"

        for c in candidates:
            assert _validate_zhaopin_url(c["detail_url"]), (
                f"Invalid page 2 URL: {c['detail_url']}"
            )
    finally:
        await service.close_browser()


@pytest.mark.asyncio
async def test_zhaopin_summary_is_valid_markdown() -> None:
    """Search result summary should be well-formed markdown with links."""
    from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.service import ZhaopinService

    service = ZhaopinService()
    try:
        result = await service.search_candidates(SEARCH_QUERY)
        rd = result.model_dump(mode="json")
        if rd["status"] != "ok":
            pytest.skip(f"Zhaopin search failed: {rd['status']}")

        summary = rd.get("summary_markdown", "")
        assert summary, "Summary markdown should not be empty"

        assert "---" in summary, "Summary should contain markdown table separators"
        link_pattern = re.compile(r"\[.+?\]\(https?://.+?zhaopin\.com.+?\)")
        links = link_pattern.findall(summary)
        assert len(links) > 0, "Summary should contain zhaopin.com markdown links"
    finally:
        await service.close_browser()
