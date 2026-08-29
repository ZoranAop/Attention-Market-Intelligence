# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Reporters: console (terminal), html (shareable report), json (machine-readable)."""

from __future__ import annotations

import json
from typing import Any, Dict

from ..core.models import AnalysisResult

__all__ = ["to_json", "write_json", "render_console", "render_html", "write_html"]


def to_json(result: AnalysisResult) -> Dict[str, Any]:
    """Serialize an analysis result to a plain dict."""
    return result.to_dict()


def write_json(result: AnalysisResult, path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result.to_dict(), fh, ensure_ascii=False, indent=2)
    return path


from .console import print_report, render_console  # noqa: E402
from .html import render_html, write_html  # noqa: E402
