# ---------------------------------------------------------------------------
# attention-market · four-axis unified interface (v0.3)
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""4 大信号轴的统一接口（RFC v0.3 §1, §2.2）。

四个轴：
    ATTENTION    · 场外注意力（Wiki / HN / Reddit / Search）
    ONCHAIN      · 场内行为（txns / makers / volume / holders）
    FUNDAMENTAL  · 基本面（TVL / Revenue / Fees，DeFi/L1 有）
    MACRO        · 宏观（DXY / UST2Y / Funding / VIX，L1/STABLECOIN 有）

v0.3 把 ``AssetProfile.signals`` 平铺字典结构化为 ``axis_weights`` + 4 轴
``AxisReading``。本模块对外暴露：
    - ``compute_axis_readings(...)``：从已有 AttentionMetrics / MarketSnapshot /
      HalfLifeResult / ConversionMetrics 派生 4 轴 AxisReading
    - ``derive_axis_weights_from_signals(...)``：v0.2 老 profile.signals 自动派生
      v0.3 axis_weights（兼容旧调用方）

任何 provider 失败 → 该轴 reading.unavailable=True，绝不编造。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .asset import SignalAxis
from .models import (
    AttentionMetrics,
    AxisReading,
    ConversionMetrics,
    HalfLifeResult,
    MarketSnapshot,
    PhaseTag,
    RegimeReading,
)
from .registry import AssetProfile

__all__ = [
    "compute_axis_readings",
    "derive_axis_weights_from_signals",
    "DEFAULT_AXIS_WEIGHTS",
    "axis_readings_from_legacy_signals",
]


# ---------------------------------------------------------------------------
# Defaults (RFC §3.1)
# ---------------------------------------------------------------------------

DEFAULT_AXIS_WEIGHTS: Dict[str, float] = {
    "attention": 0.40,
    "onchain": 0.40,
    "fundamental": 0.10,
    "macro": 0.10,
}


# v0.2 signals → v0.3 axis 映射（RFC §13 风险缓解表）
_LEGACY_SIGNAL_TO_AXIS: Dict[str, str] = {
    "onchain_txns": "onchain",
    "onchain_makers": "onchain",
    "onchain_volume": "onchain",
    "volume": "onchain",                  # v0.2 把 volume 算 on-chain proxy
    "holders": "onchain",
    "wikipedia": "attention",
    "hackernews": "attention",
    "reddit": "attention",
    "search": "attention",
    "social": "attention",
    "tvl": "fundamental",
    "revenue": "fundamental",
    "fees": "fundamental",
    "fundamentals": "fundamental",
    "dxy": "macro",
    "ust2y": "macro",
    "funding": "macro",
    "vix": "macro",
}


def derive_axis_weights_from_signals(
    signals: Dict[str, float],
) -> Dict[str, float]:
    """从 v0.2 ``profile.signals`` 自动派生 v0.3 ``axis_weights``。

    用于：旧 profile 没显式给 axis_weights 时降级使用（RFC §13）。
    返回的字典 4 轴和为 1（若原 signals 不空）；若 signals 为空则返回 DEFAULT。
    """
    if not signals:
        return dict(DEFAULT_AXIS_WEIGHTS)
    acc: Dict[str, float] = {"attention": 0.0, "onchain": 0.0, "fundamental": 0.0, "macro": 0.0}
    for key, w in signals.items():
        axis = _LEGACY_SIGNAL_TO_AXIS.get(key.lower())
        if axis is None:
            # 未知信号 → 保守归入 attention
            axis = "attention"
        acc[axis] += float(w or 0.0)
    total = sum(acc.values())
    if total <= 0:
        return dict(DEFAULT_AXIS_WEIGHTS)
    return {k: v / total for k, v in acc.items()}


# ---------------------------------------------------------------------------
# Axis computation
# ---------------------------------------------------------------------------


def _safe(value: Any) -> Optional[float]:
    """强制数值化；None / 非数 / 负值 → None。"""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def _z_from_growth(growth: Optional[float], window_sigma: float = 0.5) -> Optional[float]:
    """简化的 z-score：只有 1 个观测时，用 sigma=0.5 作为温和基准。

    当 growth 不可用或为 0 时返回 None / 0。
    """
    g = _safe(growth)
    if g is None or window_sigma <= 0:
        return None
    return g / window_sigma


@dataclass
class _LegacyInputs:
    """v0.2 已知数据 → v0.3 4 轴读数的最小输入。"""

    attention: AttentionMetrics
    market: MarketSnapshot
    halflife: HalfLifeResult
    conversion: ConversionMetrics


