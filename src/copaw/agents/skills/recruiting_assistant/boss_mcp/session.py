# -*- coding: utf-8 -*-
"""Persistent browser session helpers for the BOSS MCP adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from copaw.config.utils import (
    get_playwright_chromium_executable_path,
    get_system_default_browser,
)

from ..models import SiteStatus
from .models import BrowserLaunchConfig

_DEFAULT_PROFILE_DIR = (
    Path.home() / ".copaw" / "recruiting" / "boss-profile"
)
_BOSS_HOME_URL = "https://www.zhipin.com/web/chat/index"
_BOSS_HOST_SUFFIX = "zhipin.com"
_SEARCH_TAB_SELECTORS = [
    "text=搜索人才",
    "[role='tab']:has-text('搜索人才')",
    "button:has-text('搜索人才')",
    "a:has-text('搜索人才')",
]
_SEARCH_INPUT_SELECTORS = [
    "input[placeholder*='搜索人才']",
    "input[placeholder*='搜索候选人']",
    "input[placeholder*='请输入关键词']",
    "input[placeholder*='搜索']",
    "input[type='search']",
    "input",
    "textarea",
]


def resolve_browser_launch_config(
    profile_dir: str | None = None,
    *,
    cdp_url: str | None = None,
    headless: bool = False,
) -> BrowserLaunchConfig:
    """Resolve which browser executable/profile the adapter should use."""
    default_kind, default_path = get_system_default_browser()
    chromium_path = get_playwright_chromium_executable_path()

    browser_kind = "chromium"
    executable_path: str | None = None

    if default_kind == "chromium" and default_path:
        executable_path = default_path
    elif chromium_path:
        executable_path = chromium_path
    else:
        browser_kind = default_kind or "chromium"
        executable_path = default_path

    return BrowserLaunchConfig(
        browser_kind=browser_kind,
        executable_path=executable_path,
        profile_dir=str(
            Path(profile_dir).expanduser()
            if profile_dir
            else _DEFAULT_PROFILE_DIR
        ),
        cdp_url=str(cdp_url or "").strip() or None,
        headless=headless,
    )


def detect_boss_status(
    current_url: str,
    page_text: str,
) -> SiteStatus:
    """Infer stable BOSS session states from URL and visible text."""
    url = (current_url or "").lower()
    text = (page_text or "").strip()

    if any(token in text for token in ("验证码", "滑动验证", "安全验证", "人机验证")):
        return "captcha_required"
    if "login" in url or any(token in text for token in ("登录", "扫码登录", "账号登录")):
        if "退出登录" not in text:
            return "not_logged_in"
    return "ok"


def _is_boss_url(url: str) -> bool:
    hostname = urlparse(url or "").hostname or ""
    return hostname.endswith(_BOSS_HOST_SUFFIX)


class BossBrowserSession:
    """Manage a persistent Playwright browser profile for BOSS recruiter flows."""

    def __init__(self, launch_config: BrowserLaunchConfig) -> None:
        self.launch_config = launch_config
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None

    async def ensure_started(self) -> Any:
        """Start the persistent browser context and return the active page."""
        if self._context is None:
            self._context = await self._launch_context()

        pages = getattr(self._context, "pages", []) or []
        if pages:
            return self._select_active_page(pages)
        return await self._context.new_page()

    async def _launch_context(self) -> Any:
        """Launch the persistent browser context backing this recruiter session."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        if self.launch_config.cdp_url:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.launch_config.cdp_url,
            )
            contexts = getattr(self._browser, "contexts", []) or []
            if contexts:
                return contexts[0]
            return await self._browser.new_context()

        Path(self.launch_config.profile_dir).mkdir(
            parents=True,
            exist_ok=True,
        )
        browser_type = getattr(
            self._playwright,
            self.launch_config.browser_kind,
            self._playwright.chromium,
        )

        launch_kwargs: dict[str, Any] = {
            "user_data_dir": self.launch_config.profile_dir,
            "headless": self.launch_config.headless,
        }
        if self.launch_config.executable_path:
            launch_kwargs["executable_path"] = (
                self.launch_config.executable_path
            )
        if self.launch_config.browser_kind == "chromium":
            launch_kwargs["args"] = ["--start-maximized"]

        return await browser_type.launch_persistent_context(**launch_kwargs)

    async def close(self) -> None:
        """Close the running browser context if present."""
        if self._context is not None and not self.launch_config.cdp_url:
            await self._context.close()
        self._context = None
        self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def check_status(self, page: Any | None = None) -> SiteStatus:
        """Check the current BOSS login/verification state."""
        active_page = page or await self.ensure_started()
        if active_page is None:
            return "internal_error"

        try:
            body_text = await active_page.locator("body").inner_text(
                timeout=3000,
            )
        except Exception:
            body_text = ""
        return detect_boss_status(getattr(active_page, "url", ""), body_text)

    async def ensure_entry_page(self, page: Any | None = None) -> Any:
        """Open the BOSS recruiter home page unless already on a BOSS tab."""
        active_page = page or await self.ensure_started()
        if _is_boss_url(getattr(active_page, "url", "")):
            return active_page

        await active_page.goto(_BOSS_HOME_URL)
        await active_page.wait_for_load_state(
            "domcontentloaded",
            timeout=10000,
        )
        return active_page

    async def search_phrase(
        self,
        page: Any,
        phrase: str,
        page_number: int,
    ) -> SiteStatus:
        """Search BOSS using the visible recruiter talent-search input."""
        if not _is_boss_url(getattr(page, "url", "")):
            page = await self.ensure_entry_page(page)

        await self._ensure_candidate_search_surface(page)
        locator = await self._find_search_input(page)
        if locator is None:
            status = await self.check_status(page)
            if status != "ok":
                return status
            return "site_layout_changed"

        await locator.click()
        await locator.fill("")
        await locator.fill(phrase)
        await locator.press("Enter")
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await page.wait_for_timeout(1500)

        if page_number > 1:
            await self._goto_page_number(page, page_number)

        return await self.check_status(page)

    async def _ensure_candidate_search_surface(self, page: Any) -> None:
        """Best-effort switch into the visible candidate-search tab first."""
        locator = await self._find_clickable_target(page, _SEARCH_TAB_SELECTORS)
        if locator is None:
            return
        try:
            await locator.click()
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=10000,
            )
        except Exception:
            return
        try:
            await page.wait_for_timeout(800)
        except Exception:
            return

    async def _find_search_input(self, page: Any) -> Any | None:
        """Find the first visible editable search input."""
        for selector in _SEARCH_INPUT_SELECTORS:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, 5)):
                candidate = locator.nth(index)
                try:
                    if await candidate.is_visible() and await candidate.is_editable():
                        return candidate
                except Exception:
                    continue
        return None

    async def _find_clickable_target(
        self,
        page: Any,
        selectors: list[str],
    ) -> Any | None:
        """Return the first visible click target from a selector list."""
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = await locator.count()
            except Exception:
                continue
            for index in range(min(count, 5)):
                candidate = locator.nth(index)
                try:
                    if await candidate.is_visible():
                        return candidate
                except Exception:
                    continue
        return None

    async def _goto_page_number(self, page: Any, page_number: int) -> None:
        """Best-effort move the current results page to a target page number."""
        if page_number <= 1:
            return

        selectors = [
            f"[aria-label='{page_number}']",
            f"a[aria-label='{page_number}']",
            f"button[aria-label='{page_number}']",
            f"[data-page='{page_number}']",
            f"[data-page-num='{page_number}']",
            f"[data-page-number='{page_number}']",
            f"[title='{page_number}']",
            f'a:has-text("{page_number}")',
            f'button:has-text("{page_number}")',
            f'li:has-text("{page_number}")',
            f"text='{page_number}'",
        ]
        locator = await self._find_clickable_target(page, selectors)
        if locator is None:
            return

        try:
            await locator.click()
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=10000,
            )
        except Exception:
            return
        try:
            await page.wait_for_timeout(1000)
        except Exception:
            return

    @staticmethod
    def _select_active_page(pages: list[Any]) -> Any:
        """Prefer the newest BOSS tab before falling back to the newest page."""
        for page in reversed(pages):
            if _is_boss_url(str(getattr(page, "url", "") or "")):
                return page
        return pages[-1]
