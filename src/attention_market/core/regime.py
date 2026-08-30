# ---------------------------------------------------------------------------
# attention-market · market regime classification (v0.3)
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Market Regime 分类（RFC v0.3 §4）。

输入：6 个信号（BTC 30d / DXY 30d / UST2Y level / UST2Y 30d / Funding / VIX）
输出：RegimeKind ∈ {Bull, Range, Bear, Crisis, Unknown}

降级：
    - ≥ 4 个信号不可用 → Unknown, confidence=0
    - 1-2 个不可用 → 用剩余等比分配权重继续算
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .models import RegimeKind, RegimeReading

__all__ = [
    "RegimeSignal",
    "classify_regime",
    "DEFAULT_REGIME_WEIGHTS",
    "DEFAULT_RISK_BANDS",
]


# ---------------------------------------------------------------------------
# Defaults (RFC §4.1)
# ---------------------------------------------------------------------------

DEFAULT_REGIME_WEIGHTS: Dict[str, float] = {
    "btc_30d": 0.35,
    "dxy_30d": 0.20,
    "ust2y_level": 0.075,
    "ust2y_chg": 0.075,
    "funding": 0.20,
    "vix": 0.10,
}

# 子分映射：0 = 最 risk-on，100 = 最 risk-off（RFC §4.2 表）
DEFAULT_RISK_BANDS: Dict[str, Dict[str, float]] = {
    "btc_30d": {"risk_on_max": 0.25, "neutral": 0.0, "risk_off_min": -0.25},
    "dxy_30d": {"risk_on_max": -0.03, "neutral": 0.0, "risk_off_min": 0.03},
    "ust2y_level": {"risk_on_max": 0.03, "neutral": 0.045, "risk_off_min": 0.055},
    "ust2y_chg": {"risk_on_max": -0.003, "neutral": 0.0, "risk_off_min": 0.003},
    "funding": {"risk_on_max": -0.0002, "neutral": 0.0, "risk_off_min": -0.0005},
    "vix": {"risk_on_max": 12.0, "neutral": 20.0, "risk_off_min": 35.0},
}


# ---------------------------------------------------------------------------
# Signal container
# ---------------------------------------------------------------------------


class RegimeSignal:
    """单个 Regime 输入信号。value 缺失时 ``available=False``。"""

    __slots__ = ("name", "value", "available")

    def __init__(self, name: str, value: Optional[float], available: bool = True):
        self.name = name
        self.value = value
        self.available = available and value is not None


# ---------------------------------------------------------------------------
# Subscore computation
# ---------------------------------------------------------------------------


def _interp(value: float, risk_on_max: float, neutral: float, risk_off_min: float) -> float:
    """线性插值到 0–100。

    语义（RFC §4.2）：
      risk_on_max  → 0 分（最 risk-on，例如 BTC +25%）
      neutral      → 50 分（例如 BTC 0%）
      risk_off_min → 100 分（最 risk-off，例如 BTC -25%）

    三点单调递增（risk_on_max < neutral < risk_off_min 在数值上不一定成立）
    —— 所以统一先按单调映射计算，再判断方向：
      当 risk_on_max < risk_off_min（数值越大越 risk-off）：
        中间值 (v - risk_on_max) / (risk_off_min - risk_on_max) → [0,1]
      当 risk_on_max > risk_off_min（数值越小越 risk-off，如 VIX）：
        (risk_on_max - v) / (risk_on_max - risk_off_min) → [0,1]
    """
    span = risk_off_min - risk_on_max
    if abs(span) < 1e-12:
        return 50.0
    if span > 0:
        # 标准：越大越 risk-off（BTC, UST2Y, VIX）
        ratio = (value - risk_on_max) / span
    else:
        # 越负越 risk-off（DXY 30d: -0.03 是 risk-on, +0.03 是 risk-off；
        # 但实际上 DXY 30d 正值=美元强=risk-off，所以 +0.03=risk_off_min，
        # 而 -0.03=risk_on_max —— DXY 不属于反向；看下 funding：-0.0002=risk_on,
        # -0.0005=risk_off_min，span < 0，确实是反向）
        ratio = (risk_on_max - value) / (-span)
    return max(0.0, min(100.0, ratio * 100.0))


