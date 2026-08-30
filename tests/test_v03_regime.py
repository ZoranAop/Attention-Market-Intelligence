# ---------------------------------------------------------------------------
# attention-market · v0.3 · market regime tests
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""v0.3 新增测试：Market Regime 分类（core/regime.py）。

覆盖：
  - 6 信号 → risk_score 合成
  - 4 档阈值分箱
  - 强制覆盖（Crisis / Bull 附加条件）
  - 信号缺失降级
"""

from __future__ import annotations

from attention_market.core.regime import (
    RegimeSignal,
    classify_regime,
    DEFAULT_REGIME_WEIGHTS,
    DEFAULT_RISK_BANDS,
)
from attention_market.core.models import RegimeKind


def _sig(name: str, value):
    return RegimeSignal(name, value, available=True)


def test_all_unavailable_returns_unknown():
    signals = {k: RegimeSignal(k, None, available=False) for k in DEFAULT_REGIME_WEIGHTS}
    r = classify_regime(signals)
    assert r.kind == RegimeKind.UNKNOWN
    assert r.risk_score is None
    assert r.confidence == 0.0
    assert len(r.missing_signals) == 6


def test_more_than_three_missing_returns_unknown():
    signals = {k: RegimeSignal(k, None, available=False) for k in DEFAULT_REGIME_WEIGHTS}
    signals["btc_30d"] = _sig("btc_30d", 0.05)
    signals["vix"] = _sig("vix", 15.0)
    r = classify_regime(signals)
    assert r.kind == RegimeKind.UNKNOWN
    assert "btc_30d" in r.available_signals
    assert "vix" in r.available_signals


def test_bull_when_btc_and_funding_friendly():
    signals = {
        "btc_30d": _sig("btc_30d", 0.15),
        "dxy_30d": _sig("dxy_30d", -0.01),
        "ust2y_level": _sig("ust2y_level", 0.04),
        "ust2y_chg": _sig("ust2y_chg", -0.001),
        "funding": _sig("funding", 0.0001),
        "vix": _sig("vix", 12.0),
    }
    r = classify_regime(signals)
    assert r.kind == RegimeKind.BULL
    assert r.confidence == 1.0
    assert r.risk_score < 40


def test_bear_classification():
    signals = {
        "btc_30d": _sig("btc_30d", -0.15),
        "dxy_30d": _sig("dxy_30d", 0.02),
        "ust2y_level": _sig("ust2y_level", 0.05),
        "ust2y_chg": _sig("ust2y_chg", 0.002),
        "funding": _sig("funding", -0.0003),
        "vix": _sig("vix", 25.0),
    }
    r = classify_regime(signals)
    assert r.kind == RegimeKind.BEAR


def test_crisis_override_when_vix_extreme():
    """即使 risk_score 不到 80，VIX>35 也应强制 Crisis。"""
    signals = {
        "btc_30d": _sig("btc_30d", 0.10),
        "dxy_30d": _sig("dxy_30d", -0.01),
        "ust2y_level": _sig("ust2y_level", 0.04),
        "ust2y_chg": _sig("ust2y_chg", 0.0),
        "funding": _sig("funding", 0.0),
        "vix": _sig("vix", 40.0),
    }
    r = classify_regime(signals)
    assert r.kind == RegimeKind.CRISIS


def test_crisis_override_when_btc_collapse():
    signals = {
        "btc_30d": _sig("btc_30d", -0.30),
        "dxy_30d": _sig("dxy_30d", 0.0),
        "ust2y_level": _sig("ust2y_level", 0.045),
        "ust2y_chg": _sig("ust2y_chg", 0.0),
        "funding": _sig("funding", 0.0),
        "vix": _sig("vix", 18.0),
    }
    r = classify_regime(signals)
    assert r.kind == RegimeKind.CRISIS


def test_range_when_neutral():
    signals = {
        "btc_30d": _sig("btc_30d", 0.0),
        "dxy_30d": _sig("dxy_30d", 0.0),
        "ust2y_level": _sig("ust2y_level", 0.045),
        "ust2y_chg": _sig("ust2y_chg", 0.0),
        "funding": _sig("funding", 0.0),
        "vix": _sig("vix", 18.0),
    }
    r = classify_regime(signals)
    assert r.kind in (RegimeKind.RANGE, RegimeKind.BULL)  # 边界附近允许 RANGE


def test_confidence_scales_with_availability():
    """3/6 可用 → confidence=0.5 → 继续计算（RFC §4.4：≥4 缺失才 Unknown）。"""
    signals = {k: RegimeSignal(k, None, available=False) for k in DEFAULT_REGIME_WEIGHTS}
    signals["btc_30d"] = _sig("btc_30d", 0.0)
    signals["vix"] = _sig("vix", 20.0)
    signals["dxy_30d"] = _sig("dxy_30d", 0.0)
    r = classify_regime(signals)
    assert r.kind != RegimeKind.UNKNOWN
    assert 0 < r.confidence < 1.0
    assert math.isclose(r.confidence, 0.5, rel_tol=1e-9)


def test_confidence_scales_4_of_6_unavailable_returns_unknown():
    """4/6 不可用 → 触发 §4.4 的 Unknown 路径。"""
    signals = {k: RegimeSignal(k, None, available=False) for k in DEFAULT_REGIME_WEIGHTS}
    signals["btc_30d"] = _sig("btc_30d", 0.05)
    signals["vix"] = _sig("vix", 20.0)
    r = classify_regime(signals)
    assert r.kind == RegimeKind.UNKNOWN
    assert r.confidence == 0.0


def test_partial_unknown_signals_dropped():
    """只传 1 个信号 → 触发「≥4 missing」Unknown 路径。"""
    signals = {"btc_30d": _sig("btc_30d", 0.05)}
    r = classify_regime(signals)
    # 1/6 available → 5 missing → Unknown
    assert r.kind == RegimeKind.UNKNOWN
    assert r.confidence == 0.0


import math