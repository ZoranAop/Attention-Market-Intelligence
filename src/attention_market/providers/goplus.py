# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""GoPlus provider —— 合约安全检测（模型 E 门控的数据来源）。

免费、无需 API Key，仅覆盖 EVM 链。
注意：主域 api.goplus.io 时常超时，本项目默认使用 api.gopluslabs.io。

这个 provider 的价值在于**识破错币**：它能直接读出合约的真实
token_name / symbol / holder_count / is_in_dex，从而暴露"挂羊头卖狗肉"的合约。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..core.models import SecurityInfo
from ..utils.http import get_json
from ..utils.normalize import to_float, to_int

__all__ = ["CHAIN_IDS", "fetch_security", "parse_security", "is_supported_chain"]

BASE_URL = "https://api.gopluslabs.io/api/v1"

CHAIN_IDS: Dict[str, str] = {
    "ethereum": "1",
    "eth": "1",
    "bsc": "56",
    "binance": "56",
    "base": "8453",
    "arbitrum": "42161",
    "optimism": "10",
    "polygon": "137",
    "polygon_pos": "137",
    "avalanche": "43114",
    "fantom": "250",
}


def _cfg_of(cfg: dict) -> dict:
    return ((cfg or {}).get("providers", {}) or {}).get("goplus", {}) or {}


def is_supported_chain(chain: str) -> bool:
    return (chain or "").lower() in CHAIN_IDS


def fetch_security_ex(address: str, chain: str, cfg: dict) -> tuple[Optional[Dict[str, Any]], str]:
    """返回 (raw, status)。

    status 取值：
        ok                 —— 拿到数据
        not_found          —— 接口正常，但该合约未被收录（极新 / 不存在于此链）
                              ⚠ 这本身就是风险信号，需与「接口挂了」区分开
        unsupported_chain  —— 非 EVM 链，GoPlus 不覆盖
        http_error         —— 请求失败/超时
        disabled / no_address
    """
    p = _cfg_of(cfg)
    if p.get("enabled") is False:
        return None, "disabled"
    if not address:
        return None, "no_address"
    chain_id = CHAIN_IDS.get((chain or "").lower())
    if not chain_id:
        return None, "unsupported_chain"

    url = f"{p.get('base_url', BASE_URL)}/token_security/{chain_id}"
    data = get_json(
        url,
        params={"contract_addresses": address.lower()},
        timeout=int(p.get("timeout", 20)),
        retries=int(((cfg or {}).get("http", {}) or {}).get("retries", 2)),
    )
    if not data or not isinstance(data, dict):
        return None, "http_error"
    result = data.get("result") or {}
    raw = result.get(address.lower())
    if raw is None:
        return None, "not_found"
    return raw, "ok"


def fetch_security(address: str, chain: str, cfg: dict) -> Optional[Dict[str, Any]]:
    """返回 GoPlus 的 result 字典（key 为小写合约地址）；无数据则 None。"""
    raw, _status = fetch_security_ex(address, chain, cfg)
    return raw


def _flag(value: Any) -> Optional[bool]:
    """GoPlus 用 "1"/"0" 字符串表示布尔。"""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


def parse_security(raw: Optional[Dict[str, Any]]) -> SecurityInfo:
    """把 GoPlus 原始结果解析为 SecurityInfo。"""
    if not raw:
        return SecurityInfo(available=False)

    lp_holders = raw.get("lp_holders") or []
    holders = raw.get("holders") or []

    lp_locked: Optional[bool] = None
    lp_owner_controlled: Optional[bool] = None
    for lp in lp_holders:
        locked = _flag(lp.get("is_locked"))
        if locked is True:
            lp_locked = True
        elif lp_locked is None and locked is False:
            lp_locked = False
        # 若 LP 由未锁定的普通地址持有（尤其疑似 owner/creator）
        if lp.get("is_contract") in (0, "0", False) and locked is not True:
            lp_owner_controlled = True
    if lp_holders and lp_locked is None:
        lp_locked = False

    top_percent: Optional[float] = None
    for h in holders:
        pct = to_float(h.get("percent"))
        if pct is not None:
            top_percent = pct if top_percent is None else max(top_percent, pct)

    return SecurityInfo(
        available=True,
        is_honeypot=_flag(raw.get("is_honeypot")),
        is_mintable=_flag(raw.get("is_mintable")),
        is_in_dex=_flag(raw.get("is_in_dex")),
        is_open_source=_flag(raw.get("is_open_source")),
        lp_locked=lp_locked,
        lp_owner_controlled=lp_owner_controlled,
        holder_count=to_int(raw.get("holder_count")),
        top_holder_percent=top_percent,
        buy_tax=to_float(raw.get("buy_tax")),
        sell_tax=to_float(raw.get("sell_tax")),
        token_name=raw.get("token_name"),
        token_symbol=raw.get("token_symbol"),
        raw=raw,
    )
