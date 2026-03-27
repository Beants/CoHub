# -*- coding: utf-8 -*-
"""Tests for BOSS browser session helpers."""

from copaw.agents.skills.recruiting_assistant.boss_mcp.models import (
    BrowserLaunchConfig,
)
from copaw.agents.skills.recruiting_assistant.boss_mcp.session import (
    BossBrowserSession,
    detect_boss_status,
    resolve_browser_launch_config,
)


def test_resolve_browser_launch_config_prefers_default_chromium(
    monkeypatch,
) -> None:
    """Prefer the user's default Chromium browser when available."""
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.boss_mcp.session.get_system_default_browser",
        lambda: ("chromium", "/Applications/Google Chrome.app/test"),
    )
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.boss_mcp.session.get_playwright_chromium_executable_path",
        lambda: "/fallback/chromium",
    )

    config = resolve_browser_launch_config(
        profile_dir="/tmp/boss-profile",
        headless=False,
    )

    assert config.browser_kind == "chromium"
    assert config.executable_path == "/Applications/Google Chrome.app/test"
    assert config.profile_dir == "/tmp/boss-profile"
    assert config.headless is False


def test_resolve_browser_launch_config_preserves_cdp_url(
    monkeypatch,
) -> None:
    """CDP attach mode should keep the configured endpoint."""
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.boss_mcp.session.get_system_default_browser",
        lambda: ("chromium", "/Applications/Google Chrome.app/test"),
    )
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.boss_mcp.session.get_playwright_chromium_executable_path",
        lambda: "/fallback/chromium",
    )

    config = resolve_browser_launch_config(
        profile_dir="/tmp/boss-profile",
        cdp_url="http://127.0.0.1:9222",
    )

    assert config.cdp_url == "http://127.0.0.1:9222"


def test_detect_boss_status_handles_login_and_captcha_states() -> None:
    """Detect stable manual-verification states from URL and page text."""
    assert (
        detect_boss_status(
            "https://www.zhipin.com/web/user/login",
            "请先登录后继续",
        )
        == "not_logged_in"
    )
    assert (
        detect_boss_status(
            "https://www.zhipin.com/web/chat/index",
            "请完成滑动验证后继续访问",
        )
        == "captcha_required"
    )
    assert (
        detect_boss_status(
            "https://www.zhipin.com/web/chat/index",
            "退出登录 搜索人才",
        )
        == "ok"
    )


async def test_ensure_started_prefers_latest_boss_page() -> None:
    """Continue flows should prefer the newest existing BOSS page."""

    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [
                FakePage("https://www.example.com/old"),
                FakePage("https://www.zhipin.com/web/chat/index"),
            ]

    session = BossBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/boss-test"),
    )
    session._context = FakeContext()

    page = await session.ensure_started()

    assert page.url == "https://www.zhipin.com/web/chat/index"


async def test_ensure_started_launches_persistent_context_when_needed(
    monkeypatch,
) -> None:
    """The first session start should launch a persistent context and page."""

    class FakePage:
        url = "about:blank"

    class FakeContext:
        def __init__(self) -> None:
            self.pages: list[FakePage] = []
            self.new_page_calls = 0

        async def new_page(self):
            self.new_page_calls += 1
            return FakePage()

    fake_context = FakeContext()

    async def fake_launch_context(self):
        return fake_context

    session = BossBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/boss-test"),
    )
    monkeypatch.setattr(
        session,
        "_launch_context",
        fake_launch_context.__get__(session, BossBrowserSession),
    )

    page = await session.ensure_started()

    assert session._context is fake_context
    assert fake_context.new_page_calls == 1
    assert page.url == "about:blank"


async def test_ensure_entry_page_navigates_to_boss_home() -> None:
    """Non-BOSS tabs should be redirected to the recruiter home page."""

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://www.example.com/"
            self.goto_calls: list[str] = []
            self.wait_calls: list[tuple[str, int]] = []

        async def goto(self, url: str):
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(self, state: str, timeout: int):
            self.wait_calls.append((state, timeout))

    session = BossBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/boss-test"),
    )
    page = FakePage()

    active_page = await session.ensure_entry_page(page)

    assert active_page is page
    assert page.goto_calls == ["https://www.zhipin.com/web/chat/index"]
    assert page.wait_calls == [("domcontentloaded", 10000)]


async def test_search_phrase_uses_visible_search_input_and_target_page(
    monkeypatch,
) -> None:
    """Keyword search should use the visible search input and then switch page."""

    class FakeLeafLocator:
        def __init__(self) -> None:
            self.actions: list[tuple[str, str]] = []

        async def is_visible(self):
            return True

        async def is_editable(self):
            return True

        async def click(self):
            self.actions.append(("click", ""))

        async def fill(self, value: str):
            self.actions.append(("fill", value))

        async def press(self, value: str):
            self.actions.append(("press", value))

    class FakeCollectionLocator:
        def __init__(self, leaf: FakeLeafLocator | None) -> None:
            self.leaf = leaf

        async def count(self):
            return 1 if self.leaf is not None else 0

        def nth(self, index: int):
            assert index == 0
            assert self.leaf is not None
            return self.leaf

    class FakePage:
        def __init__(self, search_locator: FakeLeafLocator) -> None:
            self.url = "https://www.zhipin.com/web/chat/index"
            self.search_locator = search_locator
            self.wait_load_calls: list[tuple[str, int]] = []
            self.wait_timeout_calls: list[int] = []

        def locator(self, selector: str):
            if selector in {
                "input[placeholder*='搜索人才']",
                "input[placeholder*='搜索候选人']",
                "input[placeholder*='请输入关键词']",
                "input[placeholder*='搜索']",
                "input[type='search']",
                "input",
            }:
                return FakeCollectionLocator(self.search_locator)
            return FakeCollectionLocator(None)

        async def wait_for_load_state(self, state: str, timeout: int):
            self.wait_load_calls.append((state, timeout))

        async def wait_for_timeout(self, timeout: int):
            self.wait_timeout_calls.append(timeout)

    async def fake_check_status(self, page):
        _ = page
        return "ok"

    page_target_calls: list[int] = []

    async def fake_goto_page_number(self, page, page_number):
        _ = page
        page_target_calls.append(page_number)

    locator = FakeLeafLocator()
    page = FakePage(locator)
    session = BossBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/boss-test"),
    )
    monkeypatch.setattr(
        session,
        "check_status",
        fake_check_status.__get__(session, BossBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_goto_page_number",
        fake_goto_page_number.__get__(session, BossBrowserSession),
    )

    status = await session.search_phrase(page, "Python算法工程师", 2)

    assert status == "ok"
    assert locator.actions == [
        ("click", ""),
        ("fill", ""),
        ("fill", "Python算法工程师"),
        ("press", "Enter"),
    ]
    assert page.wait_load_calls == [("domcontentloaded", 10000)]
    assert page.wait_timeout_calls == [1500]
    assert page_target_calls == [2]
