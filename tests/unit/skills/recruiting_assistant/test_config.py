# -*- coding: utf-8 -*-
"""Tests for recruiting assistant runtime config."""

from copaw.agents.skills.recruiting_assistant.config import (
    load_recruiting_config,
)


def test_load_recruiting_config_uses_safe_defaults() -> None:
    """The recruiting config should default to a Liepin-only V1 setup."""
    config = load_recruiting_config({})

    assert config.enabled_sites == ["liepin"]
    assert config.failure_mode == "partial_success"
    assert config.default_page == 1
    assert config.default_result_limit == 20
    assert config.boss_profile_dir is None
    assert config.boss_cdp_url is None
    assert config.boss_debug_dump_dir is None
    assert config.zhaopin_profile_dir is None
    assert config.zhaopin_debug_dump_dir is None
    assert config.liepin_profile_dir is None
    assert config.liepin_debug_dump_dir is None
    assert config.match_model.enabled is False
    assert config.match_model.timeout_ms == 10000


def test_load_recruiting_config_parses_environment_overrides() -> None:
    """Configured env vars should be normalized into typed runtime config."""
    config = load_recruiting_config(
        {
            "RECRUITING_ENABLED_SITES": " liepin , boss , zhaopin , liepin ,, ",
            "RECRUITING_SITE_FAILURE_MODE": "strict_all_sites",
            "RECRUITING_DEFAULT_PAGE": "3",
            "RECRUITING_DEFAULT_RESULT_LIMIT": "50",
            "RECRUITING_MATCH_MODEL_PROVIDER": "openai",
            "RECRUITING_MATCH_MODEL": "gpt-4.1-mini",
            "RECRUITING_MATCH_API_KEY": "sk-test",
            "RECRUITING_MATCH_BASE_URL": "https://example.com/v1",
            "RECRUITING_MATCH_TIMEOUT_MS": "12000",
            "BOSS_PROFILE_DIR": "/tmp/boss-profile",
            "BOSS_CDP_URL": "http://127.0.0.1:9222",
            "BOSS_DEBUG_DUMP_DIR": "/tmp/boss-debug",
            "ZHAOPIN_PROFILE_DIR": "/tmp/zhaopin-profile",
            "ZHAOPIN_DEBUG_DUMP_DIR": "/tmp/zhaopin-debug",
            "LIEPIN_PROFILE_DIR": "/tmp/liepin-profile",
            "LIEPIN_DEBUG_DUMP_DIR": "/tmp/liepin-debug",
        },
    )

    assert config.enabled_sites == ["liepin", "boss", "zhaopin"]
    assert config.failure_mode == "strict_all_sites"
    assert config.default_page == 3
    assert config.default_result_limit == 50
    assert config.boss_profile_dir == "/tmp/boss-profile"
    assert config.boss_cdp_url == "http://127.0.0.1:9222"
    assert config.boss_debug_dump_dir == "/tmp/boss-debug"
    assert config.zhaopin_profile_dir == "/tmp/zhaopin-profile"
    assert config.zhaopin_debug_dump_dir == "/tmp/zhaopin-debug"
    assert config.liepin_profile_dir == "/tmp/liepin-profile"
    assert config.liepin_debug_dump_dir == "/tmp/liepin-debug"
    assert config.match_model.enabled is True
    assert config.match_model.provider == "openai"
    assert config.match_model.model == "gpt-4.1-mini"
    assert config.match_model.api_key == "sk-test"
    assert config.match_model.base_url == "https://example.com/v1"
    assert config.match_model.timeout_ms == 12000


def test_load_recruiting_config_falls_back_on_invalid_values() -> None:
    """Invalid env values should fall back to stable defaults."""
    config = load_recruiting_config(
        {
            "RECRUITING_ENABLED_SITES": " , , ",
            "RECRUITING_SITE_FAILURE_MODE": "explode_everything",
            "RECRUITING_DEFAULT_PAGE": "0",
            "RECRUITING_DEFAULT_RESULT_LIMIT": "-1",
            "RECRUITING_MATCH_TIMEOUT_MS": "abc",
        },
    )

    assert config.enabled_sites == ["liepin"]
    assert config.failure_mode == "partial_success"
    assert config.default_page == 1
    assert config.default_result_limit == 20
    assert config.match_model.timeout_ms == 10000
