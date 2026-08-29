# ---------------------------------------------------------------------------
# attention-market · tests
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Unit tests for the pure analysis layer (no network required)."""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from attention_market.core.attention import (  # noqa: E402
    DEFAULT_RANGES,
    build_attention_metrics,
    compute_index_series,
    scale_signal,
)
from attention_market.core.conversion import compute_conversion  # noqa: E402
from attention_market.core.gate import evaluate_gate  # noqa: E402
from attention_market.core.halflife import estimate_half_life  # noqa: E402
from attention_market.core.models import (  # noqa: E402
    MarketSnapshot,
    SecurityInfo,
    SeriesPoint,
)
from attention_market.core.quadrant import classify_quadrant  # noqa: E402
from attention_market.core.risk import score_risk  # noqa: E402


# ---------------------------------------------------------------------------
# Attention Index
# ---------------------------------------------------------------------------


def test_scale_signal_bounds():
    assert scale_signal("onchain_txns", 0, DEFAULT_RANGES) is None
    assert scale_signal("onchain_txns", None, DEFAULT_RANGES) is None
    lo, hi = DEFAULT_RANGES["onchain_txns"]
    assert scale_signal("onchain_txns", lo, DEFAULT_RANGES) == 0.0
    assert scale_signal("onchain_txns", hi, DEFAULT_RANGES) == 100.0
    # 超出上界应被截断到 100
    assert scale_signal("onchain_txns", hi * 10, DEFAULT_RANGES) == 100.0


def test_index_series_weighted_and_missing():
    labels = ["d1", "d2"]
    signals = {
        "onchain_txns": [1000.0, 2000.0],
        "wikipedia": [None, None],
    }
    weights = {"onchain_txns": 0.6, "wikipedia": 0.4}
    index, used, missing = compute_index_series(signals, weights, labels, policy="redistribute")
    # wikipedia 全缺失 -> 权重重分配，指数等于 onchain_txns 单独标定
    expected = scale_signal("onchain_txns", 2000.0, DEFAULT_RANGES)
    assert abs(index[-1] - expected) < 1e-6
    assert used == ["onchain_txns"]
    assert missing == ["wikipedia"]


def test_decelerating_up_is_top_warning():
    """增速为正但二阶为负 => 减速上涨（顶部预警），这是模型 B 的核心信号。"""
    labels = [f"d{i}" for i in range(5)]
    # 注意力仍在上升，但每日增量在变小：+40, +20, +10
    signals = {"wikipedia": [100.0, 140.0, 160.0, 170.0, 175.0]}
    weights = {"wikipedia": 1.0}
    metrics = build_attention_metrics(signals, weights, labels, {})
    assert metrics.growth is not None and metrics.growth > 0
    assert metrics.momentum is not None and metrics.momentum < 0
    assert metrics.trend == "decelerating_up"
    assert "顶部预警" in (metrics.top_warning or "")


# ---------------------------------------------------------------------------
# Half-Life
# ---------------------------------------------------------------------------


def test_half_life_recovery():
    """构造半衰期恰好 24h 的指数衰减，验证拟合能还原该值。"""
    series = [SeriesPoint(t=f"d{i}", value=100.0 * (0.5 ** i)) for i in range(12)]  # 步长 = 24h
    res = estimate_half_life(series, hours_per_step=24.0, min_points_after_peak=3)
    assert res.status == "ok"
    assert res.halflife_hours is not None
    assert abs(res.halflife_hours - 24.0) < 0.5
    assert res.r_squared is not None and res.r_squared > 0.99


def test_half_life_not_decaying():
    series = [SeriesPoint(t=f"d{i}", value=float(i + 1)) for i in range(10)]
    res = estimate_half_life(series, hours_per_step=24.0, min_points_after_peak=3)
    assert res.status == "not_decaying"
    assert res.halflife_hours is None


def test_half_life_insufficient():
    series = [SeriesPoint(t="d0", value=100.0), SeriesPoint(t="d1", value=50.0)]
    res = estimate_half_life(series, hours_per_step=24.0, min_points_after_peak=3)
    assert res.status == "insufficient_data"


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------


def test_conversion_beta_one():
    """action 与 attention 同比变化 => β = 1。"""
    att = [SeriesPoint(t=f"d{i}", value=v) for i, v in enumerate([10, 20, 30, 40, 50])]
    act = [SeriesPoint(t=f"d{i}", value=v) for i, v in enumerate([10, 20, 30, 40, 50])]
    res = compute_conversion(att, act)
    assert res.elasticity is not None
    assert abs(res.elasticity - 1.0) < 0.05
    assert res.interpretation == "强转化"


def test_conversion_weak():
    """注意力大幅增长而行为几乎不动 => 弱转化。"""
    att = [SeriesPoint(t=f"d{i}", value=v) for i, v in enumerate([100, 200, 400, 800])]
    act = [SeriesPoint(t=f"d{i}", value=v) for i, v in enumerate([10, 10.5, 11, 11.5])]
    res = compute_conversion(att, act)
    assert res.elasticity is not None and res.elasticity < 0.2
    assert res.interpretation == "弱转化"


def test_conversion_unavailable_on_short_series():
    att = [SeriesPoint(t="d0", value=1.0)]
    act = [SeriesPoint(t="d0", value=1.0)]
    res = compute_conversion(att, act)
    assert res.interpretation == "unavailable"


# ---------------------------------------------------------------------------
# Quadrant
# ---------------------------------------------------------------------------


def test_quadrant_matrix():
    assert classify_quadrant(0.10, 0.05).quadrant == "Expansion"
    assert classify_quadrant(0.10, -0.05).quadrant == "Divergence"
    assert classify_quadrant(-0.10, 0.05).quadrant == "Speculation"
    assert classify_quadrant(-0.10, -0.05).quadrant == "Decay"
    assert classify_quadrant(None, 0.05).quadrant == "Unknown"


# ---------------------------------------------------------------------------
# Gate (model E)
# ---------------------------------------------------------------------------


def test_gate_clean_contract_passes():
    sec = SecurityInfo(
        available=True,
        is_honeypot=False,
        is_mintable=False,
        is_in_dex=True,
        is_open_source=True,
        lp_locked=True,
        holder_count=5000,
        top_holder_percent=0.10,
    )
    gate = evaluate_gate(sec, MarketSnapshot(), fail_score=50)
    assert gate.applicable is True
    assert gate.score == 100


def test_gate_honeypot_is_hard_fail():
    """蜜罐属于硬性否决：即便总分未跌破阈值也必须判定不适用。"""
    sec = SecurityInfo(available=True, is_honeypot=True, is_in_dex=True)
    gate = evaluate_gate(sec, MarketSnapshot(), fail_score=50)
    assert gate.applicable is False
    assert any("蜜罐" in f for f in gate.failed)


def test_gate_non_evm_is_warning_only():
    """非 EVM 链拿不到安全数据 —— 只警告，不误判为不适用。"""
    sec = SecurityInfo(available=False)
    gate = evaluate_gate(sec, MarketSnapshot(liquidity_usd=100_000), fail_score=50)
    assert gate.applicable is True
    assert gate.warnings


def test_gate_not_in_dex_is_hard_fail():
    """错币/诱饵的典型特征：合约根本不在 DEX 交易。"""
    sec = SecurityInfo(available=True, is_in_dex=False, token_name="Pancake LPs")
    gate = evaluate_gate(sec, MarketSnapshot(), fail_score=50)
    assert gate.applicable is False


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------


def test_risk_high_for_shallow_pool_and_air_valuation():
    market = MarketSnapshot(
        liquidity_usd=132_130.0,
        market_cap=1_862_030.0,
        volume_h24=9_780_000.0,
    )
    from attention_market.core.models import AttentionMetrics, GateResult, QuadrantResult

    gate = GateResult(score=80, applicable=True)
    att = AttentionMetrics(level=60.0, growth=-0.2, trend="declining")
    quad = QuadrantResult(quadrant="Speculation")
    risk = score_risk(market, gate, att, quad, {})
    # 池子浅 + 14× 虚高 + 高换手 + 注意力衰退 => 应当落在「高/极高」
    assert risk.score >= 55
    assert risk.level in ("高", "极高")
    assert risk.components["attention_decay"] == 90.0
