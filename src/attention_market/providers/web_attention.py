# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""场外注意力代理（Attention 层的可插拔数据源）。

全部免费、无需 API Key：

    Wikipedia Pageviews — 对人物/事件/品牌/影视条目有效，反映"公众关注度"
    Hacker News         — 对科技/crypto 话题有效，用 Algolia 搜索 API
    Reddit              — 通用讨论热度（默认关闭：限流较严）

⚠️ 这些是**代理指标（proxy）**，不是全网注意力的直接测量。
   它们都可能被刷量/水军污染，用途是诊断与比较，不是预测。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..core.models import SeriesPoint
from ..utils.http import get_json
from ..utils.normalize import bucket_by_day

__all__ = [
    "wikipedia_series",
    "hackernews_series",
    "reddit_series",
    "wikipedia_scalar",
    "hackernews_scalar",
]


def _cfg_of(cfg: dict, name: str) -> dict:
    return ((cfg or {}).get("providers", {}) or {}).get(name, {}) or {}


def _retries(cfg: dict) -> int:
    return int(((cfg or {}).get("http", {}) or {}).get("retries", 2))


def _date_str(days: int, which: str) -> str:
    end = _dt.date.today()
    target = end if which == "end" else (end - _dt.timedelta(days=days - 1))
    return target.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Wikipedia Pageviews
# ---------------------------------------------------------------------------


def wikipedia_series(article: str, cfg: dict, days: Optional[int] = None) -> Optional[List[SeriesPoint]]:
    """取 Wikipedia 每日浏览量序列。

    article 为条目名（如 "Bitcoin" / "景甜"），会自动做 URL 编码。
    """
    p = _cfg_of(cfg, "wikipedia")
    if p.get("enabled") is False or not article:
        return None

    span = int(days or p.get("days", 14))
    project = p.get("project", "zh.wikipedia.org")
    url = (
        f"{p.get('base_url', 'https://wikimedia.org/api/rest_v1')}"
        f"/metrics/pageviews/per-article/{project}/all-access/user/"
        f"{quote(article, safe='')}/daily/{_date_str(span, 'start')}/{_date_str(span, 'end')}"
    )
    data = get_json(url, timeout=int(p.get("timeout", 20)), retries=_retries(cfg))
    if not data or not isinstance(data, dict):
        return None

    items = data.get("items") or []
    points: List[SeriesPoint] = []
    for it in items:
        ts = it.get("timestamp")  # YYYYMMDD
        views = it.get("views")
        if not ts or views is None:
            continue
        try:
            label = _dt.datetime.strptime(str(ts), "%Y%m%d").date().isoformat()
        except ValueError:
            continue
        points.append(SeriesPoint(t=label, value=float(views)))
    points.sort(key=lambda p: p.t)
    return points or None


def wikipedia_scalar(article: str, cfg: dict) -> Optional[float]:
    """最近一天（或最近可得一天）的浏览量。"""
    series = wikipedia_series(article, cfg)
    return series[-1].value if series else None


# ---------------------------------------------------------------------------
# Hacker News (Algolia)
# ---------------------------------------------------------------------------


def hackernews_series(query: str, cfg: dict, days: Optional[int] = None) -> Optional[List[SeriesPoint]]:
    """按查询词统计 Hacker News 每日相关条目数。"""
    p = _cfg_of(cfg, "hackernews")
    if p.get("enabled") is False or not query:
        return None

    span = int(days or ((cfg or {}).get("wikipedia", {}) or {}).get("days", 14) or 14)
    url = f"{p.get('base_url', 'https://hn.algolia.com/api/v1')}/search"
    data = get_json(
        url,
        params={"query": query, "tags": "story", "hitsPerPage": 200},
        timeout=int(p.get("timeout", 20)),
        retries=_retries(cfg),
    )
    if not data or not isinstance(data, dict):
        return None

    hits = data.get("hits") or []
    events = []
    for h in hits:
        ts = h.get("created_at_i")
        if ts:
            events.append((float(ts), 1.0))
    if not events:
        return None
    return bucket_by_day(events, span)


def hackernews_scalar(query: str, cfg: dict) -> Optional[float]:
    p = _cfg_of(cfg, "hackernews")
    if p.get("enabled") is False or not query:
        return None
    url = f"{p.get('base_url', 'https://hn.algolia.com/api/v1')}/search"
    data = get_json(
        url,
        params={"query": query, "tags": "story", "hitsPerPage": 1},
        timeout=int(p.get("timeout", 20)),
        retries=_retries(cfg),
    )
    if not data or not isinstance(data, dict):
        return None
    return float(data.get("nbHits") or 0) or None


# ---------------------------------------------------------------------------
# Reddit（默认关闭）
# ---------------------------------------------------------------------------


def reddit_series(query: str, cfg: dict, days: Optional[int] = None) -> Optional[List[SeriesPoint]]:
    """按查询词统计 Reddit 每日相关帖子数（易限流，默认关闭）。"""
    p = _cfg_of(cfg, "reddit")
    if p.get("enabled") is not True or not query:
        return None

    span = int(days or 14)
    url = f"{p.get('base_url', 'https://www.reddit.com')}/search.json"
    data = get_json(
        url,
        params={"q": query, "limit": 100, "sort": "new"},
        timeout=int(p.get("timeout", 20)),
        retries=_retries(cfg),
        user_agent="attention-market/0.1 (research)",
    )
    if not data or not isinstance(data, dict):
        return None
    children = (data.get("data") or {}).get("children") or []
    events = [(float((c.get("data") or {}).get("created_utc") or 0), 1.0) for c in children]
    events = [e for e in events if e[0] > 0]
    if not events:
        return None
    return bucket_by_day(events, span)
