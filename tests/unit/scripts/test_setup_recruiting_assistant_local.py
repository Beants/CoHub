# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_SOURCE = REPO_ROOT / "scripts" / "setup_recruiting_assistant_local.sh"


def test_setup_script_uses_shared_recruiting_bootstrap_helper() -> None:
    """Local setup should note recruiting is now a plugin."""
    script_text = SCRIPT_SOURCE.read_text(encoding="utf-8")

    assert "cohub-recruiting-plugin" in script_text
