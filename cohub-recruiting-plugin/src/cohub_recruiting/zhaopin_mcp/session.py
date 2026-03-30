# -*- coding: utf-8 -*-
"""Persistent browser session helpers for the Zhaopin MCP adapter."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

from copaw.config.utils import (
    get_playwright_chromium_executable_path,
    get_system_default_browser,
)

from cohub_recruiting.models import SiteStatus
from .models import BrowserLaunchConfig

_DEFAULT_PROFILE_DIR = (
    Path.home() / ".copaw" / "recruiting" / "zhaopin-profile"
)
_ZHAOPIN_HOME_URL = "https://rd6.zhaopin.com/"
_ZHAOPIN_HOME_PATHS = {"", "/", "/app/index"}
_ZHAOPIN_HOST_SUFFIX = "zhaopin.com"
_SEARCH_TAB_SELECTORS = [
    "text=搜索人才",
    "[role='tab']:has-text('搜索人才')",
    "button:has-text('搜索人才')",
    "a:has-text('搜索人才')",
]
_SEARCH_INPUT_SELECTORS = [
    "input[placeholder*='搜索人才']",
    "input[placeholder*='搜索简历']",
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


def detect_zhaopin_status(
    current_url: str,
    page_text: str,
) -> SiteStatus:
    """Infer stable Zhaopin session states from URL and visible text."""
    url = (current_url or "").lower()
    text = (page_text or "").strip()
    recruiter_surface_tokens = ("搜索人才", "搜索简历", "人才搜索")

    if any(token in text for token in ("验证码", "滑动验证", "安全验证", "人机验证")):
        return "captcha_required"
    if any(token in text for token in recruiter_surface_tokens):
        return "ok"
    if "login" in url or any(token in text for token in ("登录", "扫码登录", "账号登录")):
        if "退出登录" not in text:
            return "not_logged_in"
    return "ok"


def _is_zhaopin_url(url: str) -> bool:
    hostname = urlparse(url or "").hostname or ""
    return hostname.endswith(_ZHAOPIN_HOST_SUFFIX)


def _is_zhaopin_home_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return _is_zhaopin_url(url) and (parsed.path or "/") in _ZHAOPIN_HOME_PATHS


class ZhaopinBrowserSession:
    """Manage a persistent Playwright browser profile for Zhaopin recruiter flows."""

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

        pw = await async_playwright().start()
        try:
            if self.launch_config.cdp_url:
                self._browser = await pw.chromium.connect_over_cdp(
                    self.launch_config.cdp_url,
                )
                contexts = getattr(self._browser, "contexts", []) or []
                if contexts:
                    self._playwright = pw
                    return contexts[0]
                ctx = await self._browser.new_context()
                self._playwright = pw
                return ctx

            Path(self.launch_config.profile_dir).mkdir(
                parents=True,
                exist_ok=True,
            )
            browser_type = getattr(
                pw,
                self.launch_config.browser_kind,
                pw.chromium,
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

            ctx = await browser_type.launch_persistent_context(**launch_kwargs)
            self._playwright = pw
            return ctx
        except Exception:
            await pw.stop()
            raise

    async def close(self) -> None:
        """Close the running browser context if present."""
        try:
            if self._context is not None and not self.launch_config.cdp_url:
                try:
                    await self._context.close()
                except Exception:
                    pass
        finally:
            self._context = None
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    async def __aenter__(self):
        await self.ensure_started()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def check_status(self, page: Any | None = None) -> SiteStatus:
        """Check the current Zhaopin login/verification state."""
        active_page = page or await self.ensure_started()
        if active_page is None:
            return "internal_error"

        try:
            body_text = await active_page.locator("body").inner_text(
                timeout=3000,
            )
        except Exception:
            body_text = ""
        return detect_zhaopin_status(getattr(active_page, "url", ""), body_text)

    async def ensure_entry_page(self, page: Any | None = None) -> Any:
        """Open the Zhaopin recruiter home page unless already on a Zhaopin tab."""
        active_page = page or await self.ensure_started()
        if _is_zhaopin_url(getattr(active_page, "url", "")):
            return active_page

        await active_page.goto(_ZHAOPIN_HOME_URL)
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
        """Search Zhaopin using the visible recruiter talent-search input."""
        current_url = str(getattr(page, "url", "") or "")
        if not _is_zhaopin_url(current_url):
            page = await self.ensure_entry_page(page)
        elif not _is_zhaopin_home_url(current_url):
            await self._goto_recruiter_home(page)

        await self._ensure_candidate_search_surface(page)
        locator = await self._find_search_input(page)
        if locator is None:
            status = await self.check_status(page)
            if status != "ok":
                return status
            return "site_layout_changed"

        await self._focus_search_input(locator)
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
        """Apply supported recruiter-page filters after the keyword search."""
        applied_filters: dict[str, bool] = {}
        if not _is_zhaopin_url(str(getattr(page, "url", "") or "")):
            return {
                "search_surface": "public",
                "trusted_site_filters": False,
                "applied_filters": applied_filters,
            }

        results_signature = await self._capture_results_signature(page)

        expected_city = str(getattr(query, "expected_city", "") or "").strip()
        if expected_city:
            applied_filters["expected_city"] = await self._apply_expected_city_filter(
                page,
                expected_city,
            )

        current_city = str(getattr(query, "current_city", "") or "").strip()
        if current_city:
            applied_filters["current_city"] = await self._apply_current_city_filter(
                page,
                current_city,
            )

        experience_label = _map_experience_filter_label(
            str(getattr(query, "experience", "") or ""),
        )
        if experience_label:
            applied_filters["experience"] = await self._click_labeled_filter_option(
                page,
                "经验要求",
                experience_label,
            )

        education_label = _map_education_filter_label(
            str(getattr(query, "education", "") or ""),
        )
        if education_label:
            applied_filters["education"] = await self._click_labeled_filter_option(
                page,
                "学历要求",
                education_label,
            )

        if any(applied_filters.values()):
            results_signature = await self._wait_for_results_refresh(
                page,
                results_signature,
            )

        if page_number > 1:
            await self._goto_page_number(page, page_number)
            await self._wait_for_results_refresh(
                page,
                results_signature,
            )

        return {
            "search_surface": "recruiter",
            "trusted_site_filters": True,
            "applied_filters": applied_filters,
        }

    async def _capture_results_signature(
        self,
        page: Any,
    ) -> tuple[str, ...]:
        """Capture a compact signature for the first visible candidate cards."""
        script = """
        () => {
          const normalize = (value) =>
            (value || '').replace(/\\s+/g, ' ').trim();
          return Array.from(
            document.querySelectorAll('.search-resume-item-wrap')
          )
            .slice(0, 5)
            .map((card) => {
              const detailHref = Array.from(
                card.querySelectorAll('a[href*="resumeNumber="]')
              )
                .map((node) => node.getAttribute('href') || '')
                .find(Boolean) || '';
              const name = normalize(
                card.querySelector('.talent-basic-info__name--inner')?.textContent ||
                ''
              );
              const summary = normalize(card.textContent || '').slice(0, 240);
              return [name, detailHref, summary].filter(Boolean).join('|');
            })
            .filter(Boolean);
        }
        """
        try:
            signature = await page.evaluate(script)
        except Exception:
            return ()
        return tuple(
            str(item or "").strip()
            for item in (signature or [])
            if str(item or "").strip()
        )

    async def _wait_for_results_refresh(
        self,
        page: Any,
        previous_signature: tuple[str, ...],
        *,
        attempts: int = 18,
        interval_ms: int = 400,
    ) -> tuple[str, ...]:
        """Wait until the candidate list changes and then stabilizes."""
        last_signature: tuple[str, ...] = ()
        stable_reads = 0

        for attempt in range(max(attempts, 1)):
            current_signature = await self._capture_results_signature(page)
            signature_changed = bool(current_signature) and (
                not previous_signature or current_signature != previous_signature
            )
            if signature_changed:
                if current_signature == last_signature:
                    stable_reads += 1
                else:
                    last_signature = current_signature
                    stable_reads = 1
                if stable_reads >= 3:
                    return current_signature
            elif current_signature:
                last_signature = current_signature
                stable_reads = 0

            if attempt < attempts - 1:
                try:
                    await page.wait_for_timeout(interval_ms)
                except Exception:
                    break

        final_signature = await self._capture_results_signature(page)
        return final_signature or last_signature or previous_signature

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

    async def _goto_recruiter_home(self, page: Any) -> None:
        """Reset the current tab to the recruiter home page before a new search."""
        await page.goto(_ZHAOPIN_HOME_URL)
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

    async def _focus_search_input(self, locator: Any) -> None:
        """Best-effort focus for editable inputs with overlay placeholders."""
        try:
            await locator.click(timeout=1500)
            return
        except TypeError:
            pass
        except Exception:
            return

        try:
            await locator.click()
        except Exception:
            return

    async def _apply_expected_city_filter(
        self,
        page: Any,
        city: str,
    ) -> bool:
        """Use the top keyword city selector for expected-city filtering."""
        if await self._condition_chip_matches(
            page,
            "期望工作地",
            city,
        ):
            return True
        if await self._select_keyword_panel_city(page, city):
            return True
        return False

    async def _apply_current_city_filter(
        self,
        page: Any,
        city: str,
    ) -> bool:
        """Use the visible 现居住地 dropdown for current-city filtering."""
        return await self._click_other_dropdown_option(
            page,
            "现居住地",
            city,
        )

    async def _click_labeled_filter_option(
        self,
        page: Any,
        section_title: str,
        option_text: str,
    ) -> bool:
        """Click a visible option inside a titled Zhaopin filter block."""
        script = """
        ({ sectionTitle, optionText }) => {
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
          const clickableSelector = [
            '.search-education-new__selector-item',
            '.button-group__list-item',
            '.search-school-nature-new__item',
            'button',
            'label',
            'div',
            'span'
          ].join(',');

          const sections = Array.from(document.querySelectorAll('.search-label-wrapper-new'));
          for (const section of sections) {
            const labelNode = section.querySelector('.search-label-wrapper-new__label');
            if (!labelNode) continue;
            if (normalize(labelNode.innerText) !== normalize(sectionTitle)) continue;

            const nodes = Array.from(section.querySelectorAll(clickableSelector));
            for (const node of nodes) {
              if (!isVisible(node)) continue;
              if (normalize(node.innerText) !== normalize(optionText)) continue;
              const clickable =
                node.closest('.search-education-new__selector-item, .button-group__list-item, .search-school-nature-new__item, button, label, div') ||
                node;
              clickable.click();
              return true;
            }
          }
          return false;
        }
        """
        for attempt in range(3):
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
                try:
                    await page.wait_for_timeout(600)
                except Exception:
                    pass
                return True
            if attempt < 2:
                try:
                    await page.wait_for_timeout(300)
                except Exception:
                    break
        return False

    async def _select_keyword_panel_city(
        self,
        page: Any,
        city: str,
    ) -> bool:
        """Open the top city selector and choose a visible city option."""
        trigger = await self._find_clickable_target(
            page,
            [
                ".keyword-panel-city__label",
                ".keyword-panel-city",
                ".keyword-panel__city",
            ],
        )
        if trigger is None:
            return False
        try:
            await trigger.click()
        except Exception:
            return False
        try:
            await page.wait_for_timeout(500)
        except Exception:
            pass
        await self._clear_keyword_panel_selected_cities(page)
        clicked = await self._click_keyword_panel_city_option(page, city)
        if not clicked:
            return False
        return await self._confirm_keyword_panel_city_selection(page)

    async def _clear_keyword_panel_selected_cities(
        self,
        page: Any,
    ) -> int:
        """Remove previously selected cities from the keyword-panel modal."""
        removed = 0
        close_icons = page.locator(".s-dialog .s-tags__close")
        for _ in range(10):
            try:
                if await close_icons.count() <= 0:
                    break
                await close_icons.first.click(timeout=1500)
                removed += 1
                await page.wait_for_timeout(150)
            except Exception:
                break
        return removed

    async def _click_keyword_panel_city_option(
        self,
        page: Any,
        city: str,
    ) -> bool:
        """Select a city option from the keyword-panel modal."""
        search_input = page.locator(
            ".s-dialog input[placeholder*='搜索城市名/区县']",
        )
        try:
            if await search_input.count() > 0:
                await search_input.first.fill("")
                await search_input.first.fill(city)
                await page.wait_for_timeout(250)
        except Exception:
            pass
        search_result_locator = page.locator(
            f".s-search-select__popover .s-option:has-text('{city}')",
        )
        try:
            if await search_result_locator.count() > 0:
                await search_result_locator.first.click(timeout=1500)
                await page.wait_for_timeout(300)
                return True
        except Exception:
            pass
        city_locator = page.locator(
            f".s-dialog .s-cascader__option:has(.s-cascader__option-content[title='{city}'])",
        )
        try:
            if await city_locator.count() > 0:
                await city_locator.first.click(timeout=1500)
                await page.wait_for_timeout(250)
        except Exception:
            pass

        full_city_locator = page.locator(
            f".s-dialog .s-checkbutton__item:has-text('全{city}')",
        )
        try:
            if await full_city_locator.count() > 0:
                await full_city_locator.first.click(timeout=1500)
                await page.wait_for_timeout(300)
                return True
        except Exception:
            pass

        try:
            if await city_locator.count() > 0:
                await city_locator.first.click(timeout=1500)
                await page.wait_for_timeout(300)
                return True
        except Exception:
            pass
        return False

    async def _confirm_keyword_panel_city_selection(
        self,
        page: Any,
    ) -> bool:
        """Confirm the keyword-panel city modal selection."""
        try:
            confirm_button = page.locator(
                ".s-dialog .s-cascader__footer-button.s-button--primary",
            )
            if await confirm_button.count() <= 0:
                return False
            await confirm_button.first.click(timeout=1500)
            confirmed = True
        except Exception:
            confirmed = False
        if not confirmed:
            return False
        try:
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=3000,
            )
        except Exception:
            pass
        try:
            await page.wait_for_timeout(700)
        except Exception:
            pass
        return True

    async def _click_other_dropdown_option(
        self,
        page: Any,
        trigger_text: str,
        option_text: str,
    ) -> bool:
        """Open a visible dropdown-style filter and select an option by text."""
        script = """
        ({ triggerText }) => {
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
          const nodes = Array.from(
            document.querySelectorAll('.talent-search-other-label, .filter-other-city, .search-selector, .keyword-panel-city')
          );
          for (const node of nodes) {
            if (!isVisible(node)) continue;
            const text = normalize(node.innerText);
            if (!text.includes(normalize(triggerText))) continue;
            const clickable =
              node.closest('.filter-other__item, .search-selector, .filter-other-city, .keyword-panel-city') ||
              node;
            clickable.click();
            return true;
          }
          return false;
        }
        """
        try:
            opened = await page.evaluate(
                script,
                {"triggerText": trigger_text},
            )
        except Exception:
            opened = False
        if not opened:
            return False
        try:
            await page.wait_for_timeout(500)
        except Exception:
            pass
        return await self._click_visible_option(page, option_text)

    async def _click_visible_option(
        self,
        page: Any,
        option_text: str,
    ) -> bool:
        """Click the most likely visible popover/dropdown option by exact text."""
        script = """
        ({ optionText }) => {
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
          const shouldIgnore = (node) => !!node.closest(
            '.search-resume-item-wrap, .search-condition-result-new, .app-nav, .keyword-panel__recommend'
          );
          const scoreNode = (node) => {
            const classText = [
              node.className || '',
              node.parentElement?.className || '',
              node.closest('[class]')?.className || '',
            ].join(' ').toLowerCase();
            let score = 0;
            for (const token of ['popover', 'popper', 'dropdown', 'option', 'select', 'menu', 'city', 'item', 'panel']) {
              if (classText.includes(token)) score += 2;
            }
            if (node.getAttribute('role') === 'option') score += 4;
            if (node.tagName === 'LI' || node.tagName === 'BUTTON' || node.tagName === 'LABEL') score += 2;
            return score;
          };

          const matches = Array.from(document.querySelectorAll('li, button, label, div, span, a'))
            .filter((node) => isVisible(node) && !shouldIgnore(node))
            .filter((node) => normalize(node.innerText) === normalize(optionText))
            .sort((left, right) => scoreNode(right) - scoreNode(left));

          const target = matches[0];
          if (!target) return false;
          const clickable =
            target.closest('[role=\"option\"], li, button, label, a, div') ||
            target;
          clickable.click();
          return true;
        }
        """
        for attempt in range(4):
            try:
                clicked = await page.evaluate(
                    script,
                    {"optionText": option_text},
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
                try:
                    await page.wait_for_timeout(700)
                except Exception:
                    pass
                return True
            if attempt < 3:
                try:
                    await page.wait_for_timeout(300)
                except Exception:
                    break
        return False

    async def _condition_chip_matches(
        self,
        page: Any,
        label: str,
        value: str,
    ) -> bool:
        """Check whether a visible condition chip already contains the desired value."""
        script = """
        () => Array.from(
          document.querySelectorAll('.search-condition-result-new__item span')
        ).map((node) => (node.innerText || '').trim()).filter(Boolean)
        """
        try:
            chip_texts = await page.evaluate(script)
        except Exception:
            return False
        label_normalized = re.sub(r"\s+", "", str(label or "").lower())
        value_normalized = re.sub(r"\s+", "", str(value or "").lower())
        if not label_normalized or not value_normalized:
            return False

        for chip_text in chip_texts or []:
            text = str(chip_text or "").strip()
            normalized_text = re.sub(r"\s+", "", text.lower())
            if label_normalized not in normalized_text:
                continue
            actual_value = text
            for separator in ("：", ":"):
                if separator in text:
                    actual_value = text.split(separator, 1)[1]
                    break
            actual_normalized = re.sub(
                r"\s+",
                "",
                str(actual_value or "").lower(),
            )
            if actual_normalized == value_normalized:
                return True
        return False

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
        """Prefer the newest Zhaopin tab before falling back to the newest page."""
        for page in reversed(pages):
            if _is_zhaopin_url(str(getattr(page, "url", "") or "")):
                return page
        return pages[-1]


def _map_experience_filter_label(experience_text: str) -> str:
    """Map experience text onto Zhaopin's visible quick buckets."""
    normalized = re.sub(r"\s+", "", str(experience_text or "").lower())
    if not normalized:
        return ""
    if any(token in normalized for token in ("应届", "在校")):
        return "无经验"
    if re.search(r"1[-~至到]3年?", normalized):
        return "1-3年"
    if re.search(r"3[-~至到]5年?", normalized):
        return "3-5年"
    if re.search(r"5[-~至到]10年?", normalized):
        return "5-10年"

    match = re.search(r"(\d+)", normalized)
    if not match:
        return ""
    years = int(match.group(1))
    if years <= 0:
        return "无经验"
    if years <= 3:
        return "1-3年"
    if years <= 5:
        return "3-5年"
    return "5-10年"


def _map_education_filter_label(education_text: str) -> str:
    """Map normalized education text onto Zhaopin's visible labels."""
    normalized = str(education_text or "").strip().lower()
    if not normalized:
        return ""
    if "博士" in education_text or "phd" in normalized or "doctor" in normalized:
        return ""
    if "硕士" in education_text or "master" in normalized:
        return "硕士及以上"
    if "本科" in education_text or "bachelor" in normalized:
        return "本科及以上"
    if "大专" in education_text or "associate" in normalized:
        return "大专及以上"
    return ""
