# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Attention Half-Life：一个事件的注意力能维持多久？

从峰值之后拟合指数衰减：

    A(t) = A_peak · exp(-λ · Δt)      ⇒      t½ = ln(2) / λ

半衰期把"热度"变成了可比较的时间尺度，用来区分事件类型：
突发新闻（小时级）/ 明星事件（天级）/ 影视（周级）/ 品牌（月级）/ 科技趋势（年级）。
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from .models import HalfLifeResult, SeriesPoint

__all__ = ["estimate_half_life", "classify_event", "DEFAULT_BENCHMARKS"]

DEFAULT_BENCHMARKS = {
    "breaking_news": 6.0,     # 小时
    "celebrity": 72.0,        # 3 天
    "film": 336.0,            # 14 天
    "brand": 2160.0,          # 90 天
    "tech_trend": 8760.0,     # 365 天
}

EVENT_CLASS_LABELS = {
    "breaking_news": "突发新闻型（小时级）",
    "celebrity": "明星/人物事件型（天级）",
    "film": "影视作品型（周级）",
    "brand": "品牌事件型（月级）",
    "tech_trend": "科技趋势型（月/年级）",
}


def _ols_slope(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """最小二乘拟合 y = a + b·x，返回 (b, r²)。"""
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return b, r2


def estimate_half_life(
    series: Sequence[SeriesPoint],
    hours_per_step: float = 24.0,
    min_points_after_peak: int = 3,
    benchmarks: Optional[dict] = None,
) -> HalfLifeResult:
    """从注意力序列估计半衰期（小时）。

    取序列峰值，对其后的点做 ln(A) 对时间的线性回归，斜率 = -λ。
    """
    benchmarks = benchmarks or DEFAULT_BENCHMARKS
    if not series or len(series) < 2:
        return HalfLifeResult(status="unavailable")

    values = [p.value for p in series]
    peak_idx = max(range(len(values)), key=lambda i: values[i])
    peak_value = values[peak_idx]

    # 峰值就是最后一个观测点 —— 说明还没开始下跌，谈不上"衰减"
    if peak_idx >= len(values) - 1:
        return HalfLifeResult(
            status="not_decaying",
            peak_index=peak_idx,
            peak_value=peak_value,
        )

    tail = values[peak_idx:]
    if len(tail) < max(2, min_points_after_peak):
        return HalfLifeResult(
            status="insufficient_data",
            peak_index=peak_idx,
            peak_value=peak_value,
        )

    xs = [i * float(hours_per_step) for i in range(len(tail))]
    # 过滤非正值（log 未定义）
    pairs = [(x, v) for x, v in zip(xs, tail) if v > 0]
    if len(pairs) < 2:
        return HalfLifeResult(status="insufficient_data", peak_index=peak_idx, peak_value=peak_value)

    xs_f = [p[0] for p in pairs]
    ys_f = [math.log(p[1]) for p in pairs]
    slope, r2 = _ols_slope(xs_f, ys_f)

    if slope >= 0:
        # 峰值之后仍在上升 —— 尚未进入衰减期
        return HalfLifeResult(
            status="not_decaying",
            peak_index=peak_idx,
            peak_value=peak_value,
            r_squared=r2,
        )

    lam = -slope
    halflife = math.log(2.0) / lam
    return HalfLifeResult(
        halflife_hours=halflife,
        decay_constant=lam,
        peak_index=peak_idx,
        peak_value=peak_value,
        r_squared=r2,
        status="ok",
        event_class=classify_event(halflife, benchmarks),
    )


def classify_event(halflife_hours: float, benchmarks: Optional[dict] = None) -> str:
    """按半衰期把事件归入最接近的量级类别。"""
    benchmarks = benchmarks or DEFAULT_BENCHMARKS
    best_key, best_dist = None, float("inf")
    for key, hours in benchmarks.items():
        # 在 log 尺度上比较距离（半衰期跨小时到年，量级差异巨大）
        dist = abs(math.log10(max(halflife_hours, 1e-6)) - math.log10(max(float(hours), 1e-6)))
        if dist < best_dist:
            best_dist, best_key = dist, key
    return best_key or "celebrity"


def event_class_label(key: Optional[str]) -> str:
    if not key:
        return "—"
    return EVENT_CLASS_LABELS.get(key, key)
