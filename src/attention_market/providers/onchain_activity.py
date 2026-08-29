# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""场内行为代理（Engagement → Action 层）。

概念上的分工：

    场外注意力 Attention  = 有多少人"看见"了（搜索、社交、新闻）
    场内行为   Action      = 有多少人真的动了（交易笔数、参与地址、成交额）

场内行为是所有注意力信号里**最难伪造**的一类（刷量需要真实 gas 成本），
因此在默认权重里占比最高。它同时也是计算「注意力弹性 β」的分母侧。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..core.models import MarketSnapshot, SeriesPoint

__all__ = ["snapshot_signals", "series_from_volume", "summarize_action"]


def snapshot_signals(market: MarketSnapshot) -> Dict[str, Optional[float]]:
    """从 24h 市场快照提取场内行为信号（供 Attention Index 使用）。"""
    return {
        "onchain_txns": float(market.txns_h24_total) if market.txns_h24_total is not None else None,
        "onchain_makers": float(market.makers_h24) if market.makers_h24 is not None else None,
        "volume": market.volume_h24,
    }


def series_from_volume(volume_series: Sequence[SeriesPoint]) -> List[SeriesPoint]:
    """成交量序列即「场内行为」的时间序列（按天）。"""
    return [SeriesPoint(t=p.t, value=p.value) for p in volume_series]


def summarize_action(market: MarketSnapshot) -> Dict[str, Optional[float]]:
    """用于报告展示的场内行为摘要。"""
    return {
        "txns_h24": float(market.txns_h24_total) if market.txns_h24_total is not None else None,
        "makers_h24": float(market.makers_h24) if market.makers_h24 is not None else None,
        "volume_h24": market.volume_h24,
        "buy_sell_ratio": (
            (market.txns_h24_buys / market.txns_h24_sells)
            if market.txns_h24_buys and market.txns_h24_sells
            else None
        ),
    }
