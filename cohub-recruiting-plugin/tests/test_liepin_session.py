# -*- coding: utf-8 -*-
"""Tests for Liepin browser session helpers."""

from types import SimpleNamespace

from cohub_recruiting.liepin_mcp.session import (
    LiepinBrowserSession,
    _extract_custom_experience_min_years,
    _map_experience_filter_label,
    detect_liepin_status,
    preferred_liepin_home_url,
    resolve_browser_launch_config,
)
from cohub_recruiting.liepin_mcp.models import (
    BrowserLaunchConfig,
)


def test_resolve_browser_launch_config_prefers_default_chromium(
    monkeypatch,
) -> None:
    """Prefer the user's default Chromium browser when available."""
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.liepin_mcp.session.get_system_default_browser",
        lambda: ("chromium", "/Applications/Google Chrome.app/test"),
    )
    monkeypatch.setattr(
        "copaw.agents.skills.recruiting_assistant.liepin_mcp.session.get_playwright_chromium_executable_path",
        lambda: "/fallback/chromium",
    )

    config = resolve_browser_launch_config(
        profile_dir="/tmp/liepin-profile",
        headless=False,
    )

    assert config.browser_kind == "chromium"
    assert config.executable_path == "/Applications/Google Chrome.app/test"
    assert config.profile_dir == "/tmp/liepin-profile"
    assert config.headless is False


def test_detect_liepin_status_handles_login_and_captcha_states() -> None:
    """Detect stable manual-verification states from URL and page text."""
    assert (
        detect_liepin_status(
            "https://www.liepin.com/login",
            "请先登录后继续",
        )
        == "not_logged_in"
    )
    assert (
        detect_liepin_status(
            "https://www.liepin.com/",
            "请完成滑动验证后继续访问",
        )
        == "captcha_required"
    )
    assert (
        detect_liepin_status(
            "https://www.liepin.com/",
            "退出登录 候选人搜索",
        )
        == "ok"
    )


def test_preferred_liepin_home_url_prefers_recruiter_domain() -> None:
    """Recruiting flows should preserve the current recruiter-side origin."""
    assert (
        preferred_liepin_home_url(
            "https://h.liepin.com/account/dashboard",
        )
        == "https://h.liepin.com/"
    )
    assert (
        preferred_liepin_home_url(
            "https://lpt.liepin.com/user/login",
        )
        == "https://lpt.liepin.com/"
    )
    assert (
        preferred_liepin_home_url(
            "https://www.liepin.com/",
        )
        == "https://www.liepin.com/"
    )
    assert (
        preferred_liepin_home_url(
            "",
        )
        == "https://www.liepin.com/"
    )


def test_map_experience_filter_label_uses_custom_for_min_year_queries() -> None:
    """Minimum-year queries should use the recruiter's custom experience control."""
    assert _map_experience_filter_label("5年以上") == "自定义"
    assert _map_experience_filter_label("6年以上") == "自定义"
    assert _extract_custom_experience_min_years("6年以上") == 6


def test_map_experience_filter_label_keeps_explicit_bucket_ranges() -> None:
    """Explicit recruiter bucket ranges should keep using the quick filter chips."""
    assert _map_experience_filter_label("1-3年") == "1-3年"
    assert _map_experience_filter_label("3-5年") == "3-5年"
    assert _map_experience_filter_label("5-10年") == "5-10年"
    assert _extract_custom_experience_min_years("5-10年") is None


