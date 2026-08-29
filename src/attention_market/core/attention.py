# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""① Attention Index and ② Attention Momentum.

Three readings matter, in this order of importance:

    Level      — how much attention right now (0-100)
    Growth     — first derivative: is attention still gathering?
    Momentum   — second derivative: is the gathering *accelerating*?

The key insight encoded here: **price is driven by *new* attention (dA/dt),
not by the stock of attention (A)**. Therefore the earliest warning signal is
the sign flip of the second derivative — attention is still rising, but the
rate at which new people arrive has started to fall.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from .models import AttentionMetrics, SeriesPoint

__all__ = [
    "DEFAULT_RANGES",
    "scale_signal",
    "compute_index_series",
    "compute_momentum",
    "compute_growth_momentum",
    "geometric_aggregate",
    "classify_trend",
]

# 绝对量级参考区间 (lo, hi) —— 用 log10 映射到 0-100。
# 采用"绝对标定"而非"序列内标准化"，是为了让不同标的之间可以横向比较。
# 这些区间是研究默认值，可在 config 的 attention.reference_ranges 中覆盖。
DEFAULT_RANGES: Dict[str, Tuple[float, float]] = {
    "onchain_txns": (10.0, 100_000.0),      # 24h 交易笔数
    "onchain_makers": (5.0, 50_000.0),      # 24h 参与地址数
    "volume": (1_000.0, 100_000_000.0),     # 24h 成交额 (USD)
    "wikipedia": (10.0, 100_000.0),         # 日浏览量
    "hackernews": (1.0, 100.0),             # 相关帖子/评论数
    "reddit": (1.0, 500.0),                 # 相关帖子/评论数
}


def scale_signal(name: str, value: Optional[float], ranges: Dict[str, Tuple[float, float]]) -> Optional[float]:
    """把单一信号按 log10 绝对标定到 0-100。

    Returns None when the value is missing or non-positive (unknown ≠ zero).
    """
    if value is None or value <= 0:
        return None
    lo, hi = ranges.get(name, (1.0, 1000.0))
    lo = max(lo, 1e-9)
    try:
        score = (math.log10(value) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)) * 100.0
    except (ValueError, ZeroDivisionError):
        return None
    return max(0.0, min(100.0, score))


def compute_index_series(
    signals: Dict[str, List[Optional[float]]],
    weights: Dict[str, float],
    labels: Sequence[str],
    ranges: Optional[Dict[str, Tuple[float, float]]] = None,
    policy: str = "redistribute",
) -> Tuple[List[float], List[str], List[str]]:
    """按权重把多个信号合成为一条 0-100 的注意力指数序列。

    ``signals`` 形如 {"onchain_txns": [v_t0, v_t1, ...], "wikipedia": [...]}
    各序列长度应一致（对齐到 labels）。

    ``policy``:
        redistribute — 缺失信号不参与，剩余权重按比例重分配（推荐）
        zero         — 缺失信号记 0 分

    Returns: (index_series, used_sources, missing_sources)
    """
    ranges = ranges or DEFAULT_RANGES
    n = len(labels)
    if n == 0:
        return [], [], []

    scaled: Dict[str, List[Optional[float]]] = {}
    used: List[str] = []
    missing: List[str] = []

    for name, series in signals.items():
        vals = [scale_signal(name, v, ranges) for v in series]
        if all(v is None for v in vals):
            missing.append(name)
            continue
        scaled[name] = vals
        used.append(name)

    if not scaled:
        return [0.0] * n, [], missing

    index: List[float] = []
    for i in range(n):
        num = 0.0
        den = 0.0
        for name, vals in scaled.items():
            v = vals[i]
            if v is None:
                continue
            w = float(weights.get(name, 0.0))
            num += w * v
            den += w
        if policy == "zero":
            den = sum(float(weights.get(name, 0.0)) for name in scaled) or 1.0
        if den <= 0:
            index.append(0.0)
        else:
            index.append(num / den)

    return index, used, missing


def _rel_change(prev: float, curr: float, eps: float = 1e-9) -> Optional[float]:
    if prev is None or curr is None:
        return None
    denom = abs(prev) if abs(prev) > eps else eps
    return (curr - prev) / denom


def geometric_aggregate(
    signals: Dict[str, List[Optional[float]]],
    weights: Dict[str, float],
    labels: Sequence[str],
) -> List[Optional[float]]:
    """跨量纲信号的**加权几何聚合**。

    为什么必须用几何聚合而不是算术聚合来拟合半衰期？

    1. 各信号量纲不同（浏览量 vs 美元成交额），算术聚合会被大数主导；
    2. 更重要的是：Attention Index 经过了 log10 标定，该变换会把
       **指数衰减压成线性衰减**，在其上拟合 λ 会系统性低估衰减速度
       （实测：真实 t½=67h 的序列在指数上拟合出 186h）。

    几何聚合保持各信号的乘性变化率：若各信号都以速率 r_i 指数衰减，
    聚合后仍是指数衰减，其衰减率为加权平均 —— 半衰期拟合因此正确。
    """
    out: List[Optional[float]] = []
    for i in range(len(labels)):
        num = den = 0.0
        for name, series in signals.items():
            v = series[i] if i < len(series) else None
            if v is None or v <= 0:
                continue
            w = float(weights.get(name, 0.0))
            num += w * math.log(v)
            den += w
        out.append(math.exp(num / den) if den > 0 else None)
    return out


