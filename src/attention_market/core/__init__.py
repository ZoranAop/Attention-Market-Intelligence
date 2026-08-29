# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Core analysis layer: Attention → Engagement → Action → Market → Risk.

v0.2 通用化：在原 Attention/Beta/Quadrant/Gate/Risk 之上引入
"资产类型 + 画像"抽象层，支持稳定币/L1/DeFi/Security 等多类资产。
"""

from .asset import AssetKind, AssetSignals, classify_asset, load_whitelist
from .attention import build_attention_metrics, compute_index_series, classify_trend
from .conversion import compute_conversion
from .gate import evaluate_gate
from .halflife import estimate_half_life, event_class_label
from .models import AnalysisResult, AttentionMetrics, MarketSnapshot, SecurityInfo
from .pipeline import analyze, analyze_demo
from .quadrant import classify_quadrant
from .registry import (
    AssetProfile,
    BUILTIN_PROFILES,
    get_profile,
    list_profiles,
    register_profile,
    reset_registry,
)
from .risk import RISK_LEVELS, score_risk

__all__ = [
    # 主流水线
    "analyze",
    "analyze_demo",
    # 注意力
    "build_attention_metrics",
    "compute_index_series",
    "classify_trend",
    # 转化
    "compute_conversion",
    # 门控
    "evaluate_gate",
    # 半衰期
    "estimate_half_life",
    "event_class_label",
    # 四象限
    "classify_quadrant",
    # 风险
    "score_risk",
    "RISK_LEVELS",
    # 数据模型
    "AnalysisResult",
    "AttentionMetrics",
    "MarketSnapshot",
    "SecurityInfo",
    # v0.2 通用化新增
    "AssetKind",
    "AssetSignals",
    "AssetProfile",
    "classify_asset",
    "load_whitelist",
    "get_profile",
    "register_profile",
    "list_profiles",
    "reset_registry",
    "BUILTIN_PROFILES",
]
