# -*- coding: utf-8 -*-
"""Summary extraction hook for recruiting tool outputs."""

from __future__ import annotations

import json
import logging
from typing import Any, Union

logger = logging.getLogger(__name__)

# Site names to detect in tool output JSON payloads
_SITE_NAMES = {"liepin", "boss", "zhaopin"}


def extract_recruiting_summary(
    output: Union[str, list[dict[str, Any]]],
) -> str:
    """Extract pre-rendered summary_markdown from recruiting tool output.

    Returns the summary markdown string if found, or empty string.
    """
    payload = _extract_first_json_payload(output)
    if not payload:
        return ""

    site = payload.get("site", "")
    if site not in _SITE_NAMES:
        return ""

    summary = payload.get("summary_markdown", "")
    return summary if isinstance(summary, str) else ""


def _extract_first_json_payload(
    output: Union[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Try to extract a JSON object from tool output."""
    raw: str | None = None

    if isinstance(output, str):
        raw = output
    elif isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and item.get("type") == "text":
                raw = item.get("text")
                if raw:
                    break

    if not raw or not isinstance(raw, str):
        return None

    return _load_json_object(raw)


def _load_json_object(text: str) -> dict[str, Any] | None:
    """Attempt to parse *text* as a JSON object."""
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None
