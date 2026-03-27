# -*- coding: utf-8 -*-
"""Persistent browser session helpers for the Liepin MCP adapter."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse

from copaw.config.utils import (
    get_playwright_chromium_executable_path,
    get_system_default_browser,
)

from ..models import SiteStatus
from .models import BrowserLaunchConfig

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE_DIR = (
    Path.home() / ".copaw" / "recruiting" / "liepin-profile"
)
_LIEPIN_PUBLIC_HOME_URL = "https://www.liepin.com/"
_LIEPIN_RECRUITER_HOME_URL = "https://h.liepin.com/"
_LIEPIN_RECRUITER_HOSTS = {
    "h.liepin.com",
    "lpt.liepin.com",
}
_SEARCH_INPUT_SELECTORS = [
    "input.searchInput--KgDn1",
    "input[placeholder*='搜职位/公司/行业']",
    "input[placeholder*='中文用空格隔开']",
    "input[placeholder*='人才']",
    "input[placeholder*='候选']",
    "input[placeholder*='简历']",
    "input[placeholder*='搜索']",
    "input[placeholder*='关键词']",
    "input[type='search']",
    "input",
    "textarea",
]
_SEARCH_TAB_SELECTORS = [
    "text=搜索人才",
    "text=人才搜索",
    "text=搜索简历",
    "[role='tab']:has-text('搜索人才')",
    "[role='tab']:has-text('人才搜索')",
    "a:has-text('搜索人才')",
    "a:has-text('人才搜索')",
]
_ONE_BASED_PAGE_QUERY_KEYS = {
    "page",
    "pageNo",
    "pageNum",
    "pageNumber",
    "currentPage",
    "current_page",
    "page_no",
    "page_num",
    "pn",
    "p",
}
_ZERO_BASED_PAGE_QUERY_KEYS = {
    "cur_page",
    "curPage",
}


def resolve_browser_launch_config(
    profile_dir: str | None = None,
    *,
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
        headless=headless,
    )


def detect_liepin_status(
    current_url: str,
    page_text: str,
) -> SiteStatus:
    """Infer stable Liepin session states from URL and visible text."""
    url = (current_url or "").lower()
    text = (page_text or "").strip()

    if any(token in text for token in ("滑动验证", "安全验证", "人机验证", "验证码")):
        return "captcha_required"
    if "login" in url or any(
        token in text for token in ("登录", "扫码登录", "账号登录")
    ):
        if "退出登录" not in text:
            return "not_logged_in"
    return "ok"


def preferred_liepin_home_url(current_url: str) -> str:
    """Return the safest home URL for recruiting flows."""
    hostname = urlparse(current_url or "").hostname or ""
    if hostname in _LIEPIN_RECRUITER_HOSTS:
        return f"https://{hostname}/"
    return _LIEPIN_PUBLIC_HOME_URL


def _is_liepin_url(url: str) -> bool:
    hostname = urlparse(url or "").hostname or ""
    return hostname.endswith("liepin.com")


def _is_liepin_recruiter_url(url: str) -> bool:
    hostname = urlparse(url or "").hostname or ""
    return hostname in _LIEPIN_RECRUITER_HOSTS


def _rewrite_pagination_url(
    current_url: str,
    page_number: int,
) -> str | None:
    """Rewrite well-known Liepin pagination params to the requested page."""
    parsed = urlparse(current_url or "")
    if not parsed.query:
        return None

    rewritten_pairs: list[tuple[str, str]] = []
    changed = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        new_value = value
        if key in _ONE_BASED_PAGE_QUERY_KEYS:
            new_value = str(page_number)
        elif key in _ZERO_BASED_PAGE_QUERY_KEYS:
            new_value = str(max(page_number - 1, 0))

        rewritten_pairs.append((key, new_value))
        if new_value != value:
            changed = True

    if not changed:
        return None

    return urlunparse(
        parsed._replace(
            query=urlencode(rewritten_pairs, doseq=True),
        ),
    )


class LiepinBrowserSession:
    """Manage a persistent Playwright browser profile for Liepin."""

    def __init__(self, launch_config: BrowserLaunchConfig) -> None:
        self.launch_config = launch_config
        self._playwright: Any | None = None
        self._context: Any | None = None

    async def ensure_started(self) -> Any:
        """Start the persistent browser context and return the active page."""
        if self._context is None:
            from playwright.async_api import async_playwright

            Path(self.launch_config.profile_dir).mkdir(
                parents=True,
                exist_ok=True,
            )
            self._playwright = await async_playwright().start()
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

            self._context = await browser_type.launch_persistent_context(
                **launch_kwargs,
            )

        pages = self._context.pages
        if pages:
            return self._select_active_page(pages)
        return await self._context.new_page()

    async def close(self) -> None:
        """Close the persistent browser context if it is running."""
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def check_status(self, page: Any | None = None) -> SiteStatus:
        """Check the current Liepin login/verification state."""
        active_page = page or await self.ensure_started()
        try:
            body_text = await active_page.locator("body").inner_text(
                timeout=3000,
            )
        except Exception:
            body_text = ""
        return detect_liepin_status(active_page.url, body_text)

    async def ensure_entry_page(self, page: Any | None = None) -> Any:
        """Open the public Liepin homepage unless already on a Liepin page."""
        active_page = page or await self.ensure_started()
        if _is_liepin_url(active_page.url or ""):
            return active_page

        await active_page.goto(_LIEPIN_PUBLIC_HOME_URL)
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
        """Search Liepin using the current page's visible search input."""
        if not _is_liepin_url(page.url or ""):
            await self.ensure_entry_page(page)
        elif (page.url or "").rstrip("/") != _LIEPIN_PUBLIC_HOME_URL.rstrip("/"):
            await self._goto_public_home(page)

        locator = await self._prepare_search_input(page)
        if locator is None:
            status = await self.check_status(page)
            if status != "ok":
                return status

            if (page.url or "").rstrip("/") != _LIEPIN_PUBLIC_HOME_URL.rstrip("/"):
                await self._goto_public_home(page)
                locator = await self._prepare_search_input(page)

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

    async def apply_query_filters(
        self,
        page: Any,
        query: Any,
        page_number: int = 1,
    ) -> dict[str, Any]:
        """Apply structured recruiter-page filters after keyword search."""
        applied_filters: dict[str, bool] = {}
        if not _is_liepin_recruiter_url(page.url or ""):
            return {
                "search_surface": "public",
                "trusted_site_filters": False,
                "applied_filters": applied_filters,
            }

        current_city = str(
            getattr(query, "current_city", "") or "",
        ).strip()
        if current_city:
            clicked = await self._click_filter_option(
                page,
                "目前城市",
                current_city,
            )
            applied_filters["current_city"] = clicked
            logger.info(
                "Liepin filter apply: section=%s option=%s clicked=%s",
                "目前城市",
                current_city,
                clicked,
            )

        expected_city = str(
            getattr(query, "expected_city", "") or "",
        ).strip()
        if expected_city:
            clicked = await self._click_filter_option(
                page,
                "期望城市",
                expected_city,
            )
            applied_filters["expected_city"] = clicked
            logger.info(
                "Liepin filter apply: section=%s option=%s clicked=%s",
                "期望城市",
                expected_city,
                clicked,
            )

        experience_label = _map_experience_filter_label(
            str(getattr(query, "experience", "") or ""),
        )
        if experience_label:
            clicked = await self._click_filter_option(
                page,
                "经验",
                experience_label,
            )
            custom_min_years = _extract_custom_experience_min_years(
                str(getattr(query, "experience", "") or ""),
            )
            if (
                clicked
                and experience_label == "自定义"
                and custom_min_years is not None
            ):
                clicked = await self._fill_custom_experience_min(
                    page,
                    custom_min_years,
                )
            applied_filters["experience"] = clicked
            logger.info(
                "Liepin filter apply: section=%s option=%s custom_min=%s clicked=%s",
                "经验",
                experience_label,
                custom_min_years,
                clicked,
            )

        education_label = _map_education_filter_label(
            str(getattr(query, "education", "") or ""),
        )
        if education_label:
            clicked = await self._click_filter_option(
                page,
                "教育经历",
                education_label,
            )
            applied_filters["education"] = clicked
            logger.info(
                "Liepin filter apply: section=%s option=%s clicked=%s",
                "教育经历",
                education_label,
                clicked,
            )

        if page_number > 1:
            await self._goto_page_number(page, page_number)

        return {
            "search_surface": "recruiter",
            "trusted_site_filters": True,
            "applied_filters": applied_filters,
        }

    async def _prepare_search_input(self, page: Any) -> Any | None:
        """Move to the candidate-search surface and return a visible input."""
        await self._ensure_candidate_search_surface(page)
        return await self._find_search_input(page)

    async def _goto_public_home(self, page: Any) -> None:
        """Reset the current tab back to the public Liepin homepage."""
        await page.goto(_LIEPIN_PUBLIC_HOME_URL)
        await page.wait_for_load_state(
            "domcontentloaded",
            timeout=10000,
        )
        await page.wait_for_timeout(800)

    async def _ensure_candidate_search_surface(self, page: Any) -> None:
        """Best-effort switch into the visible candidate-search tab first."""
        locator = await self._find_clickable_target(
            page,
            _SEARCH_TAB_SELECTORS,
        )
        if locator is None:
            return

        await locator.click()
        await page.wait_for_load_state(
            "domcontentloaded",
            timeout=10000,
        )
        await page.wait_for_timeout(800)

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
        if locator is not None:
            try:
                await locator.click()
                await self._wait_for_pagination_navigation(page)
                return
            except Exception:
                logger.debug(
                    "Liepin pagination locator click failed: page=%s",
                    page_number,
                    exc_info=True,
                )

        if await self._click_pagination_target_via_dom(page, page_number):
            await self._wait_for_pagination_navigation(page)
            return

        current_url = str(getattr(page, "url", "") or "")
        paginated_url = _rewrite_pagination_url(current_url, page_number)
        if not paginated_url or paginated_url == current_url:
            return

        try:
            await page.goto(paginated_url)
            await self._wait_for_pagination_navigation(page)
        except Exception:
            logger.debug(
                "Liepin pagination URL rewrite failed: from=%s to=%s",
                current_url,
                paginated_url,
                exc_info=True,
            )

    async def _wait_for_pagination_navigation(self, page: Any) -> None:
        """Wait for recruiter pagination to settle after a click or URL jump."""
        try:
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=10000,
            )
        except Exception:
            logger.debug(
                "Liepin pagination wait_for_load_state failed",
                exc_info=True,
            )

        try:
            await page.wait_for_timeout(1000)
        except Exception:
            logger.debug(
                "Liepin pagination wait_for_timeout failed",
                exc_info=True,
            )

    async def _click_pagination_target_via_dom(
        self,
        page: Any,
        page_number: int,
    ) -> bool:
        """Use a DOM-scoped pagination click when generic locators miss."""
        script = """
        ({ pageNumber }) => {
          const wanted = String(pageNumber);
          const normalize = (value) => (value || '').replace(/\\s+/g, '');
          const isVisible = (node) => {
            if (!node || !node.isConnected) return false;
            const style = window.getComputedStyle(node);
            if (!style || style.display === 'none' || style.visibility === 'hidden') {
              return false;
            }
            const rect = node.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };
          const attrMatches = (node) =>
            ['aria-label', 'data-page', 'data-page-num', 'data-page-number', 'title']
              .some((key) => normalize(node.getAttribute?.(key)) === wanted);
          const looksLikePagerContainer = (node) => {
            const text = normalize(node.innerText);
            if (!text || !text.includes(wanted)) return false;
            return (
              text.includes('上一页') ||
              text.includes('下一页') ||
              text.includes('prev') ||
              text.includes('Prev') ||
              text.includes('next') ||
              text.includes('Next')
            );
          };

          const directContainers = Array.from(
            document.querySelectorAll(
              [
                'nav',
                '[class*="pagination"]',
                '[class*="Pagination"]',
                '[class*="pager"]',
                '[class*="Pager"]',
                '.ant-pagination',
                '.el-pagination',
                '[data-testid*="pagination"]'
              ].join(',')
            )
          ).filter((node) => isVisible(node));

          const containers = directContainers.length
            ? directContainers
            : Array.from(document.querySelectorAll('nav, ul, ol, div, section'))
                .filter((node) => isVisible(node) && looksLikePagerContainer(node));

          for (const container of containers) {
            const nodes = [container, ...container.querySelectorAll('a, button, li, span, div')];
            for (const node of nodes) {
              if (!isVisible(node)) continue;
              const text = normalize(node.innerText);
              if (text === wanted || attrMatches(node)) {
                if (node instanceof HTMLElement) {
                  node.click();
                } else {
                  node.dispatchEvent(
                    new MouseEvent('click', {
                      bubbles: true,
                      cancelable: true,
                      view: window
                    })
                  );
                }
                return true;
              }
            }
          }

          return false;
        }
        """
        try:
            clicked = await page.evaluate(
                script,
                {"pageNumber": page_number},
            )
        except Exception:
            logger.debug(
                "Liepin DOM pagination click failed: page=%s",
                page_number,
                exc_info=True,
            )
            return False
        return bool(clicked)

    async def _click_filter_option(
        self,
        page: Any,
        section_title: str,
        option_text: str,
    ) -> bool:
        """Click a recruiter filter chip inside a titled filter section."""
        script = """
        ({ sectionTitle, optionText }) => {
          const normalize = (value) =>
            (value || '').replace(/\\s+/g, '').toLowerCase();

          const sections = Array.from(document.querySelectorAll('div.wrap--KUsNx'));
          for (const section of sections) {
            const titleNode = section.querySelector('span.title--ICYvO');
            if (!titleNode) continue;
            if (normalize(titleNode.innerText) !== normalize(sectionTitle)) continue;

            const options = Array.from(section.querySelectorAll('label'));
            for (const option of options) {
              if (normalize(option.innerText) === normalize(optionText)) {
                option.click();
                return true;
              }
            }
          }
          return false;
        }
        """
        for attempt in range(4):
            try:
                clicked = await page.evaluate(
                    script,
                    {
                        "sectionTitle": section_title,
                        "optionText": option_text,
                    },
                )
            except Exception:
                clicked = False

            if clicked:
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded",
                        timeout=3000,
                    )
                except Exception:
                    pass
                await page.wait_for_timeout(600)
                return True

            if attempt < 3:
                await page.wait_for_timeout(400)
        return False

    async def _fill_custom_experience_min(
        self,
        page: Any,
        min_years: int,
    ) -> bool:
        """Fill the recruiter custom-experience minimum and apply it."""
        script = """
        async ({ minYears }) => {
          const normalize = (value) =>
            (value || '').replace(/\\s+/g, '').toLowerCase();
          const isVisible = (node) => {
            if (!node || !node.isConnected) return false;
            const style = window.getComputedStyle(node);
            if (!style || style.display === 'none' || style.visibility === 'hidden') {
              return false;
            }
            const rect = node.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          };
          const isEditableInput = (node) =>
            node instanceof HTMLInputElement &&
            !node.disabled &&
            !node.readOnly &&
            node.type !== 'hidden' &&
            node.type !== 'checkbox' &&
            node.type !== 'radio';
          const nativeValueSetter =
            Object.getOwnPropertyDescriptor(
              window.HTMLInputElement.prototype,
              'value',
            )?.set;
          const waitForNextFrame = () =>
            new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
          const setValue = async (node, value) => {
            node.focus();
            node.click();
            node.select?.();
            if (nativeValueSetter) {
              nativeValueSetter.call(node, '');
            } else {
              node.value = '';
            }
            node.dispatchEvent(new InputEvent('input', {
              bubbles: true,
              data: '',
              inputType: 'deleteContentBackward',
            }));
            if (nativeValueSetter) {
              nativeValueSetter.call(node, String(value));
            } else {
              node.value = String(value);
            }
            node.dispatchEvent(new InputEvent('input', {
              bubbles: true,
              data: String(value),
              inputType: 'insertText',
            }));
            node.dispatchEvent(new Event('change', { bubbles: true }));
            node.dispatchEvent(new KeyboardEvent('keydown', {
              bubbles: true,
              key: 'Enter',
              code: 'Enter',
            }));
            node.dispatchEvent(new KeyboardEvent('keyup', {
              bubbles: true,
              key: 'Enter',
              code: 'Enter',
            }));
            node.blur();
            await waitForNextFrame();
            await waitForNextFrame();
            return String(node.value || '').trim() === String(value);
          };
          const rankInput = (node) => {
            const text = normalize(
              [
                node.getAttribute('placeholder'),
                node.getAttribute('aria-label'),
                node.getAttribute('name'),
                node.getAttribute('id'),
                node.closest('label, div, form')?.innerText,
              ].filter(Boolean).join(' '),
            );
            if (
              text.includes('搜索') ||
              text.includes('关键词') ||
              text.includes('职位') ||
              text.includes('公司') ||
              text.includes('行业')
            ) {
              return -5;
            }
            if (text.includes('最大') || text.includes('最高')) return -1;
            if (text.includes('最小') || text.includes('最低') || text.includes('起')) {
              return 6;
            }
            if (text.includes('年') || text.includes('经验')) return 4;
            if (node.closest('[role="dialog"], .ant-modal, .ant-popover, .ant-dropdown, .ant-drawer')) {
              return 3;
            }
            return 1;
          };

          const section = Array.from(document.querySelectorAll('div.wrap--KUsNx')).find(
            (node) => normalize(node.querySelector('span.title--ICYvO')?.innerText) === normalize('经验'),
          );
          const overlayRoots = Array.from(
            document.querySelectorAll(
              [
                '[role=\"dialog\"]',
                '.ant-modal',
                '.ant-popover',
                '.ant-dropdown',
                '.ant-drawer',
                '[class*=\"popover\"]',
                '[class*=\"modal\"]',
                '[class*=\"drawer\"]',
              ].join(','),
            ),
          ).filter(isVisible);

          const roots = [section, ...overlayRoots, document.body].filter(Boolean);
          const seen = new Set();
          const inputs = [];
          for (const root of roots) {
            for (const node of root.querySelectorAll('input')) {
              if (!isEditableInput(node) || !isVisible(node)) continue;
              if (seen.has(node)) continue;
              seen.add(node);
              inputs.push(node);
            }
          }
          inputs.sort((left, right) => rankInput(right) - rankInput(left));
          if (!inputs.length) {
            return {
              filled: false,
              reason: 'input_not_found',
            };
          }

          let target = null;
          for (const candidate of inputs) {
            const filled = await setValue(candidate, minYears);
            if (filled) {
              target = candidate;
              break;
            }
          }
          if (!target) {
            return {
              filled: false,
              reason: 'value_not_sticky',
            };
          }

          const confirmTexts = ['确定', '确认', '应用', '完成'];
          const confirmRoot = overlayRoots[0] || section || document.body;
          const clickable = Array.from(
            confirmRoot.querySelectorAll('button, a, span, div'),
          ).filter(isVisible);
          const confirm = clickable.find((node) =>
            confirmTexts.some((text) => normalize(node.innerText) === normalize(text)),
          );
          if (confirm) {
            confirm.click();
          } else if (target.form && typeof target.form.requestSubmit === 'function') {
            target.form.requestSubmit();
          }
          return {
            filled: true,
            reason: 'ok',
            value: String(target.value || ''),
          };
        }
        """
        for attempt in range(4):
            try:
                outcome = await page.evaluate(
                    script,
                    {
                        "minYears": min_years,
                    },
                )
            except Exception:
                outcome = False

            if isinstance(outcome, dict):
                filled = bool(outcome.get("filled"))
            else:
                filled = bool(outcome)

            if filled:
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded",
                        timeout=3000,
                    )
                except Exception:
                    pass
                await page.wait_for_timeout(800)
                return True

            if attempt < 3:
                await page.wait_for_timeout(400)
        return False

    @staticmethod
    def _select_active_page(pages: list[Any]) -> Any:
        """Prefer the newest recruiter tab before falling back to public tabs."""
        for page in reversed(pages):
            if _is_liepin_recruiter_url(
                str(getattr(page, "url", "") or ""),
            ):
                return page
        for page in reversed(pages):
            if _is_liepin_url(str(getattr(page, "url", "") or "")):
                return page
        return pages[-1]