def compute_axis_readings(
    *,
    attention: AttentionMetrics,
    market: MarketSnapshot,
    halflife: HalfLifeResult,
    conversion: ConversionMetrics,
    profile: AssetProfile,
    regime: Optional[RegimeReading] = None,
) -> Dict[str, AxisReading]:
    """主入口：从 v0.2 已有数据派生 4 轴 AxisReading。

    输入都是 ``AnalysisResult`` 上已存在的字段；新增的 FUNDAMENTAL / MACRO 轴
    在 v0.3 默认 unavailable，由后续 providers 接入后再填充。

    返回字典按 axis.value 索引（attention / onchain / fundamental / macro）。
    """
    inp = _LegacyInputs(attention=attention, market=market, halflife=halflife, conversion=conversion)

    # -------- ATTENTION 轴 --------
    attention_reading = AxisReading(axis=SignalAxis.ATTENTION)
    attention_reading.level = _safe(inp.attention.level)
    attention_reading.growth = _safe(inp.attention.growth)
    attention_reading.momentum = _safe(inp.attention.momentum)
    attention_reading.half_life_h = _safe(inp.halflife.halflife_hours)
    attention_reading.z_score = _z_from_growth(attention_reading.growth)
    attention_reading.unavailable = attention_reading.level is None
    if attention_reading.unavailable:
        attention_reading.reason = "无 Attention Index 数据"
    attention_reading.source_breakdown = {
        "used": list(inp.attention.used_sources),
        "missing": list(inp.attention.missing_sources),
        "halflife_status": inp.halflife.status,
    }

    # -------- ONCHAIN 轴 --------
    onchain_reading = AxisReading(axis=SignalAxis.ONCHAIN)
    has_market = any(_safe(getattr(inp.market, f)) is not None for f in
                     ("volume_h24", "txns_h24_buys", "txns_h24_sells", "makers_h24", "liquidity_usd"))
    if has_market:
        # 用 volume 强度 + txns 强度合成 0-100 level
        vol = _safe(inp.market.volume_h24) or 0.0
        liq = _safe(inp.market.liquidity_usd) or 0.0
        buys = _safe(inp.market.txns_h24_buys) or 0.0
        sells = _safe(inp.market.txns_h24_sells) or 0.0
        txns = buys + sells
        # 简单合成（log 压缩）：volume 与 txns 各自 0-50
        import math
        vol_score = 50.0 if vol <= 0 else min(50.0, math.log10(max(vol, 1.0)) * 10.0)
        txns_score = 50.0 if txns <= 0 else min(50.0, math.log10(max(txns, 1.0)) * 12.0)
        onchain_reading.level = vol_score + txns_score
        onchain_reading.growth = _safe(inp.market.price_change_h24)
        onchain_reading.z_score = _z_from_growth(onchain_reading.growth)
        onchain_reading.source_breakdown = {
            "volume_h24": vol,
            "txns_h24_total": txns,
            "liquidity_usd": liq,
            "turnover": inp.market.turnover,
            "mc_to_liquidity": inp.market.mc_to_liquidity,
        }
    else:
        onchain_reading.unavailable = True
        onchain_reading.reason = "无链上/市场快照数据"

    # -------- FUNDAMENTAL 轴（v0.3 占位，v0.3.1 接入 DeFiLlama） --------
    fundamental_reading = AxisReading(axis=SignalAxis.FUNDAMENTAL)
    fundamental_reading.unavailable = True
    fundamental_reading.reason = "v0.3 占位：Fundamental 轴待 DeFiLlama/Token Terminal 接入"
    fundamental_reading.source_breakdown = {"provider_planned": ["defillama", "token_terminal"]}

    # -------- MACRO 轴（v0.3 占位，v0.3.1 接入 FRED/Coinalyze） --------
    macro_reading = AxisReading(axis=SignalAxis.MACRO)
    # 若 regime 已计算且可用，派生 level/z（避免完全 unavailable）
    if regime is not None and regime.kind.value != "Unknown" and regime.confidence > 0:
        # regime.risk_score: 0 (risk-on) → 100 (risk-off) → 轴 level 反向映射
        macro_reading.level = max(0.0, 100.0 - (regime.risk_score or 50.0))
        macro_reading.z_score = _z_from_growth(macro_reading.level - 50.0)
        macro_reading.source_breakdown = {
            "regime_kind": regime.kind.value,
            "regime_risk_score": regime.risk_score,
            "regime_confidence": regime.confidence,
        }
    else:
        macro_reading.unavailable = True
        macro_reading.reason = "v0.3 占位：Macro 轴待 FRED/Coinalyze 接入"
        macro_reading.source_breakdown = {"provider_planned": ["fred", "coinalyze"]}

    return {
        SignalAxis.ATTENTION.value: attention_reading,
        SignalAxis.ONCHAIN.value: onchain_reading,
        SignalAxis.FUNDAMENTAL.value: fundamental_reading,
        SignalAxis.MACRO.value: macro_reading,
    }


# ---------------------------------------------------------------------------
# Legacy compatibility: when a caller hands us a v0.2-style ``signals`` dict,
# we expose ``axis_readings_from_legacy_signals`` as a no-op helper that
# returns an empty dict (since v0.2 had no axis concept). It exists purely
# so the import surface is explicit.
# ---------------------------------------------------------------------------


def axis_readings_from_legacy_signals(signals: Dict[str, float]) -> Dict[str, AxisReading]:
    """占位：从 v0.2 signals 字典派生"伪"轴读数（仅用于兼容接口）。

    返回全轴 unavailable 的字典。真实派生请使用 ``compute_axis_readings``。
    """
    _ = derive_axis_weights_from_signals(signals)  # 触发权重派生，不返回
    return {
        SignalAxis.ATTENTION.value: AxisReading(axis=SignalAxis.ATTENTION, unavailable=True, reason="legacy adapter"),
        SignalAxis.ONCHAIN.value: AxisReading(axis=SignalAxis.ONCHAIN, unavailable=True, reason="legacy adapter"),
        SignalAxis.FUNDAMENTAL.value: AxisReading(axis=SignalAxis.FUNDAMENTAL, unavailable=True, reason="legacy adapter"),
        SignalAxis.MACRO.value: AxisReading(axis=SignalAxis.MACRO, unavailable=True, reason="legacy adapter"),
    }