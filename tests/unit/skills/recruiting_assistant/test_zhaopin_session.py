# -*- coding: utf-8 -*-
"""Tests for Zhaopin browser session helpers."""

from copaw.agents.skills.recruiting_assistant.models import (
    NormalizedSearchQuery,
)
from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.models import (
    BrowserLaunchConfig,
)
from copaw.agents.skills.recruiting_assistant.zhaopin_mcp.session import (
    ZhaopinBrowserSession,
    detect_zhaopin_status,
    resolve_browser_launch_config,
)


def test_resolve_browser_launch_config_prefers_default_chromium(
    monkeypatch,
) -> None:
    """Prefer the user's default Chromium browser when available."""
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.zhaopin_mcp.session.get_system_default_browser",
        lambda: ("chromium", "/Applications/Google Chrome.app/test"),
    )
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.zhaopin_mcp.session.get_playwright_chromium_executable_path",
        lambda: "/fallback/chromium",
    )

    config = resolve_browser_launch_config(
        profile_dir="/tmp/zhaopin-profile",
        headless=False,
    )

    assert config.browser_kind == "chromium"
    assert config.executable_path == "/Applications/Google Chrome.app/test"
    assert config.profile_dir == "/tmp/zhaopin-profile"
    assert config.headless is False


def test_detect_zhaopin_status_handles_login_and_captcha_states() -> None:
    """Detect stable manual-verification states from URL and page text."""
    assert (
        detect_zhaopin_status(
            "https://rd6.zhaopin.com/login",
            "请先登录后继续",
        )
        == "not_logged_in"
    )
    assert (
        detect_zhaopin_status(
            "https://rd6.zhaopin.com/talent/search",
            "请完成滑动验证后继续访问",
        )
        == "captcha_required"
    )
    assert (
        detect_zhaopin_status(
            "https://rd6.zhaopin.com/",
            "退出登录 搜索人才",
        )
        == "ok"
    )


def test_detect_zhaopin_status_prefers_recruiter_surface_over_generic_login_copy() -> None:
    """Recruiter-only navigation should win over incidental login text."""
    assert (
        detect_zhaopin_status(
            "https://rd6.zhaopin.com/talent/search",
            "搜索人才 搜索简历 登录帮助 常见问题",
        )
        == "ok"
    )


async def test_ensure_started_prefers_latest_zhaopin_page() -> None:
    """Continue flows should prefer the newest existing Zhaopin page."""

    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [
                FakePage("https://www.example.com/old"),
                FakePage("https://rd6.zhaopin.com/"),
            ]

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    session._context = FakeContext()

    page = await session.ensure_started()

    assert page.url == "https://rd6.zhaopin.com/"