async def test_apply_query_filters_uses_custom_experience_min_years() -> None:
    """Recruiter search should fill the custom minimum experience value when needed."""

    class FakePage:
        url = "https://h.liepin.com/candidate/search"

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    calls: list[tuple[str, str, object]] = []

    async def fake_click_filter_option(page, section_title, option_text) -> bool:
        _ = page
        calls.append(("click", section_title, option_text))
        return True

    async def fake_fill_custom_experience_min(page, min_years) -> bool:
        _ = page
        calls.append(("custom_min", "经验", min_years))
        return True

    session._click_filter_option = fake_click_filter_option  # type: ignore[method-assign]
    session._fill_custom_experience_min = fake_fill_custom_experience_min  # type: ignore[method-assign]

    result = await session.apply_query_filters(
        FakePage(),
        SimpleNamespace(
            expected_city="上海",
            experience="6年以上",
            education="本科",
        ),
    )

    assert result["applied_filters"] == {
        "expected_city": True,
        "experience": True,
        "education": True,
    }
    assert calls == [
        ("click", "期望城市", "上海"),
        ("click", "经验", "自定义"),
        ("custom_min", "经验", 6),
        ("click", "教育经历", "本科"),
    ]


async def test_apply_query_filters_supports_current_city_section() -> None:
    """Recruiter search should target the current-city filter when requested."""

    class FakePage:
        url = "https://h.liepin.com/candidate/search"

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    calls: list[tuple[str, str, object]] = []

    async def fake_click_filter_option(page, section_title, option_text) -> bool:
        _ = page
        calls.append(("click", section_title, option_text))
        return True

    session._click_filter_option = fake_click_filter_option  # type: ignore[method-assign]

    result = await session.apply_query_filters(
        FakePage(),
        SimpleNamespace(
            current_city="青岛",
            expected_city="",
            experience="",
            education="",
        ),
    )

    assert result["applied_filters"] == {
        "current_city": True,
    }
    assert calls == [
        ("click", "目前城市", "青岛"),
    ]


async def test_ensure_started_prefers_latest_liepin_page() -> None:
    """Continue flows should prefer the newest existing Liepin page."""

    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [
                FakePage("https://www.example.com/old"),
                FakePage("https://h.liepin.com/account/login"),
            ]

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    session._context = FakeContext()

    page = await session.ensure_started()

    assert page.url == "https://h.liepin.com/account/login"


async def test_ensure_started_prefers_recruiter_tab_over_newer_public_tab() -> None:
    """Recruiting flows should stay on the logged-in recruiter tab."""

    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url

    class FakeContext:
        def __init__(self) -> None:
            self.pages = [
                FakePage("https://h.liepin.com/candidate/search"),
                FakePage("https://www.liepin.com/zhaopin/"),
            ]

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    session._context = FakeContext()

    page = await session.ensure_started()

    assert page.url == "https://h.liepin.com/candidate/search"


async def test_ensure_entry_page_opens_public_home_when_not_on_liepin() -> None:
    """Initial manual login flow should start from the public homepage."""

    class FakePage:
        def __init__(self, url: str) -> None:
            self.url = url
            self.goto_calls: list[str] = []
            self.wait_calls: list[str] = []

        async def goto(self, url: str) -> None:
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = timeout
            self.wait_calls.append(state)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage("about:blank")

    returned = await session.ensure_entry_page(page)

    assert returned is page
    assert page.goto_calls == ["https://www.liepin.com/"]
    assert page.wait_calls == ["domcontentloaded"]