def _map_experience_filter_label(experience_text: str) -> str:
    """Map experience text into either a quick bucket or the custom control."""
    text = str(experience_text or "").strip()
    if not text:
        return ""
    if any(token in text for token in ("在校", "应届")):
        return "在校/应届"

    if _is_explicit_experience_bucket(text):
        normalized = re.sub(r"\s+", "", text)
        for label in ("1-3年", "3-5年", "5-10年"):
            if re.sub(r"\s+", "", label) in normalized:
                return label

    match = re.search(r"(\d+)", text)
    if not match:
        return ""
    return "自定义"


def _extract_custom_experience_min_years(
    experience_text: str,
) -> int | None:
    """Return the minimum-year value for custom experience filters."""
    if _map_experience_filter_label(experience_text) != "自定义":
        return None

    match = re.search(r"(\d+)", str(experience_text or "").strip())
    if not match:
        return None
    return int(match.group(1))


def _is_explicit_experience_bucket(experience_text: str) -> bool:
    """Detect recruiter-native bucket ranges like 3-5年."""
    normalized = re.sub(r"\s+", "", str(experience_text or "").lower())
    bucket_patterns = (
        r"1[-~至到]3年?",
        r"3[-~至到]5年?",
        r"5[-~至到]10年?",
    )
    return any(re.search(pattern, normalized) for pattern in bucket_patterns)


def _map_education_filter_label(education_text: str) -> str:
    """Map a normalized education query into the recruiter page's label text."""
    normalized = str(education_text or "").strip().lower()
    mapping = {
        "bachelor": "本科",
        "master": "硕士",
        "phd": "博士/博士后",
        "doctor": "博士/博士后",
    }
    for source, target in mapping.items():
        if source in normalized:
            return target
    for label in ("本科", "硕士", "博士/博士后", "大专", "中专/中技", "高中及以下"):
        if label in education_text:
            return label
    return ""
