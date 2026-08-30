# ---------------------------------------------------------------------------
# attention-market · v0.3 · phase tests
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""v0.3 新增测试：Phase 8 阶段 + Regime 强制降级（core/phase.py）。

覆盖：
  - 8 阶段短路匹配
  - Regime 强制降级（RFC §5.4）：
      * Bear/Crisis + Late Expansion → Peak
      * Bull + Drawdown → Decay
  - Profile phase_overrides 生效
  - 阈值缺失容忍（软要求）
"""

from __future__ import annotations

from attention_market.core.asset import SignalAxis
from attention_market.core.models import (
    AxisReading, RegimeKind, RegimeReading, DivergenceSignal,
)
from attention_market.core.phase import (
    apply_regime_downgrade,
    classify_phase,
    PHASE_STAGES,
)
from attention_market.core.registry import AssetKind, AssetProfile, get_profile


def _att(level=50, growth=0, momentum=0, hl=None, z=None):
    return AxisReading(
        axis=SignalAxis.ATTENTION, level=level, growth=growth,
        momentum=momentum, half_life_h=hl, z_score=z,
    )


def _regime(kind=RegimeKind.UNKNOWN, conf=0.0):
    return RegimeReading(kind=kind, risk_score=None, confidence=conf)


def _profile(kind=AssetKind.MEME):
    return get_profile(kind)


# -------- apply_regime_downgrade (RFC §5.4) --------


def test_apply_no_downgrade_for_range():
    for phase in ("Late Expansion", "Drawdown", "Peak", "Expansion"):
        new, applied = apply_regime_downgrade(phase, RegimeKind.RANGE)
        assert new == phase
        assert applied is False


def test_apply_late_expansion_becomes_peak_in_bear():
    new, applied = apply_regime_downgrade("Late Expansion", RegimeKind.BEAR)
    assert new == "Peak"
    assert applied is True


def test_apply_late_expansion_becomes_peak_in_crisis():
    new, applied = apply_regime_downgrade("Late Expansion", RegimeKind.CRISIS)
    assert new == "Peak"
    assert applied is True


def test_apply_drawdown_becomes_decay_in_bull():
    new, applied = apply_regime_downgrade("Drawdown", RegimeKind.BULL)
    assert new == "Decay"
    assert applied is True


def test_apply_unknown_regime_no_downgrade():
    new, applied = apply_regime_downgrade("Late Expansion", RegimeKind.UNKNOWN)
    assert new == "Late Expansion"
    assert applied is False


# -------- classify_phase: 8 阶段 --------


def test_stealth_when_low_level_growing():
    axes = {"attention": _att(level=20, growth=0.10)}
    tag = classify_phase(axes, _regime(), _profile())
    assert tag.primary == "Stealth"
    assert tag.regime_downgrade_applied is False


def test_expansion_when_level_mid_and_growing():
    axes = {"attention": _att(level=50, growth=0.08, momentum=0.02)}
    tag = classify_phase(axes, _regime(), _profile(), beta=0.6)
    assert tag.primary == "Expansion"


def test_late_expansion_when_momentum_negative_but_level_high():
    axes = {"attention": _att(level=75, growth=0.05, momentum=-0.02)}
    tag = classify_phase(axes, _regime(), _profile(), liquidity_growth=0.01)
    assert tag.primary == "Late Expansion"


def test_peak_requires_divergence():
    """Peak 需要 level≥80 + momentum<0 + 存在 divergence。"""
    axes_no_div = {"attention": _att(level=85, momentum=-0.05)}
    tag = classify_phase(axes_no_div, _regime(), _profile(), divergences=[])
    assert tag.primary != "Peak"

    axes_with_div = {"attention": _att(level=85, momentum=-0.05)}
    tag = classify_phase(
        axes_with_div, _regime(), _profile(),
        divergences=[DivergenceSignal(
            name="test", leading_axis="attention", lagging_axis="liquidity",
            z_gap=2.0, severity="warning", description="x",
        )],
    )
    assert tag.primary == "Peak"


def test_drawdown_when_level_mid_and_growth_negative():
    axes = {"attention": _att(level=60, growth=-0.10)}
    tag = classify_phase(
        axes, _regime(), _profile(),
        price_change_h24=-0.15, liquidity_growth=-0.10,
    )
    assert tag.primary == "Drawdown"


def test_decay_when_low_level_short_half_life():
    axes = {"attention": _att(level=30, hl=12.0)}
    tag = classify_phase(axes, _regime(), _profile())
    assert tag.primary == "Decay"


def test_recovery_when_z_positive_and_beta_back():
    axes = {"attention": _att(level=40, z=1.0)}
    tag = classify_phase(axes, _regime(), _profile(), beta=0.5)
    assert tag.primary == "Recovery"


def test_re_accumulation_when_level_mid_long_half_life():
    axes = {"attention": _att(level=50, hl=96.0)}
    tag = classify_phase(axes, _regime(), _profile())
    assert tag.primary == "Re-accumulation"


# -------- Regime 降级（集成） --------


def test_late_expansion_becomes_peak_when_bear():
    axes = {"attention": _att(level=75, growth=0.05, momentum=-0.02)}
    tag = classify_phase(
        axes, _regime(kind=RegimeKind.BEAR), _profile(),
        liquidity_growth=0.01,
    )
    assert tag.primary == "Peak"
    assert tag.regime_downgrade_applied is True
    assert any("regime_downgrade" in r for r in tag.rule_chain)


def test_drawdown_becomes_decay_when_bull():
    axes = {"attention": _att(level=60, growth=-0.10)}
    tag = classify_phase(
        axes, _regime(kind=RegimeKind.BULL), _profile(),
        price_change_h24=-0.15, liquidity_growth=-0.10,
    )
    assert tag.primary == "Decay"
    assert tag.regime_downgrade_applied is True


# -------- Profile phase_overrides --------


def test_profile_phase_overrides_apply():
    prof = AssetProfile(
        kind=AssetKind.MEME,
        label="custom",
        phase_overrides={"late_expansion": {"level_min": 70.0, "level_max": 95.0}},
    )
    # 用 override 后 late_expansion level_min=70；level=85 满足
    # 但 Expansion (30-70) 的 level_max=70，85 已超出 Expansion 范围
    axes = {"attention": _att(level=85, growth=0.05, momentum=-0.02)}
    tag = classify_phase(
        axes, _regime(kind=RegimeKind.RANGE), prof,
        liquidity_growth=0.01,
    )
    assert tag.primary == "Late Expansion"


# -------- 边界 --------


def test_unknown_when_no_rule_matches():
    axes = {"attention": _att(level=45, growth=0.0, hl=None)}
    tag = classify_phase(axes, _regime(), _profile())
    assert tag.primary == "Unknown"
    assert tag.confidence == 0.0


def test_phase_stages_constant_has_8_items():
    assert len(PHASE_STAGES) == 8