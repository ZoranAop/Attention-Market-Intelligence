# ---------------------------------------------------------------------------
# attention-market · v0.3 · 4-axis tests
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""v0.3 新增测试：4 轴统一接口（core/axes.py）。

覆盖：
  - derive_axis_weights_from_signals：v0.2 signals → v0.3 axis_weights 派生
  - compute_axis_readings：从已有 AttentionMetrics/MarketSnapshot 派生 4 轴
  - axis_readings_from_legacy_signals：兼容性接口
"""

from __future__ import annotations

from attention_market.core.asset import SignalAxis
from attention_market.core.axes import (
    compute_axis_readings,
    derive_axis_weights_from_signals,
    axis_readings_from_legacy_signals,
    DEFAULT_AXIS_WEIGHTS,
)
from attention_market.core.models import (
    AttentionMetrics,
    HalfLifeResult,
    MarketSnapshot,
    SeriesPoint,
)
from attention_market.core.registry import get_profile, AssetKind


# -------- derive_axis_weights_from_signals --------


def test_derive_empty_signals_returns_default():
    weights = derive_axis_weights_from_signals({})
    assert weights == DEFAULT_AXIS_WEIGHTS
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_derive_legacy_signals_groups_correctly():
    signals = {
        "onchain_txns": 0.30, "onchain_makers": 0.10, "volume": 0.10,    # onchain 0.50
        "wikipedia": 0.15, "hackernews": 0.10, "reddit": 0.05,           # attention 0.30
        "tvl": 0.20,                                                       # fundamental 0.20
    }
    weights = derive_axis_weights_from_signals(signals)
    # 总和必须归一化
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert abs(weights["onchain"] - 0.50) < 1e-9
    assert abs(weights["attention"] - 0.30) < 1e-9
    assert abs(weights["fundamental"] - 0.20) < 1e-9
    assert weights["macro"] == 0.0


def test_derive_unknown_signal_goes_to_attention():
    signals = {"volume": 0.5, "mystery_metric": 0.5}
    weights = derive_axis_weights_from_signals(signals)
    # mystery_metric 应保守归入 attention
    assert weights["attention"] > 0
    assert weights["onchain"] > 0


# -------- compute_axis_readings --------


def test_compute_axis_readings_attention_unavailable_when_no_data():
    profile = get_profile(AssetKind.MEME)
    readings = compute_axis_readings(
        attention=AttentionMetrics(),
        market=MarketSnapshot(),
        halflife=HalfLifeResult(),
        conversion=None,
        profile=profile,
    )
    assert SignalAxis.ATTENTION.value in readings
    assert readings[SignalAxis.ATTENTION.value].unavailable is True
    assert readings[SignalAxis.ONCHAIN.value].unavailable is True
    # fundamental / macro 是 v0.3 占位
    assert readings[SignalAxis.FUNDAMENTAL.value].unavailable is True
    assert readings[SignalAxis.MACRO.value].unavailable is True


def test_compute_axis_readings_attention_ok():
    profile = get_profile(AssetKind.MEME)
    readings = compute_axis_readings(
        attention=AttentionMetrics(
            level=72.0, growth=0.15, momentum=-0.05, trend="decelerating_up",
            used_sources=["wikipedia"], series=[SeriesPoint(t="2026-01-01", value=10.0)],
        ),
        market=MarketSnapshot(volume_h24=50000.0, liquidity_usd=200000.0,
                              txns_h24_buys=120, txns_h24_sells=80),
        halflife=HalfLifeResult(halflife_hours=48.0, status="ok"),
        conversion=None,
        profile=profile,
    )
    att = readings[SignalAxis.ATTENTION.value]
    assert att.level == 72.0
    assert att.growth == 0.15
    assert att.half_life_h == 48.0
    assert att.unavailable is False
    # z_score 应由 growth 派生
    assert att.z_score is not None


def test_compute_axis_readings_macro_pulls_from_regime():
    from attention_market.core.models import RegimeReading, RegimeKind
    profile = get_profile(AssetKind.L1)
    regime = RegimeReading(
        kind=RegimeKind.BEAR, risk_score=70.0, confidence=0.83,
        available_signals=["btc_30d"], missing_signals=["dxy_30d"],
    )
    readings = compute_axis_readings(
        attention=AttentionMetrics(level=50.0, growth=0.05),
        market=MarketSnapshot(volume_h24=100000.0, liquidity_usd=1000000.0),
        halflife=HalfLifeResult(),
        conversion=None,
        profile=profile,
        regime=regime,
    )
    macro = readings[SignalAxis.MACRO.value]
    # macro 应该从 regime 派生，unavailable=False
    assert macro.unavailable is False
    assert macro.level is not None
    assert macro.source_breakdown.get("regime_kind") == "Bear"


# -------- axis_readings_from_legacy_signals --------


def test_legacy_adapter_returns_all_unavailable():
    readings = axis_readings_from_legacy_signals({"volume": 0.5})
    for axis in SignalAxis:
        assert readings[axis.value].unavailable is True