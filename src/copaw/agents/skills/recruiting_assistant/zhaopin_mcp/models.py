# -*- coding: utf-8 -*-
"""Models shared by the Zhaopin MCP adapter."""

from __future__ import annotations

from pydantic import BaseModel


class BrowserLaunchConfig(BaseModel):
    """Resolved browser launch configuration for Zhaopin automation."""

    browser_kind: str = "chromium"
    executable_path: str | None = None
    profile_dir: str
    cdp_url: str | None = None
    headless: bool = False

