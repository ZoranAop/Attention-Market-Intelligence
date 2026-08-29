# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""GeckoTerminal provider —— OHLCV 历史序列（免费、无需 API Key）。

用途：为 Attention Growth / Momentum / Half-Life 提供**时间序列**。
注意：并非所有链都被覆盖（如 TRON/SunPump 通常不可用）。
不可用时上层会降级为「仅快照模式」，并在报告中标注 Growth/Momentum 不可用。

API: GET /api/v2/networks/{network}/pools/{pool}/ohlcv/{timeframe}
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from ..core.models import SeriesPoint
from ..utils.http import get_json
from ..utils.normalize import to_float

__all__ = ["CHAIN_TO_NETWORK", "fetch_ohlcv", "ohlcv_to_series"]

BASE_URL = "https://api.geckoterminal.com/api/v2"

# DexScreener chainId → GeckoTerminal network id
CHAIN_TO_NETWORK: Dict[str, str] = {
    "ethereum": "eth",
    "eth": "eth",
    "bsc": "bsc",
    "binance": "bsc",
    "solana": "solana",
    "base": "base",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "polygon_pos": "polygon",
    "avalanche": "avax",
    "sui": "sui",
    "tron": "tron",          # 通常不被支持，失败时会自动降级
}


def _cfg_of(cfg: dict) -> dict:
    return ((cfg or {}).get("providers", {}) or {}).get("geckoterminal", {}) or {}


def fetch_ohlcv(
    chain: str,
    pool_address: str,
    cfg: dict,
    timeframe: Optional[str] = None,
    limit: Optional[int] = None,
) -> Optional[List[List[Any]]]:
    """返回原始 ohlcv_list：[[timestamp, o, h, l, c, volume], ...]（倒序，最新在前）。"""
    p = _cfg_of(cfg)
    if p.get("enabled") is False or not pool_address:
        return None

    network = CHAIN_TO_NETWORK.get((chain or "").lower())
    if not network:
        return None

    tf = timeframe or p.get("ohlcv_timeframe", "day")
    lim = int(limit or p.get("ohlcv_limit", 60))

    url = f"{p.get('base_url', BASE_URL)}/networks/{network}/pools/{pool_address}/ohlcv/{tf}"
    data = get_json(
        url,
        params={"aggregate": 1, "limit": lim},
        timeout=int(p.get("timeout", 20)),
        retries=int(((cfg or {}).get("http", {}) or {}).get("retries", 2)),
    )
    if not data or not isinstance(data, dict):
        return None
    return ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list")


def ohlcv_to_series(
    ohlcv: Optional[List[List[Any]]],
    column: int = 5,
    drop_last: bool = False,
) -> List[SeriesPoint]:
    """把 ohlcv_list 转成按时间**升序**的 SeriesPoint 列表。

    column: 4=收盘价, 5=成交量
    drop_last: 丢弃最新的一根 K 线。

        为什么需要它：GeckoTerminal 返回的最后一根日线是**当日尚未走完**的 candle，
        成交量只有几小时的累计值。若不丢弃，Growth / Momentum 会被这一根
        严重扭曲（实测出现过 -90% 的假信号）。
    """
    if not ohlcv:
        return []
    points: List[SeriesPoint] = []
    for row in ohlcv:
        if not row or len(row) <= column:
            continue
        ts = row[0]
        value = to_float(row[column])
        if value is None:
            continue
        try:
            label = _dt.datetime.utcfromtimestamp(int(ts)).date().isoformat()
        except (ValueError, OSError, OverflowError, TypeError):
            continue
        points.append(SeriesPoint(t=label, value=value))

    # GeckoTerminal 返回倒序（最新在前），反转成升序
    points.sort(key=lambda p: p.t)
    # 同一天可能有多条（不同 timeframe），保留最后一条
    dedup: Dict[str, float] = {}
    for p in points:
        dedup[p.t] = p.value
    out = [SeriesPoint(t=k, value=v) for k, v in sorted(dedup.items())]
    if drop_last and len(out) > 2:
        out = out[:-1]      # 丢掉未走完的当日 candle
    return out


def hours_per_step(timeframe: str = "day") -> float:
    return {"day": 24.0, "hour": 1.0, "minute": 1.0 / 60.0}.get(timeframe, 24.0)
