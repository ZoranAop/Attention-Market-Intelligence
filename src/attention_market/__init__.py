# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""attention-market — Attention Market Intelligence.

An open-source framework for measuring how attention transforms into
engagement, behavior, market activity, value, and risk.

一个开源的注意力市场分析框架，用于研究注意力如何转化为参与、行为、
市场活动、价值与风险。

Quick start:
    python -m attention_market analyze "TOKEN NAME"
    python -m attention_market demo --html demo.html
"""

__version__ = "0.1.0"
__author__ = "attention-market contributors"
__license__ = "MIT"

from .core.models import AnalysisResult  # noqa: F401
from .core.pipeline import analyze, analyze_demo  # noqa: F401
from .utils.config import load_config  # noqa: F401

__all__ = ["analyze", "analyze_demo", "load_config", "AnalysisResult", "__version__"]
