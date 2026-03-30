# -*- coding: utf-8 -*-
"""Runtime config loader for the recruiting assistant skill."""

from __future__ import annotations

import os
from typing import Literal, Mapping

from pydantic import BaseModel, Field

FailureMode = Literal["partial_success", "strict_all_sites"]

_DEFAULT_ENABLED_SITES = ["liepin"]
_DEFAULT_FAILURE_MODE: FailureMode = "partial_success"
_DEFAULT_PAGE = 1
_DEFAULT_RESULT_LIMIT = 20
_DEFAULT_MATCH_TIMEOUT_MS = 10000


class MatchModelConfig(BaseModel):
    """Configuration for the small model that generates match reasons."""

    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    timeout_ms: int = _DEFAULT_MATCH_TIMEOUT_MS

    @property
    def enabled(self) -> bool:
        """Return True when the small-model config is usable."""
        return bool(self.provider and self.model and self.api_key)


class RecruitingRuntimeConfig(BaseModel):
    """Resolved recruiting assistant runtime configuration."""

    enabled_sites: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_ENABLED_SITES),
    )
    failure_mode: FailureMode = _DEFAULT_FAILURE_MODE
    default_page: int = _DEFAULT_PAGE
    default_result_limit: int = _DEFAULT_RESULT_LIMIT
    match_model: MatchModelConfig = Field(
        default_factory=MatchModelConfig,
    )
    boss_profile_dir: str | None = None
    boss_cdp_url: str | None = None
    boss_debug_dump_dir: str | None = None
    zhaopin_profile_dir: str | None = None
    zhaopin_debug_dump_dir: str | None = None
    liepin_profile_dir: str | None = None
    liepin_debug_dump_dir: str | None = None


def _parse_positive_int(
    raw: str | None,
    *,
    default: int,
) -> int:
    """Parse a positive integer, falling back to *default* on failure."""
    if raw is None:
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_enabled_sites(raw: str | None) -> list[str]:
    """Parse a comma-separated site list with dedupe and safe fallback."""
    if raw is None:
        return list(_DEFAULT_ENABLED_SITES)

    sites: list[str] = []
    seen: set[str] = set()
    for item in str(raw).split(","):
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        sites.append(normalized)

    return sites or list(_DEFAULT_ENABLED_SITES)


def _parse_failure_mode(raw: str | None) -> FailureMode:
    """Parse a supported failure mode or return the safe default."""
    if raw is None:
        return _DEFAULT_FAILURE_MODE

    normalized = str(raw).strip().lower()
    if normalized in {"partial_success", "strict_all_sites"}:
        return normalized  # type: ignore[return-value]
    return _DEFAULT_FAILURE_MODE


def load_recruiting_config(
    env: Mapping[str, str] | None = None,
) -> RecruitingRuntimeConfig:
    """Load recruiting assistant config from env vars or a provided mapping."""
    source = os.environ if env is None else env

    return RecruitingRuntimeConfig(
        enabled_sites=_parse_enabled_sites(
            source.get("RECRUITING_ENABLED_SITES"),
        ),
        failure_mode=_parse_failure_mode(
            source.get("RECRUITING_SITE_FAILURE_MODE"),
        ),
        default_page=_parse_positive_int(
            source.get("RECRUITING_DEFAULT_PAGE"),
            default=_DEFAULT_PAGE,
        ),
        default_result_limit=_parse_positive_int(
            source.get("RECRUITING_DEFAULT_RESULT_LIMIT"),
            default=_DEFAULT_RESULT_LIMIT,
        ),
        match_model=MatchModelConfig(
            provider=str(
                source.get("RECRUITING_MATCH_MODEL_PROVIDER", ""),
            ).strip(),
            model=str(
                source.get("RECRUITING_MATCH_MODEL", ""),
            ).strip(),
            api_key=str(
                source.get("RECRUITING_MATCH_API_KEY", ""),
            ).strip(),
            base_url=str(
                source.get("RECRUITING_MATCH_BASE_URL", ""),
            ).strip(),
            timeout_ms=_parse_positive_int(
                source.get("RECRUITING_MATCH_TIMEOUT_MS"),
                default=_DEFAULT_MATCH_TIMEOUT_MS,
            ),
        ),
        boss_profile_dir=(
            str(source.get("BOSS_PROFILE_DIR", "")).strip() or None
        ),
        boss_cdp_url=(
            str(source.get("BOSS_CDP_URL", "")).strip() or None
        ),
        boss_debug_dump_dir=(
            str(source.get("BOSS_DEBUG_DUMP_DIR", "")).strip() or None
        ),
        zhaopin_profile_dir=(
            str(source.get("ZHAOPIN_PROFILE_DIR", "")).strip() or None
        ),
        zhaopin_debug_dump_dir=(
            str(source.get("ZHAOPIN_DEBUG_DUMP_DIR", "")).strip() or None
        ),
        liepin_profile_dir=(
            str(source.get("LIEPIN_PROFILE_DIR", "")).strip() or None
        ),
        liepin_debug_dump_dir=(
            str(source.get("LIEPIN_DEBUG_DUMP_DIR", "")).strip() or None
        ),
    )
