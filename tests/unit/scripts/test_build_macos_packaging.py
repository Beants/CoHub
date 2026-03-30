# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_SOURCE = REPO_ROOT / "scripts" / "pack" / "build_macos.sh"


def test_build_macos_bootstraps_recruiting_after_init() -> None:
    """macOS desktop launcher should note recruiting is now a plugin."""
    script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

    assert "copaw init --defaults --accept-security" in script_text
    assert "cohub-recruiting-plugin" in script_text
