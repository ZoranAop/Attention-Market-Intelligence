# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""HTTP helper with retry + graceful degradation.

哲学：数据源失败是**常态**而非异常。所有请求失败都返回 None，
由上层把对应指标标记为 unavailable —— 绝不伪造数据填补空缺。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

DEFAULT_USER_AGENT = "attention-market/0.1 (+research; contact: local)"

__all__ = ["get_json", "get_text", "DEFAULT_USER_AGENT"]


def _backoff_sleep(attempt: int, backoff: float) -> None:
    time.sleep(backoff * (2 ** attempt))


def get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
    retries: int = 2,
    backoff: float = 0.8,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[Any]:
    """GET a URL and parse JSON. Returns None on any failure."""
    hdrs = {"User-Agent": user_agent, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - 任何失败都降级为 None
            last_err = exc
            if attempt < retries:
                _backoff_sleep(attempt, backoff)
    return None


def get_text(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
    retries: int = 2,
    backoff: float = 0.8,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Optional[str]:
    """GET a URL and return text. Returns None on any failure."""
    hdrs = {"User-Agent": user_agent}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.text
        except Exception:  # noqa: BLE001
            if attempt < retries:
                _backoff_sleep(attempt, backoff)
    return None