async def test_ensure_entry_page_navigates_to_zhaopin_home() -> None:
    """Non-Zhaopin tabs should be redirected to the recruiter home page."""

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

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    page = FakePage()

    active_page = await session.ensure_entry_page(page)

    assert active_page is page
    assert page.goto_calls == ["https://rd6.zhaopin.com/"]
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
            self.url = "https://rd6.zhaopin.com/"
            self.search_locator = search_locator
            self.wait_load_calls: list[tuple[str, int]] = []
            self.wait_timeout_calls: list[int] = []

        def locator(self, selector: str):
            if selector in {
                "input[placeholder*='搜索人才']",
                "input[placeholder*='搜索简历']",
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
    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    monkeypatch.setattr(
        session,
        "check_status",
        fake_check_status.__get__(session, ZhaopinBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_goto_page_number",
        fake_goto_page_number.__get__(session, ZhaopinBrowserSession),
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


async def test_search_phrase_switches_into_search_talent_surface_before_typing(
    monkeypatch,
) -> None:
    """Homepage search should click the 搜索人才 tab before typing."""

    class FakeTabLeafLocator:
        def __init__(self, page) -> None:
            self.page = page

        async def is_visible(self):
            return True

        async def click(self):
            self.page.tab_clicked = True

    class FakeInputLeafLocator:
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
        def __init__(self, items) -> None:
            self.items = list(items)

        async def count(self):
            return len(self.items)

        def nth(self, index: int):
            return self.items[index]

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://rd6.zhaopin.com/app/index"
            self.tab_clicked = False
            self.wait_load_calls: list[tuple[str, int]] = []
            self.wait_timeout_calls: list[int] = []
            self.input_locator = FakeInputLeafLocator()
            self.tab_locator = FakeTabLeafLocator(self)

        def locator(self, selector: str):
            if selector in {
                "text=搜索人才",
                "[role='tab']:has-text('搜索人才')",
                "button:has-text('搜索人才')",
                "a:has-text('搜索人才')",
            }:
                return FakeCollectionLocator([self.tab_locator])
            if selector in {
                "input[placeholder*='搜索人才']",
                "input[placeholder*='搜索简历']",
                "input[placeholder*='请输入关键词']",
                "input[placeholder*='搜索']",
                "input[type='search']",
                "input",
            }:
                if self.tab_clicked:
                    return FakeCollectionLocator([self.input_locator])
                return FakeCollectionLocator([])
            return FakeCollectionLocator([])

        async def wait_for_load_state(self, state: str, timeout: int):
            self.wait_load_calls.append((state, timeout))

        async def wait_for_timeout(self, timeout: int):
            self.wait_timeout_calls.append(timeout)

    async def fake_check_status(self, page):
        _ = page
        return "ok"

    page = FakePage()
    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    monkeypatch.setattr(
        session,
        "check_status",
        fake_check_status.__get__(session, ZhaopinBrowserSession),
    )

    status = await session.search_phrase(page, "Python算法工程师", 1)

    assert status == "ok"
    assert page.tab_clicked is True
    assert page.input_locator.actions == [
        ("click", ""),
        ("fill", ""),
        ("fill", "Python算法工程师"),
        ("press", "Enter"),
    ]


async def test_search_phrase_continues_when_input_click_is_intercepted(
    monkeypatch,
) -> None:
    """Placeholder overlays should not block typing into the editable input."""

    class FakeLeafLocator:
        def __init__(self) -> None:
            self.actions: list[tuple[str, str]] = []

        async def is_visible(self):
            return True

        async def is_editable(self):
            return True

        async def click(self):
            raise RuntimeError("pointer intercepted")

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
            self.url = "https://rd6.zhaopin.com/talent/search"
            self.search_locator = search_locator
            self.wait_load_calls: list[tuple[str, int]] = []
            self.wait_timeout_calls: list[int] = []
            self.goto_calls: list[str] = []

        def locator(self, selector: str):
            if selector in {
                "text=搜索人才",
                "[role='tab']:has-text('搜索人才')",
                "button:has-text('搜索人才')",
                "a:has-text('搜索人才')",
            }:
                return FakeCollectionLocator(None)
            if selector in {
                "input[placeholder*='搜索人才']",
                "input[placeholder*='搜索简历']",
                "input[placeholder*='请输入关键词']",
                "input[placeholder*='搜索']",
                "input[type='search']",
                "input",
            }:
                return FakeCollectionLocator(self.search_locator)
            return FakeCollectionLocator(None)

        async def goto(self, url: str):
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(self, state: str, timeout: int):
            self.wait_load_calls.append((state, timeout))

        async def wait_for_timeout(self, timeout: int):
            self.wait_timeout_calls.append(timeout)

    async def fake_check_status(self, page):
        _ = page
        return "ok"

    locator = FakeLeafLocator()
    page = FakePage(locator)
    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    monkeypatch.setattr(
        session,
        "check_status",
        fake_check_status.__get__(session, ZhaopinBrowserSession),
    )

    status = await session.search_phrase(page, "Python算法工程师", 1)

    assert status == "ok"
    assert locator.actions == [
        ("fill", ""),
        ("fill", "Python算法工程师"),
        ("press", "Enter"),
    ]


async def test_search_phrase_resets_existing_search_page_before_typing(
    monkeypatch,
) -> None:
    """A fresh keyword search should reset stale recruiter filters by going back home first."""

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
            self.url = "https://rd6.zhaopin.com/app/search"
            self.search_locator = search_locator
            self.wait_load_calls: list[tuple[str, int]] = []
            self.wait_timeout_calls: list[int] = []

        def locator(self, selector: str):
            if selector in {
                "text=搜索人才",
                "[role='tab']:has-text('搜索人才')",
                "button:has-text('搜索人才')",
                "a:has-text('搜索人才')",
            }:
                return FakeCollectionLocator(None)
            if selector in {
                "input[placeholder*='搜索人才']",
                "input[placeholder*='搜索简历']",
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

    home_reset_calls: list[str] = []

    async def fake_goto_recruiter_home(self, page):
        home_reset_calls.append(page.url)
        page.url = "https://rd6.zhaopin.com/app/index"

    locator = FakeLeafLocator()
    page = FakePage(locator)
    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    monkeypatch.setattr(
        session,
        "check_status",
        fake_check_status.__get__(session, ZhaopinBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_goto_recruiter_home",
        fake_goto_recruiter_home.__get__(session, ZhaopinBrowserSession),
        raising=False,
    )

    status = await session.search_phrase(page, "Python算法工程师", 1)

    assert status == "ok"
    assert home_reset_calls == ["https://rd6.zhaopin.com/app/search"]
    assert locator.actions == [
        ("click", ""),
        ("fill", ""),
        ("fill", "Python算法工程师"),
        ("press", "Enter"),
    ]


async def test_apply_query_filters_uses_expected_city_current_city_experience_and_education(
    monkeypatch,
) -> None:
    """Structured recruiter filters should map onto the visible Zhaopin filter controls."""

    class FakePage:
        url = "https://rd6.zhaopin.com/app/search"

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    page = FakePage()
    calls: list[tuple[str, str | int]] = []

    async def fake_apply_expected_city(self, page_arg, city):
        assert page_arg is page
        calls.append(("expected_city", city))
        return True

    async def fake_apply_current_city(self, page_arg, city):
        assert page_arg is page
        calls.append(("current_city", city))
        return True

    async def fake_click_labeled_option(self, page_arg, section_title, option_text):
        assert page_arg is page
        calls.append((section_title, option_text))
        return True

    async def fake_goto_page_number(self, page_arg, page_number):
        assert page_arg is page
        calls.append(("goto_page", page_number))

    monkeypatch.setattr(
        session,
        "_apply_expected_city_filter",
        fake_apply_expected_city.__get__(session, ZhaopinBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_apply_current_city_filter",
        fake_apply_current_city.__get__(session, ZhaopinBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_click_labeled_filter_option",
        fake_click_labeled_option.__get__(session, ZhaopinBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_goto_page_number",
        fake_goto_page_number.__get__(session, ZhaopinBrowserSession),
    )

    query = NormalizedSearchQuery(
        position="Python算法工程师",
        expected_city="青岛",
        current_city="青岛",
        experience="6年以上",
        education="本科",
    )

    result = await session.apply_query_filters(page, query, page_number=2)

    assert result == {
        "search_surface": "recruiter",
        "trusted_site_filters": True,
        "applied_filters": {
            "expected_city": True,
            "current_city": True,
            "experience": True,
            "education": True,
        },
    }
    assert calls == [
        ("expected_city", "青岛"),
        ("current_city", "青岛"),
        ("经验要求", "5-10年"),
        ("学历要求", "本科及以上"),
        ("goto_page", 2),
    ]


async def test_apply_query_filters_waits_for_results_refresh_after_structured_filters(
    monkeypatch,
) -> None:
    """Structured filter flows should wait for the candidate list to refresh before returning."""

    class FakePage:
        url = "https://rd6.zhaopin.com/app/search"

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    page = FakePage()
    observed_wait_signatures: list[tuple[str, ...]] = []

    async def fake_capture_results_signature(self, page_arg):
        assert page_arg is page
        return ("keyword-only", "page-1")

    async def fake_apply_expected_city(self, page_arg, city):
        assert page_arg is page
        assert city == "深圳"
        return True

    async def fake_wait_for_results_refresh(self, page_arg, previous_signature):
        assert page_arg is page
        observed_wait_signatures.append(previous_signature)
        return ("filtered", "page-1")

    monkeypatch.setattr(
        session,
        "_capture_results_signature",
        fake_capture_results_signature.__get__(
            session,
            ZhaopinBrowserSession,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        session,
        "_apply_expected_city_filter",
        fake_apply_expected_city.__get__(session, ZhaopinBrowserSession),
    )
    monkeypatch.setattr(
        session,
        "_wait_for_results_refresh",
        fake_wait_for_results_refresh.__get__(
            session,
            ZhaopinBrowserSession,
        ),
        raising=False,
    )

    query = NormalizedSearchQuery(
        position="Python算法工程师",
        expected_city="深圳",
    )

    await session.apply_query_filters(page, query, page_number=1)

    assert observed_wait_signatures == [("keyword-only", "page-1")]


async def test_wait_for_results_refresh_prefers_latest_stable_signature(
    monkeypatch,
) -> None:
    """Refresh waits should not settle on a transient intermediate candidate batch."""

    class FakePage:
        def __init__(self) -> None:
            self.wait_calls: list[int] = []

        async def wait_for_timeout(self, timeout: int):
            self.wait_calls.append(timeout)

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    page = FakePage()
    signatures = iter(
        [
            ("keyword-only", "page-1"),
            ("intermediate", "page-1"),
            ("intermediate", "page-1"),
            ("final", "page-1"),
            ("final", "page-1"),
            ("final", "page-1"),
        ]
    )

    async def fake_capture_results_signature(self, page_arg):
        assert page_arg is page
        return next(signatures)

    monkeypatch.setattr(
        session,
        "_capture_results_signature",
        fake_capture_results_signature.__get__(
            session,
            ZhaopinBrowserSession,
        ),
        raising=False,
    )

    result = await session._wait_for_results_refresh(
        page,
        ("keyword-only", "page-1"),
        attempts=5,
        interval_ms=250,
    )

    assert result == ("final", "page-1")
    assert page.wait_calls


async def test_select_keyword_panel_city_replaces_existing_multi_select_before_confirming(
    monkeypatch,
) -> None:
    """Expected-city selection should clear prior city tags before picking and confirming the new one."""

    class FakeTriggerLocator:
        def __init__(self) -> None:
            self.click_calls = 0

        async def is_visible(self):
            return True

        async def click(self):
            self.click_calls += 1

    class FakeCollectionLocator:
        def __init__(self, items) -> None:
            self.items = list(items)

        async def count(self):
            return len(self.items)

        def nth(self, index: int):
            return self.items[index]

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://rd6.zhaopin.com/app/search"
            self.trigger = FakeTriggerLocator()
            self.wait_timeout_calls: list[int] = []

        def locator(self, selector: str):
            if selector in {
                ".keyword-panel-city__label",
                ".keyword-panel-city",
                ".keyword-panel__city",
            }:
                return FakeCollectionLocator([self.trigger])
            return FakeCollectionLocator([])

        async def wait_for_timeout(self, timeout: int):
            self.wait_timeout_calls.append(timeout)

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )
    page = FakePage()
    calls: list[object] = []

    async def fake_clear_selected_cities(self, page_arg):
        assert page_arg is page
        calls.append("clear")
        return 1

    async def fake_click_city_option(self, page_arg, city):
        assert page_arg is page
        calls.append(("choose", city))
        return True

    async def fake_confirm_city(self, page_arg):
        assert page_arg is page
        calls.append("confirm")
        return True

    monkeypatch.setattr(
        session,
        "_clear_keyword_panel_selected_cities",
        fake_clear_selected_cities.__get__(session, ZhaopinBrowserSession),
        raising=False,
    )
    monkeypatch.setattr(
        session,
        "_click_keyword_panel_city_option",
        fake_click_city_option.__get__(session, ZhaopinBrowserSession),
        raising=False,
    )
    monkeypatch.setattr(
        session,
        "_confirm_keyword_panel_city_selection",
        fake_confirm_city.__get__(session, ZhaopinBrowserSession),
        raising=False,
    )

    result = await session._select_keyword_panel_city(page, "深圳")

    assert result is True
    assert page.trigger.click_calls == 1
    assert calls == ["clear", ("choose", "深圳"), "confirm"]


async def test_condition_chip_matches_requires_exact_value_for_multi_city_expected_city() -> None:
    """A multi-city chip should not count as an exact match for a single expected city."""

    class FakePage:
        async def evaluate(self, script, payload=None):
            _ = script, payload
            return [
                "期望工作地：青岛、深圳",
                "关键词：Python算法工程师",
            ]

    session = ZhaopinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/zhaopin-test"),
    )

    assert (
        await session._condition_chip_matches(
            FakePage(),
            "期望工作地",
            "深圳",
        )
        is False
    )
