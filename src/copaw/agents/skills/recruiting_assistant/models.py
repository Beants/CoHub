# -*- coding: utf-8 -*-
"""Shared data models for the recruiting assistant skill."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SiteStatus = Literal[
    "ok",
    "not_logged_in",
    "captcha_required",
    "rate_limited",
    "site_layout_changed",
    "extraction_unreliable",
    "unsupported_filter",
    "empty_result",
    "internal_error",
]


class NormalizedSearchQuery(BaseModel):
    """Unified recruiting search contract shared across site adapters."""

    sites: list[str] = Field(default_factory=list)
    keyword: str = ""
    position: str = ""
    company: str = ""
    current_city: str = ""
    expected_city: str = ""
    experience: str = ""
    education: str = ""
    current_industry: str = ""
    expected_industry: str = ""
    current_function: str = ""
    expected_function: str = ""
    current_salary: str = ""
    expected_salary: str = ""
    school: str = ""
    major: str = ""
    active_status: str = ""
    job_status: str = ""
    management_experience: str = ""
    page: int = 1
    page_size_limit: int = 20


class CandidateSummary(BaseModel):
    """Unified candidate summary shown in CoPaw."""

    site: str
    candidate_id: str
    display_name: str
    headline: str
    city: str = ""
    expected_city: str = ""
    years_experience: str = ""
    education: str = ""
    current_company: str = ""
    current_title: str = ""
    expected_title: str = ""
    expected_salary: str = ""
    highlights: list[str] = Field(default_factory=list)
    extra_attributes: dict[str, str] = Field(default_factory=dict)
    detail_url: str
    page: int = 1
    rank: int = 0
    site_status: SiteStatus = "ok"


class SiteSearchResult(BaseModel):
    """Result envelope returned by a recruiting site adapter."""

    site: str
    status: SiteStatus
    page: int = 1
    total: int = 0
    message: str = ""
    continue_tool: str = ""
    reuse_same_browser_window: bool = False
    avoid_reopen_browser: bool = False
    stop_current_turn: bool = False
    ignored_filters: list[str] = Field(default_factory=list)
    summary_markdown: str = ""
    candidates: list[CandidateSummary] = Field(default_factory=list)
