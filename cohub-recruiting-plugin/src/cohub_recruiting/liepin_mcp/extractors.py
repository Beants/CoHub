# -*- coding: utf-8 -*-
"""Candidate extraction helpers for Liepin search pages."""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qs
from urllib.parse import urljoin
from urllib.parse import urlparse

from cohub_recruiting.models import CandidateSummary

_EDUCATION_KEYWORDS = (
    "博士",
    "硕士",
    "本科",
    "大专",
    "中专",
    "MBA",
    "EMBA",
)
_COMMON_CITIES = {
    "上海",
    "北京",
    "广州",
    "深圳",
    "杭州",
    "苏州",
    "南京",
    "成都",
    "武汉",
    "西安",
    "天津",
    "重庆",
    "长沙",
    "青岛",
    "厦门",
    "宁波",
    "郑州",
    "合肥",
    "福州",
    "济南",
    "大连",
    "东莞",
    "佛山",
    "无锡",
    "沈阳",
    "长春",
    "哈尔滨",
}
_CARD_SELECTORS = [
    "li[data-resumeurl]",
    "[data-resumeurl*='showresumedetail']",
    "[data-testid*='candidate']",
    "[class*='candidate']",
    "[class*='resume']",
    "[class*='card']",
    "li",
    "article",
]
_LINK_HINTS = [
    "/cvview/showresumedetail",
    "/resume/",
    "/candidate/",
    "/talent/",
    "/profile/",
    "/resume-detail",
    "/resumeDetail",
    "/detail/",
    "/detail?",
    "/view/",
]
_GENERIC_SEARCH_PATHS = {
    "",
    "/",
    "/search",
}
_NOISE_TOKENS = (
    "共有",
    "份简历",
    "立即沟通",
    "浏览简历",
    "全选",
    "活跃状态",
    "隐藏 活跃状态",
)
_RESUME_CARD_PATTERN = re.compile(
    r"<li\b(?P<attrs>[^>]*\bdata-resumeurl=(?P<quote>[\"'])"
    r"(?P<resume_url>.*?showresumedetail.*?)"
    r"(?P=quote)[^>]*)>(?P<body>.*?)</li>",
    re.IGNORECASE | re.DOTALL,
)


def parse_candidate_card(
    raw_text: str,
    *,
    detail_url: str,
    site: str,
    page: int,
    rank: int,
) -> CandidateSummary | None:
    """Convert a raw card text block into a structured candidate summary."""
    cleaned = _clean_card_text(raw_text)
    if not cleaned:
        return None

    lines = [line for line in cleaned.split("\n") if line]
    name = _extract_display_name(lines)
    if not name:
        return None

    role = _extract_role(lines, name)
    city = _extract_city(cleaned)
    years_experience = _extract_experience(cleaned)
    education = _extract_education(cleaned)

    headline_parts = [
        part
        for part in (role, city, years_experience, education)
        if part
    ]
    headline = " / ".join(headline_parts) if headline_parts else cleaned

    return CandidateSummary(
        site=site,
        candidate_id=_candidate_id_from_url(detail_url, rank),
        display_name=name,
        headline=headline,
        city=city,
        years_experience=years_experience,
        education=education,
        detail_url=detail_url,
        page=page,
        rank=rank,
    )


def candidate_summary_is_reliable(candidate: CandidateSummary) -> bool:
    """Return ``True`` only for candidate summaries that look card-shaped."""
    display_name = (candidate.display_name or "").strip()
    detail_url = (candidate.detail_url or "").strip()

    if not display_name:
        return False
    if candidate.candidate_id == "search":
        return False
    if _is_generic_search_detail_url(detail_url):
        return False
    if len(display_name) > 80:
        return False
    if any(token in display_name for token in _NOISE_TOKENS):
        return False
    if display_name.startswith(("共有 ", "期望：", "立即沟通", "全选")):
        return False
    return True


def candidate_batch_is_reliable(candidates: list[CandidateSummary]) -> bool:
    """Detect whether the extracted candidate batch is trustworthy enough."""
    if not candidates:
        return True
    reliable_count = sum(
        1 for candidate in candidates if candidate_summary_is_reliable(candidate)
    )
    if reliable_count == 0:
        return False
    return reliable_count * 2 >= len(candidates)