async def test_search_phrase_clicks_search_talent_tab_before_typing() -> None:
    """Homepage search should enter the candidate-search tab before typing."""

    class FakeElement:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector
            self.filled_values: list[str] = []
            self.pressed_keys: list[str] = []

        async def is_visible(self) -> bool:
            return True

        async def is_editable(self) -> bool:
            return self.selector == "input[placeholder*='人才']"

        async def click(self) -> None:
            self.page.clicked_selectors.append(self.selector)
            if self.selector == "text=搜索人才":
                self.page.search_talent_tab_opened = True

        async def fill(self, value: str) -> None:
            self.filled_values.append(value)
            self.page.filled_values.append(value)

        async def press(self, key: str) -> None:
            self.pressed_keys.append(key)
            self.page.pressed_keys.append(key)

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def count(self) -> int:
            if self.selector == "text=搜索人才":
                return 1
            if (
                self.selector == "input[placeholder*='人才']"
                and self.page.search_talent_tab_opened
            ):
                return 1
            return 0

        def nth(self, _index: int) -> FakeElement:
            return FakeElement(self.page, self.selector)

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://www.liepin.com/"
            self.search_talent_tab_opened = False
            self.clicked_selectors: list[str] = []
            self.filled_values: list[str] = []
            self.pressed_keys: list[str] = []
            self.wait_calls: list[str] = []
            self.wait_timeouts: list[int] = []

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = timeout
            self.wait_calls.append(state)

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_timeouts.append(timeout_ms)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    async def fake_check_status(_page) -> str:
        return "ok"

    session.check_status = fake_check_status  # type: ignore[method-assign]

    status = await session.search_phrase(page, "Python算法工程师 上海", 1)

    assert status == "ok"
    assert page.clicked_selectors[0] == "text=搜索人才"
    assert page.filled_values == ["", "Python算法工程师 上海"]
    assert page.pressed_keys == ["Enter"]


async def test_search_phrase_resets_existing_liepin_results_page_before_typing() -> None:
    """Each new search should start from a clean Liepin home state."""

    class FakeElement:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def is_visible(self) -> bool:
            return True

        async def is_editable(self) -> bool:
            return self.selector == "input[placeholder*='人才']"

        async def click(self) -> None:
            self.page.clicked_selectors.append(self.selector)
            if self.selector == "text=搜索人才":
                self.page.search_talent_tab_opened = True

        async def fill(self, value: str) -> None:
            self.page.filled_values.append(value)

        async def press(self, key: str) -> None:
            self.page.pressed_keys.append(key)

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def count(self) -> int:
            if self.selector == "text=搜索人才":
                return 1
            if (
                self.selector == "input[placeholder*='人才']"
                and self.page.search_talent_tab_opened
            ):
                return 1
            return 0

        def nth(self, _index: int) -> FakeElement:
            return FakeElement(self.page, self.selector)

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://lpt.liepin.com/search?old=filters"
            self.search_talent_tab_opened = False
            self.clicked_selectors: list[str] = []
            self.filled_values: list[str] = []
            self.pressed_keys: list[str] = []
            self.goto_calls: list[str] = []

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        async def goto(self, url: str) -> None:
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = state, timeout

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            _ = timeout_ms

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    async def fake_check_status(_page) -> str:
        return "ok"

    session.check_status = fake_check_status  # type: ignore[method-assign]

    status = await session.search_phrase(page, "Python算法工程师", 1)

    assert status == "ok"
    assert page.goto_calls == ["https://www.liepin.com/"]
    assert page.clicked_selectors[0] == "text=搜索人才"
    assert page.filled_values == ["", "Python算法工程师"]


async def test_search_phrase_falls_back_to_public_home_from_stale_liepin_tab() -> None:
    """Search should recover from stale Liepin tabs by reopening the public home."""

    class FakeElement:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def is_visible(self) -> bool:
            return True

        async def is_editable(self) -> bool:
            return self.selector == "input[placeholder*='人才']"

        async def click(self) -> None:
            self.page.clicked_selectors.append(self.selector)
            if self.selector == "text=搜索人才":
                self.page.search_talent_tab_opened = True

        async def fill(self, value: str) -> None:
            self.page.filled_values.append(value)

        async def press(self, key: str) -> None:
            self.page.pressed_keys.append(key)

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def count(self) -> int:
            if not self.page.public_home_opened:
                return 0
            if self.selector == "text=搜索人才":
                return 1
            if (
                self.selector == "input[placeholder*='人才']"
                and self.page.search_talent_tab_opened
            ):
                return 1
            return 0

        def nth(self, _index: int) -> FakeElement:
            return FakeElement(self.page, self.selector)

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://h.liepin.com/some-stale-page"
            self.public_home_opened = False
            self.search_talent_tab_opened = False
            self.goto_calls: list[str] = []
            self.clicked_selectors: list[str] = []
            self.filled_values: list[str] = []
            self.pressed_keys: list[str] = []
            self.wait_calls: list[str] = []
            self.wait_timeouts: list[int] = []

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        async def goto(self, url: str) -> None:
            self.goto_calls.append(url)
            self.url = url
            if url == "https://www.liepin.com/":
                self.public_home_opened = True

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = timeout
            self.wait_calls.append(state)

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_timeouts.append(timeout_ms)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    async def fake_check_status(_page) -> str:
        return "ok"

    session.check_status = fake_check_status  # type: ignore[method-assign]

    status = await session.search_phrase(page, "Python算法工程师 上海", 1)

    assert status == "ok"
    assert page.goto_calls == ["https://www.liepin.com/"]
    assert page.clicked_selectors == ["text=搜索人才", "input[placeholder*='人才']"]
    assert page.filled_values == ["", "Python算法工程师 上海"]
    assert page.pressed_keys == ["Enter"]


