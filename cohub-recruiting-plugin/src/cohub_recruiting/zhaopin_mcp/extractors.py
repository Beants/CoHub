# -*- coding: utf-8 -*-
"""Candidate extraction helpers for Zhaopin recruiter search pages."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from urllib.parse import parse_qs

from cohub_recruiting.models import CandidateSummary

_NON_CANDIDATE_NAME_TOKENS = {
    "首页",
    "职位中心",
    "推荐人才",
    "搜索人才",
    "潜在人才",
    "互动",
    "人才管理",
    "道具商城",
    "更多功能",
    "服务中心",
    "通知",
    "帮助",
    "面试",
    "我的收藏",
    "招聘数据",
    "企业主页",
    "会员服务",
    "手机版",
}
_CANDIDATE_SIGNAL_PATTERN = re.compile(
    r"(岁|年应届生|\d+年|本科|硕士|博士|大专|中专|在职|离职|期望[:：]|投递|浏览过职位|有回复|活跃)",
)


def _coerce_detail_url(raw_card: dict[str, Any]) -> str:
    """Prefer a resumeNumber-specific search URL over the generic search page."""
    detail_url = str(raw_card.get("detail_url") or "").strip()
    if not detail_url:
        return ""

    resume_number = str(raw_card.get("resume_number") or "").strip()
    parsed = urlsplit(detail_url)
    if (
        resume_number
        and parsed.netloc.endswith("zhaopin.com")
        and parsed.path == "/app/search"
    ):
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["resumeNumber"] = resume_number
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )
    return detail_url


def _looks_like_candidate_card(
    *,
    name: str,
    headline: str,
    city: str,
    experience: str,
    education: str,
    extra_attributes: dict[str, str],
    detail_url: str,
) -> bool:
    """Return ``True`` only for entries that look like candidate cards."""
    normalized_name = name.strip()
    if not normalized_name:
        return False
    if normalized_name in _NON_CANDIDATE_NAME_TOKENS:
        return False
    if detail_url.startswith("javascript:"):
        return False

    combined = " ".join(
        part
        for part in (
            headline,
            city,
            experience,
            education,
            " ".join(
                f"{key}:{value}" for key, value in extra_attributes.items()
            ),
        )
        if part
    ).strip()
    if not combined:
        return False
    return bool(_CANDIDATE_SIGNAL_PATTERN.search(combined))


def parse_candidate_card(
    raw_card: dict[str, Any],
    *,
    site: str,
    page: int,
    rank: int,
) -> CandidateSummary | None:
    """Convert one raw recruiter card payload into the shared summary shape."""
    name = str(raw_card.get("name") or "").strip()
    detail_url = _coerce_detail_url(raw_card)
    if not name or not detail_url:
        return None

    headline = str(raw_card.get("headline") or "").strip()
    city = str(raw_card.get("city") or "").strip()
    experience = str(raw_card.get("experience") or "").strip()
    education = str(raw_card.get("education") or "").strip()
    extra_attributes = {
        str(key): str(value)
        for key, value in dict(
            raw_card.get("extra_attributes") or {},
        ).items()
        if str(key).strip() and str(value).strip()
    }
    if not _looks_like_candidate_card(
        name=name,
        headline=headline,
        city=city,
        experience=experience,
        education=education,
        extra_attributes=extra_attributes,
        detail_url=detail_url,
    ):
        return None

    return CandidateSummary(
        site=site,
        candidate_id=str(raw_card.get("candidate_id") or detail_url),
        display_name=name,
        headline=headline,
        city=city,
        years_experience=experience,
        education=education,
        current_company=str(raw_card.get("current_company") or "").strip(),
        current_title=str(raw_card.get("current_title") or "").strip(),
        expected_title=str(raw_card.get("expected_title") or "").strip(),
        expected_salary=str(raw_card.get("expected_salary") or "").strip(),
        highlights=[
            str(item).strip()
            for item in list(raw_card.get("highlights") or [])
            if str(item).strip()
        ],
        extra_attributes=extra_attributes,
        detail_url=detail_url,
        page=page,
        rank=rank,
    )


def candidate_summary_is_reliable(candidate: CandidateSummary) -> bool:
    """Return ``True`` only for candidate summaries that still look card-shaped."""
    display_name = (candidate.display_name or "").strip()
    detail_url = (candidate.detail_url or "").strip()

    if not display_name:
        return False
    if display_name in _NON_CANDIDATE_NAME_TOKENS:
        return False
    if candidate.candidate_id == "search":
        return False
    if len(display_name) > 80:
        return False
    if _is_generic_search_detail_url(detail_url):
        return False

    combined = " ".join(
        part
        for part in (
            candidate.headline,
            candidate.city,
            candidate.years_experience,
            candidate.education,
            " ".join(candidate.highlights),
            " ".join(
                f"{key}:{value}"
                for key, value in candidate.extra_attributes.items()
            ),
        )
        if part
    ).strip()
    if not combined:
        return False
    return bool(_CANDIDATE_SIGNAL_PATTERN.search(combined))


def candidate_batch_is_reliable(candidates: list[CandidateSummary]) -> bool:
    """Detect whether the extracted Zhaopin batch is trustworthy enough."""
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
    """Extract candidate summaries from the current Zhaopin recruiter page."""
    try:
        raw_cards = await page.evaluate(
            _EXTRACT_CANDIDATES_SCRIPT,
            {"maxCards": max_cards},
        )
    except Exception:
        raw_cards = []

    summaries: list[CandidateSummary] = []
    for index, raw_card in enumerate(raw_cards or [], start=1):
        if not isinstance(raw_card, dict):
            continue
        summary = parse_candidate_card(
            raw_card,
            site="zhaopin",
            page=page_number,
            rank=index,
        )
        if summary is not None:
            summaries.append(summary)
    return summaries


async def extract_total_from_page(page: Any) -> int:
    """Best-effort parse the visible total result count from the page."""
    try:
        raw_total = await page.evaluate(_EXTRACT_TOTAL_SCRIPT)
    except Exception:
        return 0
    return _coerce_positive_int(raw_total)


async def capture_extraction_debug_snapshot(
    page: Any,
    max_cards: int,
) -> dict[str, Any]:
    """Capture bounded Zhaopin page evidence for debugging unreliable extraction."""
    try:
        raw_cards = await page.evaluate(
            _EXTRACT_CANDIDATES_SCRIPT,
            {"maxCards": max_cards},
        )
    except Exception:
        raw_cards = []

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


def _coerce_positive_int(value: Any) -> int:
    """Normalize an evaluate result into a safe positive integer."""
    if isinstance(value, int):
        return value if value > 0 else 0
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"\d+", text.replace(",", ""))
    if not match:
        return 0
    parsed = int(match.group(0))
    return parsed if parsed > 0 else 0


def _is_generic_search_detail_url(detail_url: str) -> bool:
    """Detect generic search-page links that do not identify a specific resume."""
    if not detail_url:
        return True
    parsed = urlsplit(detail_url)
    if not parsed.netloc.endswith("zhaopin.com"):
        return False
    if parsed.path != "/app/search":
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    return not bool(query.get("resumeNumber"))


_EXTRACT_CANDIDATES_SCRIPT = """
({ maxCards }) => {
  const limit = Number(maxCards) > 0 ? Number(maxCards) : Number.POSITIVE_INFINITY;
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const compact = (value) => normalize(value).replace(/\\s+/g, '');
  const isVisible = (node) => {
    if (!node || !node.isConnected) return false;
    const style = window.getComputedStyle(node);
    if (!style || style.display === 'none' || style.visibility === 'hidden') {
      return false;
    }
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const absoluteUrl = (href) => {
    try {
      return new URL(href, window.location.href).toString();
    } catch (_error) {
      return '';
    }
  };
  const readText = (root, selectors) => {
    for (const selector of selectors) {
      const node = root.querySelector(selector);
      if (!node) continue;
      const text =
        normalize(node.innerText) ||
        normalize(node.getAttribute?.('title')) ||
        normalize(node.textContent);
      if (text) return text;
    }
    return '';
  };
  const splitHeadline = (headline) => {
    const parts = headline
      .split('/')
      .map((part) => normalize(part))
      .filter(Boolean);
    return {
      city: parts[1] || '',
      experience: parts[2] || '',
      education: parts[3] || '',
    };
  };
  const collectExtras = (card) => {
    const extras = {};
    const chips = Array.from(card.querySelectorAll('span, div, li'))
      .map((node) => normalize(node.innerText))
      .filter(Boolean)
      .slice(0, 24);
    for (const text of chips) {
      if (!text.includes('：') && !text.includes(':')) continue;
      const separator = text.includes('：') ? '：' : ':';
      const [key, ...rest] = text.split(separator);
      const normalizedKey = normalize(key);
      const normalizedValue = normalize(rest.join(separator));
      if (!normalizedKey || !normalizedValue) continue;
      if (!(normalizedKey in extras)) {
        extras[normalizedKey] = normalizedValue;
      }
    }
    return extras;
  };
  const noiseNames = new Set([
    '首页',
    '职位中心',
    '推荐人才',
    '搜索人才',
    '潜在人才',
    '互动',
    '人才管理',
    '道具商城',
    '更多功能',
    '服务中心',
    '通知',
    '帮助',
    '面试',
    '我的收藏',
    '招聘数据',
    '企业主页',
    '会员服务',
    '手机版',
  ]);
  const hasCandidateSignals = (payload, cardText) => {
    if (!payload.name || noiseNames.has(payload.name)) return false;
    if ((payload.detail_url || '').startsWith('javascript:')) return false;
    const combined = compact([
      payload.headline,
      payload.city,
      payload.experience,
      payload.education,
      payload.expected_title,
      payload.expected_salary,
      payload.current_company,
      payload.current_title,
      cardText,
      Object.entries(payload.extra_attributes || {})
        .map(([key, value]) => `${key}:${value}`)
        .join(' '),
    ].filter(Boolean).join(' '));
    return /(岁|年应届生|\\d+年|本科|硕士|博士|大专|中专|在职|离职|期望[:：]|投递|浏览过职位|有回复|活跃)/.test(combined);
  };
  const collectTags = (card) => {
    const seen = new Set();
    const values = [];
    const nodes = Array.from(
      card.querySelectorAll('.talent-basic-info__tags-search [title], .talent-basic-info__tags-search span')
    );
    for (const node of nodes) {
      const text = normalize(node.getAttribute?.('title') || node.innerText || node.textContent);
      if (!text || seen.has(text)) continue;
      seen.add(text);
      values.push(text);
      if (values.length >= 8) break;
    }
    return values;
  };
  const collectExperienceRows = (card) => {
    return Array.from(card.querySelectorAll('.resume-item__experience tr'))
      .map((row) => ({
        time: readText(row, ['.talent-experience__time']),
        company: readText(row, ['.talent-experience__name']),
        title: readText(row, ['.talent-experience__title']),
      }))
      .filter((row) => row.time || row.company || row.title);
  };
  const readVueCandidate = (card) => {
    const candidates = [
      card,
      card.querySelector('.resume-item__content'),
      card.querySelector('.search-resume-item'),
    ].filter(Boolean);
    for (const node of candidates) {
      const vue = node.__vue__;
      const payload = vue && vue._props && vue._props.candidate;
      if (payload && typeof payload === 'object') {
        return payload;
      }
    }
    return null;
  };
  const dedupeKey = (payload) =>
    compact([
      payload.name,
      payload.city,
      payload.experience,
      payload.education,
      payload.expected_title,
      payload.expected_salary,
      payload.current_company,
      payload.current_title,
    ].filter(Boolean).join('|'));

  const cards = [];
  const seen = new Set();
  const seenKeys = new Set();
  const structuredCards = Array.from(
    document.querySelectorAll('.search-resume-item-wrap, .search-resume-item')
  );

  for (const rawCard of structuredCards) {
    const card = rawCard.closest('.search-resume-item-wrap') || rawCard;
    if (!isVisible(card)) continue;
    if (seen.has(card)) continue;
    seen.add(card);

    const name = readText(card, [
      '.talent-basic-info__name--inner',
      '.talent-basic-info__name [title]',
      '[class*="name"]',
      '[class*="Name"]',
      'h3',
      'h4',
      'strong',
    ]);
    const activeTag = readText(card, ['.global-active-tag']);
    const age = readText(card, ['.age-label']);
    const workYears = readText(card, ['.work-years-label']);
    const education = readText(card, ['.education-label']);
    const careerStatus = readText(card, ['.career-status-label']);
    const desiredCity = readText(card, ['.desired-city']);
    const desiredJobType = readText(card, ['.desired-job-type']);
    const desiredSalary = readText(card, ['.desired-salary']);
    const tags = collectTags(card);
    const experienceRows = collectExperienceRows(card);
    const vueCandidate = readVueCandidate(card);
    const latestExperience = experienceRows[0] || { company: '', title: '' };
    const detailUrl =
      absoluteUrl(
        card.getAttribute?.('data-detail-url') ||
        card.querySelector('[data-detail-url]')?.getAttribute?.('data-detail-url') ||
        card.querySelector('a[href*="/resume/"]')?.getAttribute?.('href') ||
        card.querySelector('a[href*="/candidate/"]')?.getAttribute?.('href') ||
        card.querySelector('a[href*="/talent/"]')?.getAttribute?.('href') ||
        ''
      ) ||
      window.location.href;
    const headline = [activeTag, age, workYears, education, careerStatus]
      .filter(Boolean)
      .join(' ');
    if (!name || (!headline && !desiredCity && !desiredJobType && !desiredSalary)) {
      continue;
    }

    const payload = {
      candidate_id:
        dedupeKey({
          name,
          city: desiredCity,
          experience: workYears,
          education,
          expected_title: desiredJobType,
          expected_salary: desiredSalary,
          current_company: latestExperience.company,
          current_title: latestExperience.title,
        }) || detailUrl,
      name,
      headline,
      city: desiredCity,
      experience: workYears,
      education,
      detail_url: detailUrl,
      resume_number: normalize(vueCandidate?.resumeNumber),
      current_company: latestExperience.company,
      current_title: latestExperience.title,
      expected_title: desiredJobType,
      expected_salary: desiredSalary,
      highlights: tags,
      extra_attributes: {},
    };
    if (activeTag) payload.extra_attributes['最近活跃'] = activeTag;
    if (careerStatus) payload.extra_attributes['求职状态'] = careerStatus;
    if (desiredJobType) payload.extra_attributes['期望职位'] = desiredJobType;
    if (desiredSalary) payload.extra_attributes['期望薪资'] = desiredSalary;
    if (tags.length) payload.extra_attributes['技能标签'] = tags.join('、');
    if (latestExperience.company) payload.extra_attributes['最近公司'] = latestExperience.company;
    if (latestExperience.title) payload.extra_attributes['最近职位'] = latestExperience.title;
    if (!hasCandidateSignals(payload, normalize(card.innerText))) continue;

    const key = dedupeKey(payload);
    if (!key || seenKeys.has(key)) continue;
    seenKeys.add(key);
    cards.push(payload);

    if (cards.length >= limit) {
      break;
    }
  }

  if (cards.length > 0) {
    return cards;
  }

  const anchors = Array.from(
    document.querySelectorAll('a[href], [data-resume-id], [class*="resume"], [class*="Resume"]')
  );

  for (const anchor of anchors) {
    const href = absoluteUrl(anchor.getAttribute?.('href') || '');
    const card =
      anchor.closest('li, article, [class*="card"], [class*="Card"], [class*="list-item"], [class*="resume"]') ||
      anchor;
    if (!isVisible(card)) continue;
    if (seen.has(card)) continue;
    seen.add(card);

    const name =
      normalize(card.querySelector('[class*="name"], [class*="Name"], h3, h4, strong')?.innerText) ||
      normalize(anchor.innerText).split(/\\s+/)[0];
    const headline =
      normalize(card.querySelector('[class*="title"], [class*="Title"], [class*="summary"], [class*="Summary"]')?.innerText) ||
      Array.from(card.querySelectorAll('span, div, p'))
        .map((node) => normalize(node.innerText))
        .find((text) => text.includes('/') || text.includes('年') || text.includes('本科') || text.includes('硕士')) ||
      '';
    const derived = splitHeadline(headline);
    const detailUrl =
      href ||
      absoluteUrl(card.querySelector('a[href]')?.getAttribute?.('href') || '') ||
      window.location.href;
    if (!name || !detailUrl) continue;
    const payload = {
      candidate_id:
        normalize(card.getAttribute?.('data-resume-id') || card.getAttribute?.('data-id')) ||
        detailUrl,
      name,
      headline,
      city:
        normalize(card.querySelector('[class*="city"], [class*="City"]')?.innerText) ||
        derived.city,
      experience:
        normalize(card.querySelector('[class*="year"], [class*="exp"], [class*="Experience"]')?.innerText) ||
        derived.experience,
      education:
        normalize(card.querySelector('[class*="degree"], [class*="edu"], [class*="Education"]')?.innerText) ||
        derived.education,
      detail_url: detailUrl,
      extra_attributes: collectExtras(card),
    };
    if (!hasCandidateSignals(payload, normalize(card.innerText))) continue;

    const key = dedupeKey(payload) || detailUrl;
    if (seenKeys.has(key)) continue;
    seenKeys.add(key);
    cards.push(payload);

    if (cards.length >= limit) {
      break;
    }
  }

  return cards;
}
"""


_EXTRACT_TOTAL_SCRIPT = """
() => {
  const normalize = (value) => (value || '').replace(/\\s+/g, '').trim();
  const candidates = Array.from(document.querySelectorAll('body, div, span, p'));
  for (const node of candidates) {
    const text = normalize(node.innerText);
    if (!text) continue;
    const match =
      text.match(/共(\\d+)人/) ||
      text.match(/共(\\d+)份/) ||
      text.match(/找到(\\d+)人/) ||
      text.match(/找到(\\d+)份/) ||
      text.match(/(\\d+)份简历/);
    if (match) {
      return Number(match[1]);
    }
  }
  return 0;
}
"""
