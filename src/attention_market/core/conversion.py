# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""④ Conversion Index：注意力到底有没有转化成行为？

    Attention ≠ Action —— 100 万人看到新闻，不等于 100 万人会购买。

这里用「注意力弹性 β」来度量转化：

    β = Δlog(Action) / Δlog(Attention)

用 log-log 最小二乘回归估计（斜率即弹性）：

    β ≥ 0.8   强转化   —— 注意力高效变成行为
    β ~ 0.2-0.8 部分转化 —— 有人在围观，有人在行动
    β < 0.2   弱转化   —— 注意力停留在外围（看热闹、嘲笑、无购买意愿）
    β < 0     背离     —— 注意力上升但行为下降（典型"叫好不叫座"）
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from .models import ConversionMetrics, SeriesPoint

__all__ = ["compute_conversion"]


def _ols(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
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


def compute_conversion(
    attention: Sequence[SeriesPoint],
    action: Sequence[SeriesPoint],
    high: float = 0.8,
    low: float = 0.2,
    min_points: int = 3,
) -> ConversionMetrics:
    """估计「注意力 → 行为」的转化弹性。

    ``attention`` 场外注意力序列（搜索/社交/新闻等）
    ``action``   场内行为序列（交易笔数 / 成交量 / 注册数等）
    """
    if not attention or not action:
        return ConversionMetrics(interpretation="unavailable", note="缺少注意力或行为序列")

    n = min(len(attention), len(action))
    if n < min_points:
        return ConversionMetrics(
            interpretation="unavailable",
            note=f"序列点不足（需要 ≥{min_points}，实际 {n}）",
        )

    xs, ys = [], []
    for i in range(n):
        a = attention[-n + i].value
        b = action[-n + i].value
        if a is not None and b is not None and a > 0 and b > 0:
            xs.append(math.log(a))
            ys.append(math.log(b))

    if len(xs) < min_points:
        return ConversionMetrics(interpretation="unavailable", note="可用于回归的有效点不足")

    beta, r2 = _ols(xs, ys)

    if beta >= high:
        interp = "强转化"
        note = "注意力高效转化为实际行为 —— 关注的确实是想行动的人"
    elif beta >= low:
        interp = "部分转化"
        note = "注意力部分转化为行为，存在明显的围观成分"
    elif beta >= 0:
        interp = "弱转化"
        note = "注意力大量停留在外围 —— 看热闹多于行动（想笑而非想买）"
    else:
        interp = "背离"
        note = "注意力上升而行为下降 —— 典型「叫好不叫座」，或注意力性质为负面/猎奇"

    return ConversionMetrics(elasticity=beta, r_squared=r2, interpretation=interp, note=note)
