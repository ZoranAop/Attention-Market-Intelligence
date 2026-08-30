# ---------------------------------------------------------------------------
# attention-market · fundamental data provider (v0.3 placeholder)
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""基本面数据 provider（占位，v0.3.1 接入 DeFiLlama + Token Terminal）。

返回结构：每个函数都返回 ``(data_dict_or_none, status_str)``。
status ∈ {"ok", "not_found", "unsupported_chain", "http_error", "disabled"}。
任何失败都不抛异常 —— 框架要求"拿不到数据绝不显示成通过"。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..utils.http import get_json

__all__ = ["fetch_defillama_tvl", "fetch_token_terminal_revenue", "parse_fundamental"]


# ---------------------------------------------------------------------------
# DeFiLlama (free, no key required)
# https://api.llama.fi/protocol/{slug}
# ---------------------------------------------------------------------------

DEFILLAMA_BASE = "https://api.llama.fi"


def fetch_defillama_tvl(slug: Optional[str], cfg: dict) -> Tuple[Optional[Dict[str, Any]], str]:
    """拉取 DeFiLlama 上的协议 TVL。

    返回 ``({slug, tvl_usd, chain, category}, status)``；失败时 data=None。
    """
    if not slug:
        return None, "not_found"
    p = (((cfg or {}).get("providers", {}) or {}).get("fundamental", {}) or {}).get(
        "defillama", {}
    ) or {}
    if p.get("enabled") is False:
        return None, "disabled"
    url = f"{p.get('base_url', DEFILLAMA_BASE)}/protocol/{slug}"
    raw = get_json(url, timeout=int(p.get("timeout", 15)))
    if not raw or not isinstance(raw, dict):
        return None, "http_error"
    return (
        {
            "slug": slug,
            "tvl_usd": raw.get("tvl"),
            "chain": raw.get("chain"),
            "category": raw.get("category"),
            "source": "defillama",
        },
        "ok",
    )


# ---------------------------------------------------------------------------
# Token Terminal (free tier / placeholder for v0.3)
# ---------------------------------------------------------------------------


def fetch_token_terminal_revenue(project_id: Optional[str], cfg: dict) -> Tuple[Optional[Dict[str, Any]], str]:
    """占位：v0.3.1 接入 Token Terminal。当前直接返回 disabled。"""
    p = (((cfg or {}).get("providers", {}) or {}).get("fundamental", {}) or {}).get(
        "token_terminal", {}
    ) or {}
    if p.get("enabled") is False or not project_id:
        return None, "disabled"
    # 真实接入位置（v0.3.1+）
    return None, "disabled"


def parse_fundamental(tvl_data: Optional[Dict[str, Any]], rev_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """合并 TVL + Revenue 为 AxisReading 友好的 dict。"""
    result: Dict[str, Any] = {
        "tvl_usd": None,
        "revenue_usd": None,
        "chain": None,
        "category": None,
        "available": False,
        "sources": [],
    }
    if tvl_data:
        result["tvl_usd"] = tvl_data.get("tvl_usd")
        result["chain"] = tvl_data.get("chain")
        result["category"] = tvl_data.get("category")
        result["sources"].append("defillama")
        result["available"] = True
    if rev_data:
        result["revenue_usd"] = rev_data.get("revenue_usd")
        result["sources"].append("token_terminal")
        result["available"] = True
    return result