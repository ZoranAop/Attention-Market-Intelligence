# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""DexScreener provider —— 市场快照（价格 / 流动性 / 成交量 / 交易活跃度）。

免费、无需 API Key、覆盖多链（EVM + Solana + TRON 等）。
文档: https://docs.dexscreener.com/api/reference
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.models import MarketSnapshot
from ..utils.http import get_json
from ..utils.normalize import to_float, to_int

__all__ = ["search_pairs", "fetch_by_contract", "parse_pair", "pick_best_pair"]

BASE_URL = "https://api.dexscreener.com"


def _cfg_of(cfg: dict) -> dict:
    return ((cfg or {}).get("providers", {}) or {}).get("dexscreener", {}) or {}


def search_pairs(query: str, cfg: dict) -> List[Dict[str, Any]]:
    """按名称/符号/地址搜索交易对。"""
    p = _cfg_of(cfg)
    if p.get("enabled") is False:
        return []
    url = f"{p.get('base_url', BASE_URL)}/latest/dex/search"
    data = get_json(
        url,
        params={"q": query},
        timeout=int(p.get("timeout", 20)),
        retries=int(((cfg or {}).get("http", {}) or {}).get("retries", 2)),
    )
    if not data or not isinstance(data, dict):
        return []
    return data.get("pairs") or []


def fetch_by_contract(address: str, cfg: dict) -> List[Dict[str, Any]]:
    """按合约地址取交易对。"""
    p = _cfg_of(cfg)
    if p.get("enabled") is False:
        return []
    url = f"{p.get('base_url', BASE_URL)}/latest/dex/tokens/{address}"
    data = get_json(
        url,
        timeout=int(p.get("timeout", 20)),
        retries=int(((cfg or {}).get("http", {}) or {}).get("retries", 2)),
    )
    if not data or not isinstance(data, dict):
        return []
    return data.get("pairs") or []


def pick_best_pair(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """选择流动性最高的交易对作为主观测对象。"""
    if not pairs:
        return None

    def liq(p: Dict[str, Any]) -> float:
        return to_float(((p.get("liquidity") or {}).get("usd")), 0.0) or 0.0

    return max(pairs, key=liq)


def parse_pair(pair: Dict[str, Any]) -> MarketSnapshot:
    """把 DexScreener 的 pair 对象解析为 MarketSnapshot。"""
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    txns = (pair.get("txns") or {}).get("h24") or {}
    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}
    liquidity = pair.get("liquidity") or {}

    buys = to_int(txns.get("buys"), None)
    sells = to_int(txns.get("sells"), None)
    if buys is None:
        buys = to_int(txns.get("buyers"), None)
    if sells is None:
        sells = to_int(txns.get("sellers"), None)

    makers = None
    buyers = to_int(txns.get("buyers"), None)
    sellers = to_int(txns.get("sellers"), None)
    if buyers is not None or sellers is not None:
        makers = (buyers or 0) + (sellers or 0)

    return MarketSnapshot(
        chain=pair.get("chainId"),
        dex=pair.get("dexId"),
        pair_address=pair.get("pairAddress"),
        base_symbol=base.get("symbol"),
        base_name=base.get("name"),
        base_address=base.get("address"),
        quote_symbol=quote.get("symbol"),
        price_usd=to_float(pair.get("priceUsd")),
        liquidity_usd=to_float(liquidity.get("usd")),
        market_cap=to_float(pair.get("marketCap")),
        fdv=to_float(pair.get("fdv")),
        volume_h24=to_float(volume.get("h24")),
        txns_h24_buys=buys,
        txns_h24_sells=sells,
        makers_h24=makers,
        price_change_h24=to_float(price_change.get("h24")),
        pair_created_at=to_int(pair.get("pairCreatedAt")),
    )
