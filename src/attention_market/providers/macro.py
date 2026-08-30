# ---------------------------------------------------------------------------
# attention-market · macro data provider (v0.3 placeholder)
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""宏观数据 provider（占位，v0.3.1 接入 FRED + Coinalyze）。

返回结构：``(value, status)``。
status ∈ {"ok", "not_found", "unsupported", "http_error", "disabled", "rate_limited"}。
任何失败绝不抛异常 —— 与框架整体降级策略一致。
"""

from __future__ import annotations

from typing import Optional, Tuple

from ..utils.http import get_json

__all__ = [
    "fetch_fred_series",
    "fetch_dxy_change",
    "fetch_ust2y",
    "fetch_vix",
    "fetch_avg_funding",
]


# ---------------------------------------------------------------------------
# FRED (需 API Key，默认禁用 —— 占位)
# https://api.stlouisfed.org/fred/series/observations
# ---------------------------------------------------------------------------


def fetch_fred_series(series_id: str, cfg: dict) -> Tuple[Optional[float], str]:
    """占位：v0.3.1 接入 FRED API。当前默认 disabled。"""
    p = (((cfg or {}).get("providers", {}) or {}).get("macro", {}) or {}).get("fred", {}) or {}
    if p.get("enabled") is False or not p.get("api_key"):
        return None, "disabled"
    # 真实接入占位
    return None, "disabled"


# ---------------------------------------------------------------------------
# DXY / UST2Y / VIX — 简单 wrapper（数据源待 v0.3.1 选定）
# ---------------------------------------------------------------------------


def fetch_dxy_change(cfg: dict) -> Tuple[Optional[float], str]:
    return fetch_fred_series("DTWEXBGS", cfg)


def fetch_ust2y(cfg: dict) -> Tuple[Optional[float], str]:
    """UST 2Y 当前水平。"""
    return fetch_fred_series("DGS2", cfg)


def fetch_ust2y_chg(cfg: dict) -> Tuple[Optional[float], str]:
    """UST 2Y 30d 变化 bp。"""
    return fetch_fred_series("DGS2CHG30D", cfg)


def fetch_vix(cfg: dict) -> Tuple[Optional[float], str]:
    """VIX 当前水平。"""
    return fetch_fred_series("VIXCLS", cfg)


# ---------------------------------------------------------------------------
# Coinalyze (free tier / placeholder)
# https://api.coinalyze.net/v1/funding-rate
# ---------------------------------------------------------------------------


def fetch_avg_funding(cfg: dict) -> Tuple[Optional[float], str]:
    """平均 Funding Rate（8h，主流币聚合）。"""
    p = (((cfg or {}).get("providers", {}) or {}).get("macro", {}) or {}).get("coinalyze", {}) or {}
    if p.get("enabled") is False or not p.get("api_key"):
        return None, "disabled"
    return None, "disabled"