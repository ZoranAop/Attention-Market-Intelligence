# ---------------------------------------------------------------------------
# attention-market · cross-axis divergence detection (v0.3)
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""跨轴 z-score 背离检测（RFC v0.3 §6）。

预置 6 类背离：
    1. Attention > Liquidity    热度先于资金
    2. Attention > Behavior     看热闹不买
    3. Behavior > Attention     暗中建仓
    4. Macro > On-chain         宏观领先链上
    5. Fundamental > Attention  价值未被定价
    6. Price > Liquidity        价格虚高

输入：4 轴 AxisReading + 可选 market.price_change_h24 / market.liquidity_usd
输出：List[DivergenceSignal]，按 severity 排序（critical > warning > info）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .asset import SignalAxis
from .models import AxisReading, DivergenceSignal, MarketSnapshot

__all__ = [
    "detect_divergence",
    "DivergenceRule",
    "DEFAULT_DIVERGENCE_RULES",
    "DEFAULT_Z_GAP_THRESHOLDS",
]


@dataclass
class DivergenceRule:
    """单条背离规则定义。"""

    name: str
    leading: str                    # axis.value 或派生轴（"liquidity" / "price"）
    lagging: str
    description_template: str       # 自然语言模板
    info_only: bool = False         # True 时即使触发也不进 warning/critical


# 预置 6 类（RFC §6.2）
DEFAULT_DIVERGENCE_RULES: List[DivergenceRule] = [
    DivergenceRule(
        name="Attention > Liquidity",
        leading=SignalAxis.ATTENTION.value,
        lagging="liquidity",
        description_template="Attention 跑得比 Liquidity 快：热度先于资金",
    ),
    DivergenceRule(
        name="Attention > Behavior",
        leading=SignalAxis.ATTENTION.value,
        lagging=SignalAxis.ONCHAIN.value,
        description_template="Attention 跑得比 Behavior 快：看热闹不买",
    ),
    DivergenceRule(
        name="Behavior > Attention",
        leading=SignalAxis.ONCHAIN.value,
        lagging=SignalAxis.ATTENTION.value,
        description_template="Behavior 跑得比 Attention 快：暗中建仓",
    ),
    DivergenceRule(
        name="Macro > On-chain",
        leading=SignalAxis.MACRO.value,
        lagging=SignalAxis.ONCHAIN.value,
        description_template="Macro 跑得比 On-chain 快：宏观领先链上",
    ),
    DivergenceRule(
        name="Fundamental > Attention",
        leading=SignalAxis.FUNDAMENTAL.value,
        lagging=SignalAxis.ATTENTION.value,
        description_template="Fundamental 跑得比 Attention 快：价值未被定价",
    ),
    DivergenceRule(
        name="Price > Liquidity",
        leading="price",
        lagging="liquidity",
        description_template="Price 跑得比 Liquidity 快：价格虚高",
        info_only=False,
    ),
]


# 严重度阈值（RFC §6.1）
DEFAULT_Z_GAP_THRESHOLDS = {
    "warning": 1.5,
    "critical": 2.5,
}


# ---------------------------------------------------------------------------
# Helpers for derived axes (liquidity / price) which are not first-class axes
# but can still participate in divergence detection.
# ---------------------------------------------------------------------------


def _liquidity_z_from_market(market: Optional[MarketSnapshot]) -> Optional[float]:
    """从 MarketSnapshot 派生 liquidity 的 z-score。

    简化策略：用 liquidity_usd 在 ±100% 范围 log 压缩作为 z 近似。
    """
    if market is None:
        return None
    liq = market.liquidity_usd
    if liq is None or liq <= 0:
        return None
    import math
    # liquidity ∈ [1k, 100M] 时 log10(liq) ∈ [3, 8]
    # 居中点 log10(1M) = 6 → z ≈ (log10(liq) - 6) / 1.5
    z = (math.log10(liq) - 6.0) / 1.5
    # 截断到 ±3
    return max(-3.0, min(3.0, z))


def _price_z_from_market(market: Optional[MarketSnapshot]) -> Optional[float]:
    """从 MarketSnapshot 派生 price 的 z-score（基于 24h 变化）。"""
    if market is None:
        return None
    ch = market.price_change_h24
    if ch is None:
        return None
    # 24h 涨跌幅 ±30% 映射到 ±3 sigma
    z = (ch - 0.0) / 0.10
    return max(-3.0, min(3.0, z))


def _get_z(value: str, axis_readings: Dict[str, AxisReading], market: Optional[MarketSnapshot]) -> Optional[float]:
    if value in (SignalAxis.ATTENTION.value, SignalAxis.ONCHAIN.value,
                 SignalAxis.FUNDAMENTAL.value, SignalAxis.MACRO.value):
        reading = axis_readings.get(value)
        if reading is None or reading.unavailable:
            return None
        return reading.z_score
    if value == "liquidity":
        return _liquidity_z_from_market(market)
    if value == "price":
        return _price_z_from_market(market)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def detect_divergence(
    axis_readings: Dict[str, AxisReading],
    market: Optional[MarketSnapshot] = None,
    rules: Optional[List[DivergenceRule]] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> List[DivergenceSignal]:
    """主入口：返回按 severity 排序的 DivergenceSignal 列表。

    ``info`` 级别默认仍返回（便于报告展示）；调用方可按需过滤。
    """
    rules = rules or DEFAULT_DIVERGENCE_RULES
    thresholds = dict(thresholds or DEFAULT_Z_GAP_THRESHOLDS)
    warn_gap = float(thresholds.get("warning", 1.5))
    crit_gap = float(thresholds.get("critical", 2.5))

    signals: List[DivergenceSignal] = []
    for rule in rules:
        z_lead = _get_z(rule.leading, axis_readings, market)
        z_lag = _get_z(rule.lagging, axis_readings, market)
        if z_lead is None or z_lag is None:
            continue
        gap = z_lead - z_lag
        # 判定方向：leading 应该 > lagging（gap > 0）
        if gap <= 0:
            continue
        if gap < warn_gap:
            severity = "info"
        elif gap < crit_gap:
            severity = "warning"
        else:
            severity = "critical"
        if severity == "info" and rule.info_only:
            continue
        desc = rule.description_template
        signals.append(DivergenceSignal(
            name=rule.name,
            leading_axis=rule.leading,
            lagging_axis=rule.lagging,
            z_gap=gap,
            severity=severity,
            description=desc,
        ))

    # 按严重度排序
    severity_rank = {"critical": 3, "warning": 2, "info": 1}
    signals.sort(key=lambda s: severity_rank.get(s.severity, 0), reverse=True)
    return signals