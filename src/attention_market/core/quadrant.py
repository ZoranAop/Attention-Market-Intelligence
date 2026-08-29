# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Attention × Market 二维状态矩阵（⑤ Market Response）。

                市场上涨              市场下跌
    注意力 ↑   🔥 Expansion          ⚠️ Divergence
    注意力 ↓   ⚠️ Speculation         ❄️ Decay

正常链条是 Attention ↑ → Action ↑ → Price ↑。
任何偏离都携带信息：

    Attention ↑ + Price ↓   注意力与市场背离 —— 预期落空，或注意力性质为负面
    Attention ↓ + Price ↑   价格脱离注意力基础 —— 投机/控盘主导，最需警惕
"""

from __future__ import annotations

from typing import Optional

from .models import QuadrantResult

__all__ = ["classify_quadrant"]

QUADRANT_META = {
    "Expansion": ("🔥 注意力驱动型增长", "注意力与市场同步上行，通常处于事件扩散阶段"),
    "Divergence": ("⚠️ 注意力与市场背离", "注意力仍在聚集但市场不买账，可能存在预期落空或负面性质"),
    "Speculation": ("⚠️ 价格脱离注意力", "注意力已衰减而价格仍在上涨，投机或控盘主导，最需警惕"),
    "Decay": ("❄️ 同步衰退", "注意力与市场同步下行，通常进入冷却阶段"),
    "Neutral": ("— 中性/持平", "注意力或市场之一处于持平区间，信号不明确"),
    "Unknown": ("— 数据不足", "缺少注意力增速或价格变化数据"),
}


def _state(value: Optional[float], up: float, down: Optional[float] = None) -> str:
    if value is None:
        return "unknown"
    down = down if down is not None else -up
    if value > up:
        return "up"
    if value < down:
        return "down"
    return "flat"


def classify_quadrant(
    attention_growth: Optional[float],
    price_change: Optional[float],
    attention_threshold: float = 0.05,
    market_threshold: float = 0.02,
) -> QuadrantResult:
    """根据「注意力增速 × 市场变化」判定所处象限。

    ``price_change`` 用小数表示（0.05 = +5%）。
    """
    a_state = _state(attention_growth, attention_threshold)
    m_state = _state(price_change, market_threshold)

    if a_state == "unknown" or m_state == "unknown":
        quad = "Unknown"
    elif a_state == "up" and m_state == "up":
        quad = "Expansion"
    elif a_state == "up" and m_state == "down":
        quad = "Divergence"
    elif a_state == "down" and m_state == "up":
        quad = "Speculation"
    elif a_state == "down" and m_state == "down":
        quad = "Decay"
    else:
        quad = "Neutral"

    label, desc = QUADRANT_META.get(quad, ("", ""))
    return QuadrantResult(
        attention_state=a_state,
        market_state=m_state,
        quadrant=quad,
        label=label,
        description=desc,
    )
