# -*- coding: utf-8 -*-
"""Markdown rendering helpers for recruiting search results."""

from __future__ import annotations

from collections.abc import Sequence

from .models import SiteSearchResult

_SITE_LABELS = {
    "boss": "BOSS直聘",
    "liepin": "猎聘",
    "zhaopin": "智联招聘",
}
_TABLE_HEADERS = [
    "序号",
    "姓名",
    "摘要",
    "城市",
    "期望城市",
    "经验",
    "学历",
    "当前公司",
    "当前职位",
    "期望职位",
    "期望薪资",
    "命中点",
    "详情",
]
_BASE_COLUMN_COUNT = len(_TABLE_HEADERS)


def site_label(site: str) -> str:
    """Return a user-facing site label."""
    normalized = (site or "").strip().lower()
    if normalized in _SITE_LABELS:
        return _SITE_LABELS[normalized]
    return normalized or "未知站点"


def _markdown_cell(value: str) -> str:
    """Render a safe markdown table cell with a visible fallback."""
    text = str(value or "").strip()
    if not text:
        return "-"
    return text.replace("\n", "<br>").replace("|", "\\|")


def render_search_results(
    results: Sequence[SiteSearchResult],
    display_limit: int | None = None,
) -> str:
    """Render recruiting site results into user-facing markdown."""
    lines: list[str] = []
    rendered_count = 0
    limit_hit = False

    for result in results:
        label = site_label(result.site)
        lines.append(f"### {label}")

        if result.ignored_filters:
            ignored = "；".join(result.ignored_filters)
            lines.append(f"- 忽略筛选：{ignored}")

        if result.status != "ok":
            lines.append(f"- 状态：{result.status}")
            lines.append("")
            continue

        extra_headers: list[str] = []
        seen_extra_headers: set[str] = set()
        for candidate in result.candidates:
            for key in candidate.extra_attributes:
                normalized_key = str(key or "").strip()
                if not normalized_key or normalized_key in seen_extra_headers:
                    continue
                seen_extra_headers.add(normalized_key)
                extra_headers.append(normalized_key)

        table_rows: list[str] = []
        for candidate in result.candidates:
            if display_limit is not None and rendered_count >= display_limit:
                limit_hit = True
                break

            rendered_count += 1
            table_rows.append(
                "| "
                + " | ".join(
                    [
                        str(rendered_count),
                        _markdown_cell(candidate.display_name),
                        _markdown_cell(candidate.headline),
                        _markdown_cell(candidate.city),
                        _markdown_cell(candidate.expected_city),
                        _markdown_cell(candidate.years_experience),
                        _markdown_cell(candidate.education),
                        _markdown_cell(candidate.current_company),
                        _markdown_cell(candidate.current_title),
                        _markdown_cell(candidate.expected_title),
                        _markdown_cell(candidate.expected_salary),
                        _markdown_cell("；".join(candidate.highlights)),
                        f"[打开{label}详情]({candidate.detail_url})",
                    ]
                    + [
                        _markdown_cell(candidate.extra_attributes.get(header, ""))
                        for header in extra_headers
                    ],
                )
                + " |",
            )

        if table_rows:
            lines.append(
                "| " + " | ".join(_TABLE_HEADERS + extra_headers) + " |",
            )
            lines.append(
                "| "
                + " | ".join(["---"] * (_BASE_COLUMN_COUNT + len(extra_headers)))
                + " |",
            )
            lines.extend(table_rows)
            lines.append("")

        if result.status == "ok" and not result.candidates:
            lines.append("- 状态：empty_result")
            lines.append("")
        elif table_rows and lines[-1] != "":
            lines.append("")

    if limit_hit and display_limit is not None:
        lines.append(f"已按显示上限展示 {display_limit} 位候选人。")

    return "\n".join(lines).strip()
