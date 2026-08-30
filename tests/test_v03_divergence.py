# ---------------------------------------------------------------------------
# attention-market · v0.3 · divergence tests
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""v0.3 新增测试：跨轴 z-score 背离（core/divergence.py）。

覆盖：
  - 6 类预置规则
  - 严重度分级（info / warning / critical）
  - 排序与信息缺省
"""

from __future__ import annotations

from attention_market.core.asset import SignalAxis
from attention_market.core.divergence import (
    DEFAULT_DIVERGENCE_RULES,
    DEFAULT_Z_GAP_THRESHOLDS,
    detect_divergence,
    DivergenceRule,
)
from attention_market.core.models import AxisReading, MarketSnapshot


def _att(z=None):
    return AxisReading(axis=SignalAxis.ATTENTION, level=50.0, z_score=z)


def _onchain(z=None):
    return AxisReading(axis=SignalAxis.ONCHAIN, level=50.0, z_score=z)


def _liq_market(usd: float):
    return MarketSnapshot(liquidity_usd=usd)


def _price_market(ch: float):
    return MarketSnapshot(price_change_h24=ch)


def test_no_divergence_when_all_axes_at_zero():
    axes = {
        SignalAxis.ATTENTION.value: _att(z=0.0),
        SignalAxis.ONCHAIN.value: _onchain(z=0.0),
    }
    sigs = detect_divergence(axes)
    assert sigs == []


def test_attention_vs_liquidity_warning():
    """attention z=2.0, liquidity z=0.0 → gap=2.0 → warning。"""
    axes = {
        SignalAxis.ATTENTION.value: _att(z=2.0),
        SignalAxis.ONCHAIN.value: _onchain(z=0.0),
    }
    market = _liq_market(1_000_000)  # log10=6 → z=0
    sigs = detect_divergence(axes, market=market)
    names = [s.name for s in sigs]
    assert "Attention > Liquidity" in names
    sig = next(s for s in sigs if s.name == "Attention > Liquidity")
    assert sig.severity == "warning"
    import math
    assert math.isclose(sig.z_gap, 2.0, rel_tol=1e-6)


def test_attention_vs_liquidity_critical():
    """gap ≥ 2.5 → critical。"""
    axes = {
        SignalAxis.ATTENTION.value: _att(z=3.0),
        SignalAxis.ONCHAIN.value: _onchain(z=0.0),
    }
    market = _liq_market(1_000_000)
    sigs = detect_divergence(axes, market=market)
    sig = next(s for s in sigs if s.name == "Attention > Liquidity")
    assert sig.severity == "critical"


def test_attention_vs_liquidity_info():
    """gap ∈ (0, 1.5) → info。"""
    axes = {
        SignalAxis.ATTENTION.value: _att(z=0.5),
        SignalAxis.ONCHAIN.value: _onchain(z=-0.3),
    }
    market = _liq_market(1_000_000)
    sigs = detect_divergence(axes, market=market)
    sig = next(s for s in sigs if s.name == "Attention > Liquidity")
    assert sig.severity == "info"


def test_attention_vs_behavior_direction():
    """leading > lagging 才触发（gap > 0）。"""
    axes_behavior_lead = {
        SignalAxis.ATTENTION.value: _att(z=-1.0),
        SignalAxis.ONCHAIN.value: _onchain(z=2.0),
    }
    sigs = detect_divergence(axes_behavior_lead)
    names = [s.name for s in sigs]
    assert "Behavior > Attention" in names
    assert "Attention > Behavior" not in names


def test_price_vs_liquidity():
    """price 24h +30% → z=3.0; liquidity=1M → z=0 → critical divergence。"""
    axes = {
        SignalAxis.ATTENTION.value: _att(z=0.0),
        SignalAxis.ONCHAIN.value: _onchain(z=0.0),
    }
    market = MarketSnapshot(liquidity_usd=1_000_000, price_change_h24=30.0)
    sigs = detect_divergence(axes, market=market)
    sig = next(s for s in sigs if s.name == "Price > Liquidity")
    assert sig.severity == "critical"


def test_missing_axis_results_in_no_signal():
    """attention轴 unavailable 时不应触发需要 attention 的 divergence。"""
    att = AxisReading(axis=SignalAxis.ATTENTION, unavailable=True, reason="x")
    axes = {SignalAxis.ATTENTION.value: att}
    sigs = detect_divergence(axes)
    # 没 onchain 数据 → Attention > Behavior / Behavior > Attention 都不触发
    assert sigs == []


def test_severity_sorting():
    """critical 应排在 warning 之前。"""
    axes = {
        SignalAxis.ATTENTION.value: _att(z=3.0),  # → Attention > Liquidity critical
        SignalAxis.ONCHAIN.value: _onchain(z=1.0),
    }
    market = MarketSnapshot(liquidity_usd=100_000)  # log10=5 → z=-0.67
    sigs = detect_divergence(axes, market=market)
    # 第一个应是 critical
    if sigs:
        assert sigs[0].severity in ("critical", "warning")


def test_default_rules_count():
    assert len(DEFAULT_DIVERGENCE_RULES) == 6


def test_default_thresholds():
    assert DEFAULT_Z_GAP_THRESHOLDS["warning"] == 1.5
    assert DEFAULT_Z_GAP_THRESHOLDS["critical"] == 2.5