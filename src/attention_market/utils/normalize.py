# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Normalization helpers: turning raw event timestamps into daily series.

大多数据源（Hacker News / Reddit / Wikipedia）给的是离散事件或每日计数，
这里统一成「按天对齐的序列」，便于后续做一阶/二阶差分与半衰期拟合。
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable, List, Optional, Sequence, Tuple

from ..core.models import SeriesPoint

__all__ = ["to_float", "to_int", "bucket_by_day", "align_series", "day_labels"]


def to_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def day_labels(days: int, end: Optional[_dt.date] = None) -> List[str]:
    """生成最近 days 天的日期标签（升序，含 end 当天）。"""
    end = end or _dt.date.today()
    return [(end - _dt.timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]


def bucket_by_day(
    events: Iterable[Tuple[float, float]],
    days: int,
    end: Optional[_dt.date] = None,
) -> List[SeriesPoint]:
    """把 (unix_timestamp, weight) 事件按天聚合。

    缺失的天补 0 —— 对计数型指标（帖子数、交易数）而言，0 是真实观测值。
    """
    labels = day_labels(days, end)
    index = {label: 0.0 for label in labels}
    start_date = _dt.date.fromisoformat(labels[0])

    for ts, weight in events:
        try:
            d = _dt.datetime.utcfromtimestamp(float(ts)).date()
        except (ValueError, OSError, OverflowError):
            continue
        if d < start_date:
            continue
        key = d.isoformat()
        if key in index:
            index[key] += float(weight or 0.0)

    return [SeriesPoint(t=label, value=index[label]) for label in labels]


def align_series(series: Sequence[SeriesPoint], labels: Sequence[str]) -> List[Optional[float]]:
    """把任意序列对齐到给定标签轴，缺失位置填 None（不是 0）。"""
    lookup = {p.t: p.value for p in series}
    return [lookup.get(label) for label in labels]