async def test_find_search_input_prefers_primary_recruiter_search_box() -> None:
    """Recruiter search should type into the top search box, not filter inputs."""

    class FakeElement:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        async def is_visible(self) -> bool:
            return True

        async def is_editable(self) -> bool:
            return True

    class FakeLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        async def count(self) -> int:
            if self.selector in {
                "input[placeholder*='搜职位/公司/行业']",
                "input[placeholder*='搜索职位']",
                "input",
            }:
                return 1
            return 0

        def nth(self, _index: int) -> FakeElement:
            return FakeElement(self.selector)

    class FakePage:
        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )

    locator = await session._find_search_input(FakePage())  # type: ignore[arg-type]

    assert locator is not None
    assert locator.selector == "input[placeholder*='搜职位/公司/行业']"


async def test_goto_page_number_uses_dom_pagination_fallback_when_locators_miss() -> None:
    """Pagination should fall back to a DOM-scoped click when simple selectors miss."""

    class FakeElement:
        def __init__(self, page, selector: str, visible: bool) -> None:
            self.page = page
            self.selector = selector
            self.visible = visible

        async def is_visible(self) -> bool:
            return self.visible

        async def click(self) -> None:
            self.page.clicked_selectors.append(self.selector)

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def count(self) -> int:
            return 0

        def nth(self, _index: int) -> FakeElement:
            return FakeElement(self.page, self.selector, False)

        @property
        def first(self) -> FakeElement:
            return FakeElement(self.page, self.selector, False)

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://h.liepin.com/candidate/search?currentPage=1"
            self.clicked_selectors: list[str] = []
            self.goto_calls: list[str] = []
            self.evaluate_calls: list[dict[str, int]] = []
            self.wait_calls: list[str] = []
            self.wait_timeouts: list[int] = []

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        async def evaluate(
            self,
            _script: str,
            payload: dict[str, int],
        ) -> bool:
            self.evaluate_calls.append(payload)
            return payload == {"pageNumber": 2}

        async def goto(self, url: str) -> None:
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = timeout
            self.wait_calls.append(state)

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_timeouts.append(timeout_ms)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    await session._goto_page_number(page, 2)

    assert page.evaluate_calls == [{"pageNumber": 2}]
    assert page.goto_calls == []
    assert page.wait_calls == ["domcontentloaded"]
    assert page.wait_timeouts == [1000]


