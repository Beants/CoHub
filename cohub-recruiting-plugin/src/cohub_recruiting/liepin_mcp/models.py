# -*- coding: utf-8 -*-
"""Models shared by the Liepin MCP adapter."""

from __future__ import annotations

from pydantic import BaseModel


class BrowserLaunchConfig(BaseModel):
    """Resolved browser launch configuration for Liepin automation."""

    browser_kind: str = "chromium"
    executable_path: str | None = None
    profile_dir: str
    headless: bool = False