def _signal_subscore(signal: RegimeSignal, bands: Dict[str, Dict[str, float]]) -> Optional[float]:
    if not signal.available or signal.value is None:
        return None
    cfg = bands.get(signal.name)
    if not cfg:
        return None
    return _interp(
        signal.value,
        float(cfg["risk_on_max"]),
        float(cfg["neutral"]),
        float(cfg["risk_off_min"]),
    )


# ---------------------------------------------------------------------------
# Main classification
# ---------------------------------------------------------------------------


def classify_regime(
    signals: Dict[str, RegimeSignal],
    weights: Optional[Dict[str, float]] = None,
    bands: Optional[Dict[str, Dict[str, float]]] = None,
) -> RegimeReading:
    """主入口。

    Parameters
    ----------
    signals : dict[str, RegimeSignal]
        6 个键之一：btc_30d / dxy_30d / ust2y_level / ust2y_chg / funding / vix
    weights, bands : optional override
    """
    weights = dict(weights or DEFAULT_REGIME_WEIGHTS)
    bands = dict(bands or DEFAULT_RISK_BANDS)

    subscores: Dict[str, float] = {}
    available_keys: List[str] = []
    missing_keys: List[str] = []
    for key in weights.keys():
        sig = signals.get(key)
        if sig is None:
            missing_keys.append(key)
            continue
        sub = _signal_subscore(sig, bands)
        if sub is None:
            missing_keys.append(key)
            continue
        subscores[key] = sub
        available_keys.append(key)

    # 全部不可用
    if len(available_keys) == 0:
        return RegimeReading(
            kind=RegimeKind.UNKNOWN,
            risk_score=None,
            confidence=0.0,
            available_signals=[],
            missing_signals=list(weights.keys()),
            note="全部信号不可用，无法判定 regime",
        )

    # ≥ 4 个不可用 → Unknown（RFC §4.4）
    if len(missing_keys) >= 4:
        return RegimeReading(
            kind=RegimeKind.UNKNOWN,
            risk_score=None,
            confidence=0.0,
            available_signals=available_keys,
            missing_signals=missing_keys,
            note="可用信号不足 2 个，无法可靠判定",
        )

    # 重新归一化权重（仅在可用信号上）
    used_weight = sum(weights[k] for k in available_keys)
    if used_weight <= 0:
        used_weight = 1.0
    risk_score = sum(subscores[k] * (weights[k] / used_weight) for k in available_keys)
    confidence = len(available_keys) / len(weights)

    # 强制覆盖规则（RFC §4.3）
    kind = _bucketize(risk_score, signals)

    return RegimeReading(
        kind=kind,
        risk_score=risk_score,
        confidence=confidence,
        available_signals=available_keys,
        missing_signals=missing_keys,
        note=f"基于 {len(available_keys)}/6 信号",
    )


def _bucketize(risk_score: float, signals: Dict[str, RegimeSignal]) -> RegimeKind:
    """分箱 + 强制覆盖。"""
    # Crisis 强制条件（满足任一）
    vix = signals.get("vix")
    btc = signals.get("btc_30d")
    funding = signals.get("funding")
    if vix and vix.available and vix.value is not None and vix.value > 35.0:
        return RegimeKind.CRISIS
    if btc and btc.available and btc.value is not None and btc.value < -0.25:
        return RegimeKind.CRISIS
    if funding and funding.available and funding.value is not None and funding.value < -0.0005:
        return RegimeKind.CRISIS

    # 区间分箱
    if risk_score >= 80:
        return RegimeKind.CRISIS
    if risk_score >= 60:
        return RegimeKind.BEAR
    if risk_score <= 39:
        # Bull 附加条件（避免过度乐观）
        if btc and btc.available and btc.value is not None and 0.10 <= btc.value <= 0.25:
            return RegimeKind.BULL
        if risk_score <= 20:
            return RegimeKind.BULL
        return RegimeKind.RANGE
    return RegimeKind.RANGE