async def test_goto_page_number_rewrites_known_pagination_query_params() -> None:
    """Pagination should rewrite known page query params when clicking is unavailable."""

    class FakeElement:
        def __init__(self, page, selector: str, visible: bool) -> None:
            self.page = page
            self.selector = selector
            self.visible = visible

        async def is_visible(self) -> bool:
            return self.visible

        async def click(self) -> None:
            self.page.clicked_selectors.append(self.selector)

    class FakeLocator:
        def __init__(self, page, selector: str) -> None:
            self.page = page
            self.selector = selector

        async def count(self) -> int:
            return 0

        def nth(self, _index: int) -> FakeElement:
            return FakeElement(self.page, self.selector, False)

        @property
        def first(self) -> FakeElement:
            return FakeElement(self.page, self.selector, False)

    class FakePage:
        def __init__(self) -> None:
            self.url = (
                "https://h.liepin.com/candidate/search?"
                "keyword=python&currentPage=1&cur_page=0&page=1&pageNo=1"
            )
            self.clicked_selectors: list[str] = []
            self.goto_calls: list[str] = []
            self.evaluate_calls: list[dict[str, int]] = []
            self.wait_calls: list[str] = []
            self.wait_timeouts: list[int] = []

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(self, selector)

        async def evaluate(
            self,
            _script: str,
            payload: dict[str, int],
        ) -> bool:
            self.evaluate_calls.append(payload)
            return False

        async def goto(self, url: str) -> None:
            self.goto_calls.append(url)
            self.url = url

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = timeout
            self.wait_calls.append(state)

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_timeouts.append(timeout_ms)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    await session._goto_page_number(page, 2)

    assert page.evaluate_calls == [{"pageNumber": 2}]
    assert page.goto_calls == [
        "https://h.liepin.com/candidate/search?"
        "keyword=python&currentPage=2&cur_page=1&page=2&pageNo=2"
    ]
    assert page.wait_calls == ["domcontentloaded"]
    assert page.wait_timeouts == [1000]


async def test_fill_custom_experience_min_retries_until_input_is_confirmed() -> None:
    """Custom experience fill should retry until the input really contains the minimum."""

    class FakePage:
        def __init__(self) -> None:
            self.evaluate_calls: list[dict[str, int]] = []
            self.wait_calls: list[str] = []
            self.wait_timeouts: list[int] = []
            self.results = [
                {"filled": False, "reason": "input_not_ready"},
                {"filled": True, "reason": "ok"},
            ]

        async def evaluate(
            self,
            _script: str,
            payload: dict[str, int],
        ) -> dict[str, object]:
            self.evaluate_calls.append(payload)
            return self.results.pop(0)

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = timeout
            self.wait_calls.append(state)

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_timeouts.append(timeout_ms)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    result = await session._fill_custom_experience_min(page, 6)

    assert result is True
    assert page.evaluate_calls == [
        {"minYears": 6},
        {"minYears": 6},
    ]
    assert page.wait_calls == ["domcontentloaded"]
    assert page.wait_timeouts == [400, 800]


async def test_fill_custom_experience_min_returns_false_when_value_never_sticks() -> None:
    """Custom experience fill should fail when the page never confirms the value."""

    class FakePage:
        def __init__(self) -> None:
            self.evaluate_calls: list[dict[str, int]] = []
            self.wait_calls: list[str] = []
            self.wait_timeouts: list[int] = []

        async def evaluate(
            self,
            _script: str,
            payload: dict[str, int],
        ) -> dict[str, object]:
            self.evaluate_calls.append(payload)
            return {"filled": False, "reason": "value_reset"}

        async def wait_for_load_state(
            self,
            state: str,
            timeout: int,
        ) -> None:
            _ = state, timeout
            self.wait_calls.append(state)

        async def wait_for_timeout(self, timeout_ms: int) -> None:
            self.wait_timeouts.append(timeout_ms)

    session = LiepinBrowserSession(
        BrowserLaunchConfig(profile_dir="/tmp/liepin-test"),
    )
    page = FakePage()

    result = await session._fill_custom_experience_min(page, 6)

    assert result is False
    assert page.evaluate_calls == [
        {"minYears": 6},
        {"minYears": 6},
        {"minYears": 6},
        {"minYears": 6},
    ]
    assert page.wait_calls == []
    assert page.wait_timeouts == [400, 400, 400]
