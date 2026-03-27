# -*- coding: utf-8 -*-
"""Candidate extraction helpers for BOSS recruiter search pages."""

from __future__ import annotations

import re
from typing import Any

from ..models import CandidateSummary


def parse_candidate_card(
    raw_card: dict[str, Any],
    *,
    site: str,
    page: int,
    rank: int,
) -> CandidateSummary | None:
    """Convert one raw recruiter card payload into the shared summary shape."""
    name = str(raw_card.get("name") or "").strip()
    detail_url = str(raw_card.get("detail_url") or "").strip()
    if not name or not detail_url:
        return None

    return CandidateSummary(
        site=site,
        candidate_id=str(raw_card.get("candidate_id") or detail_url),
        display_name=name,
        headline=str(raw_card.get("headline") or "").strip(),
        city=str(raw_card.get("city") or "").strip(),
        years_experience=str(raw_card.get("experience") or "").strip(),
        education=str(raw_card.get("education") or "").strip(),
        extra_attributes={
            str(key): str(value)
            for key, value in dict(
                raw_card.get("extra_attributes") or {},
            ).items()
            if str(key).strip() and str(value).strip()
        },
        detail_url=detail_url,
        page=page,
        rank=rank,
    )


async def extract_candidates_from_page(
    page: Any,
    page_number: int,
    max_cards: int,
) -> list[CandidateSummary]:
    """Extract candidate summaries from the current BOSS recruiter page."""
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
            site="boss",
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


_EXTRACT_CANDIDATES_SCRIPT = """
({ maxCards }) => {
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
  const findHeadline = (card) => {
    const textNodes = Array.from(card.querySelectorAll('span, div, p'))
      .map((node) => normalize(node.innerText))
      .filter(Boolean);
    return textNodes.find((text) =>
      text.includes('/') || text.includes('年') || text.includes('本科') || text.includes('硕士')
    ) || '';
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
  const splitHeadline = (headline) => {
    const parts = headline.split('/').map((part) => normalize(part)).filter(Boolean);
    return {
      city: parts[1] || '',
      experience: parts[2] || '',
      education: parts[3] || '',
    };
  };

  const cards = [];
  const seen = new Set();
  const anchors = Array.from(
    document.querySelectorAll('a[href], [data-geek-id], [ka*="search_list"]')
  );

  for (const anchor of anchors) {
    const href = absoluteUrl(anchor.getAttribute?.('href') || '');
    if (
      !href &&
      !anchor.getAttribute?.('data-geek-id') &&
      !anchor.getAttribute?.('data-id')
    ) {
      continue;
    }
    const card = anchor.closest('li, article, [class*="card"], [class*="Card"], [class*="list-item"], [class*="geek"]') || anchor;
    if (!isVisible(card)) continue;
    if (seen.has(card)) continue;
    seen.add(card);

    const name =
      normalize(card.querySelector('[class*="name"], [class*="Name"], h3, h4, strong')?.innerText) ||
      normalize(anchor.innerText).split(/\\s+/)[0];
    const headline = findHeadline(card);
    const derived = splitHeadline(headline);
    const detailUrl =
      href ||
      absoluteUrl(card.querySelector('a[href]')?.getAttribute?.('href') || '');
    if (!name || !detailUrl) continue;

    cards.push({
      candidate_id:
        normalize(card.getAttribute?.('data-geek-id') || card.getAttribute?.('data-id')) ||
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
    });

    if (cards.length >= Math.max(1, Number(maxCards) || 20)) {
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
      text.match(/共(\\d+)位/) ||
      text.match(/找到(\\d+)人/) ||
      text.match(/找到(\\d+)位/) ||
      text.match(/(\\d+)份简历/);
    if (match) {
      return Number(match[1]);
    }
  }
  return 0;
}
"""