async def extract_candidates_from_page(
    page: Any,
    page_number: int,
    max_cards: int,
) -> list[CandidateSummary]:
    """Extract candidate summaries from the current Liepin page."""
    raw_cards = await _collect_raw_cards_from_page(page, max_cards)
    summaries: list[CandidateSummary] = []
    for index, card in enumerate(raw_cards, start=1):
        detail_url = urljoin(
            page.url,
            str(card.get("href") or card.get("detail_url") or ""),
        )
        summary = _build_candidate_summary_from_card(
            card,
            detail_url=detail_url,
            site="liepin",
            page=page_number,
            rank=index,
        )
        if summary is not None:
            summaries.append(summary)
    return summaries


async def extract_total_from_page(page: Any) -> int:
    """Best-effort parse the total result count from the visible page text."""
    try:
        text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return 0

    patterns = [
        r"共有\s*(\d+)\s*份简历",
        r"共\s*(\d+)\s*位",
        r"共\s*(\d+)\s*条",
        r"找到\s*(\d+)\s*位",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return 0


async def capture_extraction_debug_snapshot(
    page: Any,
    max_cards: int,
) -> dict[str, Any]:
    """Capture bounded page evidence for debugging unreliable extraction."""
    raw_cards = await _collect_raw_cards_from_page(page, max_cards)

    try:
        title = await page.title()
    except Exception:
        title = ""

    try:
        body_text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""

    try:
        html = await page.content()
    except Exception:
        html = ""

    return {
        "url": getattr(page, "url", ""),
        "title": title,
        "body_text": body_text[:20000],
        "raw_cards": raw_cards,
        "html": html[:200000],
    }


async def _collect_raw_cards_from_page(
    page: Any,
    max_cards: int,
) -> list[dict[str, str]]:
    """Collect raw candidate card blocks from the current page."""
    try:
        html_content = await page.content()
    except Exception:
        html_content = ""

    html_cards = _collect_raw_cards_from_html(html_content, max_cards)
    if html_cards:
        return html_cards

    script = """
    ({ selectors, linkHints, maxCards }) => {
      const seen = new Set();
      const out = [];

      const hrefLooksUseful = (href) =>
        !!href && linkHints.some((hint) => href.includes(hint));

      const pushNode = (node) => {
        if (!node || out.length >= maxCards) return;
        const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
        if (!text || text.length < 6) return;

        let href = (
          node.getAttribute('data-resumeurl') ||
          node.dataset?.resumeurl ||
          ''
        );
        const links = Array.from(node.querySelectorAll('a[href]'));
        if (!href) {
          for (const link of links) {
            const candidateHref = link.href || '';
            if (hrefLooksUseful(candidateHref)) {
              href = candidateHref;
              break;
            }
          }
        }
        if (!href && links.length > 0) {
          href = links[0].href || '';
        }

        const key = `${href}::${text}`;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({ href, text });
      };

      for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        for (const node of nodes) {
          if (out.length >= maxCards) break;
          pushNode(node);
        }
        if (out.length >= maxCards) break;
      }

      if (out.length === 0) {
        const links = Array.from(document.querySelectorAll('a[href]'));
        for (const link of links) {
          if (!hrefLooksUseful(link.href || '')) continue;
          pushNode(link.closest('li,article,section,div') || link);
          if (out.length >= maxCards) break;
        }
      }

      return out.slice(0, maxCards);
    }
    """
    return await page.evaluate(
        script,
        {
            "selectors": _CARD_SELECTORS,
            "linkHints": _LINK_HINTS,
            "maxCards": max_cards,
        },
    )


def _build_candidate_summary_from_card(
    card: dict[str, Any],
    *,
    detail_url: str,
    site: str,
    page: int,
    rank: int,
) -> CandidateSummary | None:
    """Create a candidate summary from structured card data when available."""
    display_name = str(card.get("display_name", "") or "").strip()
    if display_name:
        city = str(card.get("city", "") or "").strip()
        expected_city = str(card.get("expected_city", "") or "").strip()
        years_experience = str(card.get("years_experience", "") or "").strip()
        education = str(card.get("education", "") or "").strip()
        expected_title = str(card.get("expected_title", "") or "").strip()
        expected_salary = str(card.get("expected_salary", "") or "").strip()
        current_company = str(card.get("current_company", "") or "").strip()
        current_title = str(card.get("current_title", "") or "").strip()
        highlights = [
            item
            for item in card.get("highlights", [])
            if isinstance(item, str) and item.strip()
        ]
        headline_parts = [
            part
            for part in (
                expected_title or current_title,
                city,
                years_experience,
                education,
            )
            if part
        ]
        headline = " / ".join(headline_parts) if headline_parts else display_name
        return CandidateSummary(
            site=site,
            candidate_id=str(card.get("candidate_id") or "")
            or _candidate_id_from_url(detail_url, rank),
            display_name=display_name,
            headline=headline,
            city=city,
            expected_city=expected_city,
            years_experience=years_experience,
            education=education,
            current_company=current_company,
            current_title=current_title,
            expected_title=expected_title,
            expected_salary=expected_salary,
            highlights=highlights,
            detail_url=detail_url,
            page=page,
            rank=rank,
        )

    return parse_candidate_card(
        str(card.get("text", "") or ""),
        detail_url=detail_url,
        site=site,
        page=page,
        rank=rank,
    )


def _collect_raw_cards_from_html(
    html_content: str,
    max_cards: int,
) -> list[dict[str, Any]]:
    """Extract structured resume cards from recruiter search HTML."""
    if not html_content:
        return []

    cards: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for match in _RESUME_CARD_PATTERN.finditer(html_content):
        detail_url = html.unescape(match.group("resume_url")).strip()
        if not detail_url or detail_url in seen_urls:
            continue
        seen_urls.add(detail_url)

        attrs = match.group("attrs")
        body = match.group("body")
        skills_block = _first_match(
            body,
            r"<div[^>]*class=(['\"]).*?nest-resume-personal-skills.*?\1[^>]*>"
            r"(?P<inner>.*?)</div>",
            group="inner",
        )
        expected_match = re.search(
            r"<span[^>]*class=(['\"]).*?personal-expect-content.*?\1[^>]*>\s*"
            r"<span[^>]*>(.*?)</span>\s*"
            r"<span[^>]*>(.*?)</span>\s*"
            r"<span[^>]*>(.*?)</span>",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        expected_parts = (
            [_clean_html_text(group) for group in expected_match.groups()[1:]]
            if expected_match
            else ["", "", ""]
        )

        highlight_items = []
        active_status = _first_match(
            body,
            r"<span[^>]*class=(['\"]).*?nest-resume-offline.*?\1[^>]*>.*?"
            r"<em[^>]*>(.*?)</em>",
        )
        if active_status:
            highlight_items.append(_clean_html_text(active_status))
        if skills_block:
            highlight_items.extend(
                skill
                for skill in (
                    _clean_html_text(item)
                    for item in re.findall(
                        r"<span[^>]*>(.*?)</span>",
                        skills_block,
                        re.IGNORECASE | re.DOTALL,
                    )
                )
                if skill
            )

        text_parts = [
            _clean_html_text(
                _first_match(
                    body,
                    r"<div[^>]*class=(['\"]).*?nest-resume-personal-name.*?\1[^>]*>"
                    r".*?<em[^>]*>(.*?)</em>",
                ),
            ),
            expected_parts[1],
            " ".join(
                part
                for part in (
                    _clean_html_text(
                        _first_match(
                            body,
                            r"<span[^>]*class=(['\"]).*?personal-detail-dq.*?\1[^>]*>(.*?)</span>",
                        ),
                    ),
                    _clean_html_text(
                        _first_match(
                            body,
                            r"<span[^>]*class=(['\"]).*?personal-detail-workyears.*?\1[^>]*>(.*?)</span>",
                        ),
                    ),
                    _clean_html_text(
                        _first_match(
                            body,
                            r"<span[^>]*class=(['\"]).*?personal-detail-edulevel.*?\1[^>]*>(.*?)</span>",
                        ),
                    ),
                )
                if part
            ),
            _clean_html_text(
                _first_match(
                    body,
                    r"<span[^>]*class=(['\"]).*?work-item-compname.*?\1[^>]*>(.*?)</span>",
                ),
            ),
            _clean_html_text(
                _first_match(
                    body,
                    r"<span[^>]*class=(['\"]).*?work-item-extra.*?\1[^>]*>\s*"
                    r"<span[^>]*>(.*?)</span>",
                ),
            ),
        ]

        cards.append(
            {
                "href": detail_url,
                "candidate_id": _clean_html_text(
                    _extract_attr(attrs, "data-resumeidencode"),
                ),
                "display_name": _clean_html_text(
                    _first_match(
                        body,
                        r"<div[^>]*class=(['\"]).*?nest-resume-personal-name.*?\1[^>]*>"
                        r".*?<em[^>]*>(.*?)</em>",
                    ),
                ),
                "city": _clean_html_text(
                    _first_match(
                        body,
                        r"<span[^>]*class=(['\"]).*?personal-detail-dq.*?\1[^>]*>(.*?)</span>",
                    ),
                ),
                "expected_city": expected_parts[0],
                "years_experience": _clean_html_text(
                    _first_match(
                        body,
                        r"<span[^>]*class=(['\"]).*?personal-detail-workyears.*?\1[^>]*>(.*?)</span>",
                    ),
                ),
                "education": _clean_html_text(
                    _first_match(
                        body,
                        r"<span[^>]*class=(['\"]).*?personal-detail-edulevel.*?\1[^>]*>(.*?)</span>",
                    ),
                ),
                "expected_title": expected_parts[1],
                "expected_salary": expected_parts[2],
                "current_company": _clean_html_text(
                    _first_match(
                        body,
                        r"<span[^>]*class=(['\"]).*?work-item-compname.*?\1[^>]*>(.*?)</span>",
                    ),
                ),
                "current_title": _clean_html_text(
                    _first_match(
                        body,
                        r"<span[^>]*class=(['\"]).*?work-item-extra.*?\1[^>]*>\s*"
                        r"<span[^>]*>(.*?)</span>",
                    ),
                ),
                "highlights": _dedupe_items(highlight_items),
                "text": "\n".join(part for part in text_parts if part),
            },
        )
        if len(cards) >= max_cards:
            break

    return cards


def _first_match(
    text: str,
    pattern: str,
    *,
    group: int | str = 2,
) -> str:
    """Return the first regex group match or an empty string."""
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    try:
        return str(match.group(group) or "")
    except IndexError:
        return ""


def _extract_attr(opening_tag_attrs: str, attr_name: str) -> str:
    """Extract a single attribute value from an HTML opening-tag snippet."""
    pattern = rf"\b{re.escape(attr_name)}=(['\"])(.*?)\1"
    return _first_match(opening_tag_attrs, pattern)


def _clean_html_text(raw_text: str) -> str:
    """Convert an HTML fragment into compact plain text."""
    if not raw_text:
        return ""
    cleaned = raw_text.replace("<br>", "\n").replace("<br/>", "\n")
    cleaned = cleaned.replace("<br />", "\n")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _dedupe_items(items: list[str]) -> list[str]:
    """Keep highlight items stable and duplicate-free."""
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _clean_card_text(raw_text: str) -> str:
    """Normalize raw card text into compact line-based content."""
    lines = []
    for line in (raw_text or "").splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        if normalized:
            lines.append(normalized)
    return "\n".join(lines)


def _extract_display_name(lines: list[str]) -> str:
    """Extract the most likely display name from card lines."""
    for line in lines[:3]:
        if len(line) > 12:
            continue
        if any(token in line for token in ("先生", "女士", "*", "同学")):
            return line
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z·]{2,8}", line):
            return line
    return lines[0] if lines else ""


def _extract_role(lines: list[str], name: str) -> str:
    """Extract the most likely role/title line from card lines."""
    for line in lines:
        if line == name:
            continue
        if any(keyword in line for keyword in _EDUCATION_KEYWORDS):
            continue
        if re.search(r"\d+\s*年", line):
            continue
        if len(line) > 2:
            return line
    return ""


def _extract_city(text: str) -> str:
    """Extract a likely city token from free-form card text."""
    for city in _COMMON_CITIES:
        if city in text:
            return city

    for token in re.split(r"[\s/|]+", text):
        if (
            2 <= len(token) <= 6
            and re.fullmatch(r"[\u4e00-\u9fff]+", token)
            and token not in _EDUCATION_KEYWORDS
        ):
            return token
    return ""


def _extract_experience(text: str) -> str:
    """Extract a normalized years-of-experience token."""
    match = re.search(r"(\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?\+?\s*年)", text)
    if not match:
        return ""
    return match.group(1).replace(" ", "")


def _extract_education(text: str) -> str:
    """Extract a normalized education token."""
    for keyword in _EDUCATION_KEYWORDS:
        if keyword in text:
            return keyword
    return ""


def _candidate_id_from_url(detail_url: str, rank: int) -> str:
    """Build a stable candidate identifier from the detail URL."""
    parsed = urlparse(detail_url or "")
    res_ids = parse_qs(parsed.query).get("resIdEncode", [])
    if res_ids and res_ids[0]:
        return res_ids[0]
    cleaned = (detail_url or "").rstrip("/")
    if cleaned:
        return cleaned.split("/")[-1] or f"liepin-{rank}"
    return f"liepin-{rank}"


def _is_generic_search_detail_url(detail_url: str) -> bool:
    """Treat generic recruiter search URLs as unusable candidate details."""
    if not detail_url:
        return True
    parsed = urlparse(detail_url)
    path = (parsed.path or "").rstrip("/")
    return parsed.hostname == "lpt.liepin.com" and path in _GENERIC_SEARCH_PATHS
