# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Core analysis layer: Attention → Engagement → Action → Market → Risk."""

from .attention import build_attention_metrics, compute_index_series, classify_trend
from .conversion import compute_conversion
from .gate import evaluate_gate
from .halflife import estimate_half_life, event_class_label
from .models import AnalysisResult, AttentionMetrics, MarketSnapshot, SecurityInfo
from .pipeline import analyze, analyze_demo
from .quadrant import classify_quadrant
from .risk import score_risk

__all__ = [
    "analyze",
    "analyze_demo",
    "build_attention_metrics",
    "compute_index_series",
    "classify_trend",
    "compute_conversion",
    "evaluate_gate",
    "estimate_half_life",
    "event_class_label",
    "classify_quadrant",
    "score_risk",
    "AnalysisResult",
    "AttentionMetrics",
    "MarketSnapshot",
    "SecurityInfo",
]