def compute_growth_momentum(
    signals: Dict[str, List[Optional[float]]],
    weights: Dict[str, float],
    growth_window: int = 1,
    momentum_window: int = 1,
) -> Tuple[Optional[float], Optional[float]]:
    """Growth / Momentum 基于**各信号自身的变化率**加权平均。

    为什么不在标定后的 Attention Index 上做差分？

    Index 是 log 压缩 + 截断到 0-100 的尺度，跨源量纲被压平后，
    原始信号的真实动态会被严重低估（原始涨 75% 在指数上可能只涨 24%）。
    因此 Level 用标定后的指数（便于横向比较），
    而 Growth / Momentum 用各信号自身的相对变化率加权（保留真实动态）。

    Returns: (growth, momentum)
    """
    gw = max(1, int(growth_window))
    mw = max(1, int(momentum_window))

    def weighted_change(shift: int) -> Optional[float]:
        """以倒数第 (1+shift) 点为「当前」，倒数第 (1+shift+gw) 点为「基准」。"""
        num = den = 0.0
        for name, series in signals.items():
            if len(series) <= shift + gw:
                continue
            curr = series[-1 - shift]
            prev = series[-1 - shift - gw]
            if curr is None or prev is None:
                continue
            if prev <= 0:
                continue
            w = float(weights.get(name, 0.0))
            num += w * ((curr - prev) / abs(prev))
            den += w
        return (num / den) if den > 0 else None

    growth = weighted_change(0)
    prev_growth = weighted_change(mw)
    momentum = None
    if growth is not None and prev_growth is not None:
        momentum = growth - prev_growth
    return growth, momentum


def compute_momentum(
    index: Sequence[float],
    labels: Sequence[str],
    growth_window: int = 1,
    momentum_window: int = 1,
) -> Tuple[Optional[float], Optional[float], List[SeriesPoint]]:
    """从指数序列算 Growth（一阶）与 Momentum（二阶）。

    Returns: (growth, momentum, series_points)
    """
    series = [SeriesPoint(t=str(labels[i]), value=float(index[i])) for i in range(len(index))]
    if len(index) < 2:
        return None, None, series

    gw = max(1, int(growth_window))
    growth = _rel_change(index[-1 - gw], index[-1])

    momentum = None
    if len(index) >= gw + max(1, int(momentum_window)) + 1:
        mw = max(1, int(momentum_window))
        prev_growth = _rel_change(index[-1 - gw - mw], index[-1 - mw])
        if prev_growth is not None and growth is not None:
            momentum = growth - prev_growth

    return growth, momentum, series


def classify_trend(
    growth: Optional[float],
    momentum: Optional[float],
    up_threshold: float = 0.02,
    down_threshold: float = -0.02,
) -> str:
    """判定注意力趋势（核心：减速上涨 = 顶部预警）。"""
    if growth is None:
        return "unknown"
    if growth > up_threshold:
        if momentum is None:
            return "accelerating_up"
        # 增速仍在上升 -> 加速聚集；增速开始回落 -> 减速上涨（危险）
        return "accelerating_up" if momentum > 0 else "decelerating_up"
    if growth < down_threshold:
        return "declining"
    return "flat"


def build_attention_metrics(
    signals: Dict[str, List[Optional[float]]],
    weights: Dict[str, float],
    labels: Sequence[str],
    cfg: dict,
) -> AttentionMetrics:
    """封装：合成指数 → 算动量 → 判趋势。"""
    att_cfg = (cfg or {}).get("attention", {})
    mom_cfg = (cfg or {}).get("momentum", {})
    ranges = {**DEFAULT_RANGES, **(att_cfg.get("reference_ranges") or {})}

    index, used, missing = compute_index_series(
        signals,
        weights,
        labels,
        ranges=ranges,
        policy=att_cfg.get("missing_signal_policy", "redistribute"),
    )
    if not index:
        return AttentionMetrics(note="无任何可用注意力信号", missing_sources=missing)

    growth, momentum, series = compute_momentum(
        index,
        labels,
        growth_window=mom_cfg.get("growth_window", 1),
        momentum_window=mom_cfg.get("momentum_window", 1),
    )
    # Level 用标定指数（便于横向比较）；Growth/Momentum 用各信号自身变化率（保留真实动态）
    g2, m2 = compute_growth_momentum(
        signals,
        weights,
        growth_window=mom_cfg.get("growth_window", 1),
        momentum_window=mom_cfg.get("momentum_window", 1),
    )
    if g2 is not None:
        growth, momentum = g2, m2
    trend = classify_trend(
        growth,
        momentum,
        up_threshold=mom_cfg.get("up_threshold", 0.02),
        down_threshold=mom_cfg.get("down_threshold", -0.02),
    )

    note = None
    if len(index) < 2:
        note = "仅有单点快照，无法计算增速与动量（Growth/Momentum 不可用）"
    elif len(index) < 4:
        note = "序列较短，动量（二阶）可靠性有限"

    return AttentionMetrics(
        level=float(index[-1]),
        growth=growth,
        momentum=momentum,
        trend=trend,
        series=series,
        used_sources=used,
        missing_sources=missing,
        note=note,
    )
