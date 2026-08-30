# ---------------------------------------------------------------------------
# attention-market · 8-stage phase classification (v0.3)
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Phase 8 阶段判定（RFC v0.3 §5）。

8 阶段：
    Stealth → Expansion → Late Expansion → Peak →
    Drawdown → Decay → Recovery → Re-accumulation

输入：AxisReading 字典（4 轴）+ RegimeReading + Profile
输出：PhaseTag

强制降级（RFC §5.4）：
    - regime ∈ {Bear, Crisis} 且 phase == "Late Expansion" → Peak
    - regime == "Bull" 且 phase == "Drawdown" → Decay
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .asset import SignalAxis
from .models import AxisReading, PhaseTag, RegimeKind, RegimeReading
from .registry import AssetProfile

__all__ = [
    "classify_phase",
    "DEFAULT_PHASE_THRESHOLDS",
    "apply_regime_downgrade",
    "PHASE_STAGES",
]


# 8 阶段标签顺序（短路匹配顺序）
# Peak 在 Late Expansion 之前：level 高 + momentum<0 + 有 divergence 时
# 直接判定为 Peak（不先经过 Late Expansion），与 RFC §5.6 语义一致。
PHASE_STAGES: List[str] = [
    "Stealth",
    "Expansion",
    "Peak",
    "Late Expansion",
    "Drawdown",
    "Decay",
    "Recovery",
    "Re-accumulation",
]

# 阶段名 → 阈值 key 的映射（避免 "Late Expansion" 这种带空格名作为 key）
_PHASE_LABEL_TO_KEY: Dict[str, str] = {
    "Stealth": "stealth",
    "Expansion": "expansion",
    "Late Expansion": "late_expansion",
    "Peak": "peak",
    "Drawdown": "drawdown",
    "Decay": "decay",
    "Recovery": "recovery",
    "Re-accumulation": "re_accumulation",
}

# RFC §5.6 默认阈值
DEFAULT_PHASE_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "stealth": {
        "level_max": 30.0,
        "growth_min": 0.0,
    },
    "expansion": {
        "level_min": 30.0,
        "level_max": 70.0,
        "growth_min": 0.0,
        "beta_min": 0.5,
    },
    "late_expansion": {
        "level_min": 60.0,
        "level_max": 90.0,
        "momentum_max": 0.0,
        "liq_lag_required": True,
    },
    "peak": {
        "level_min": 80.0,
        "momentum_max": 0.0,
        "divergence_required": True,
    },
    "drawdown": {
        "level_min": 50.0,
        "level_max": 80.0,
        "growth_max": 0.0,
        "price_min": -0.30,
        "price_max": -0.10,
        "liq_drop_min": -0.20,
        "liq_drop_max": -0.05,
    },
    "decay": {
        "level_max": 50.0,
        "half_life_max_h": 24.0,
    },
    "recovery": {
        "z_min": 0.0,
        "beta_min": 0.0,
    },
    "re_accumulation": {
        "level_min": 40.0,
        "level_max": 65.0,
        "half_life_min_h": 72.0,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(axis_readings: Dict[str, AxisReading], name: str) -> Optional[AxisReading]:
    return axis_readings.get(name)


def _safe_num(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v


def _in_range(value: Optional[float], lo: Optional[float], hi: Optional[float]) -> bool:
    v = _safe_num(value)
    if v is None:
        return False
    if lo is not None and v < lo:
        return False
    if hi is not None and v > hi:
        return False
    return True


def _gte(value: Optional[float], threshold: float) -> bool:
    v = _safe_num(value)
    return v is not None and v >= threshold


def _lte(value: Optional[float], threshold: float) -> bool:
    v = _safe_num(value)
    return v is not None and v <= threshold


def apply_regime_downgrade(phase: str, regime: RegimeKind) -> tuple:
    """RFC §5.4 强制降级。

    返回 (new_phase, downgrade_applied)。
    """
    if phase == "Late Expansion" and regime in (RegimeKind.BEAR, RegimeKind.CRISIS):
        return ("Peak", True)
    if phase == "Drawdown" and regime == RegimeKind.BULL:
        return ("Decay", True)
    return (phase, False)


# ---------------------------------------------------------------------------
# Stage predicates
# ---------------------------------------------------------------------------


def _stage_stealth(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = att.level is not None and att.level < thresholds["level_max"]
    growth_ok = att.growth is not None and att.growth > thresholds["growth_min"]
    if level_ok and growth_ok:
        rule_chain.append(f"attention.level<{thresholds['level_max']}✓")
        rule_chain.append(f"attention.growth>{thresholds['growth_min']}✓")
        return True
    return False


def _stage_expansion(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
    beta: Optional[float],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = _in_range(att.level, thresholds["level_min"], thresholds["level_max"])
    growth_ok = att.growth is not None and att.growth > thresholds["growth_min"]
    # beta_min 是软要求：beta 缺失时仍可触发（标 rule 跳过）
    beta_ok = beta is None or beta >= thresholds["beta_min"]
    if level_ok and growth_ok and beta_ok:
        rule_chain.append(f"attention.level∈[{thresholds['level_min']},{thresholds['level_max']}]✓")
        rule_chain.append(f"attention.growth>{thresholds['growth_min']}✓")
        if beta is not None:
            rule_chain.append(f"β={beta:.2f}≥{thresholds['beta_min']}✓")
        return True
    return False


def _stage_late_expansion(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
    liquidity_growth: Optional[float],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = _in_range(att.level, thresholds["level_min"], thresholds["level_max"])
    momentum_ok = att.momentum is not None and att.momentum <= thresholds["momentum_max"]
    # liq_lag 是软要求：liquidity_growth 缺失时仍可触发
    liq_ok = (
        not thresholds.get("liq_lag_required", False)
        or liquidity_growth is None
        or liquidity_growth < att.growth
    )
    if level_ok and momentum_ok and liq_ok:
        rule_chain.append(f"attention.level∈[{thresholds['level_min']},{thresholds['level_max']}]✓")
        rule_chain.append(f"attention.momentum≤{thresholds['momentum_max']}✓")
        if liquidity_growth is not None and att.growth is not None:
            rule_chain.append(
                f"liquidity_growth({liquidity_growth:.2f})<attention.growth({att.growth:.2f})✓"
            )
        return True
    return False


def _stage_peak(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
    divergences: List[Any],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = att.level is not None and att.level >= thresholds["level_min"]
    momentum_ok = att.momentum is not None and att.momentum <= thresholds["momentum_max"]
    has_div = bool(divergences)
    if level_ok and momentum_ok and has_div:
        rule_chain.append(f"attention.level≥{thresholds['level_min']}✓")
        rule_chain.append(f"attention.momentum≤{thresholds['momentum_max']}✓")
        rule_chain.append(f"divergences({len(divergences)})≥1✓")
        return True
    return False


def _stage_drawdown(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
    price_change: Optional[float],
    liquidity_growth: Optional[float],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = _in_range(att.level, thresholds["level_min"], thresholds["level_max"])
    growth_ok = att.growth is not None and att.growth < thresholds["growth_max"]
    price_ok = _in_range(price_change, thresholds["price_min"], thresholds["price_max"])
    liq_ok = _in_range(liquidity_growth, thresholds["liq_drop_min"], thresholds["liq_drop_max"])
    if level_ok and growth_ok and price_ok and liq_ok:
        rule_chain.append(f"attention.level∈[{thresholds['level_min']},{thresholds['level_max']}]✓")
        rule_chain.append(f"attention.growth<{thresholds['growth_max']}✓")
        if price_change is not None:
            rule_chain.append(f"price∈[{thresholds['price_min']},{thresholds['price_max']}]✓")
        if liquidity_growth is not None:
            rule_chain.append(
                f"liq∈[{thresholds['liq_drop_min']},{thresholds['liq_drop_max']}]✓"
            )
        return True
    return False


def _stage_decay(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = att.level is not None and att.level < thresholds["level_max"]
    hl_ok = (
        att.half_life_h is not None
        and att.half_life_h < thresholds["half_life_max_h"]
    )
    if level_ok and hl_ok:
        rule_chain.append(f"attention.level<{thresholds['level_max']}✓")
        rule_chain.append(f"half_life<{thresholds['half_life_max_h']}h✓")
        return True
    return False


def _stage_recovery(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
    beta: Optional[float],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    z_ok = att.z_score is not None and att.z_score > thresholds["z_min"]
    beta_ok = beta is None or beta >= thresholds["beta_min"]
    if z_ok and beta_ok:
        rule_chain.append(f"attention.z>{thresholds['z_min']}✓")
        if beta is not None:
            rule_chain.append(f"β={beta:.2f}≥{thresholds['beta_min']}✓")
        return True
    return False


def _stage_re_accumulation(
    axes: Dict[str, AxisReading],
    thresholds: Dict[str, Any],
    rule_chain: List[str],
) -> bool:
    att = _read(axes, SignalAxis.ATTENTION.value)
    if not att or att.unavailable:
        return False
    level_ok = _in_range(att.level, thresholds["level_min"], thresholds["level_max"])
    hl_ok = (
        att.half_life_h is not None
        and att.half_life_h > thresholds["half_life_min_h"]
    )
    if level_ok and hl_ok:
        rule_chain.append(f"attention.level∈[{thresholds['level_min']},{thresholds['level_max']}]✓")
        rule_chain.append(f"half_life>{thresholds['half_life_min_h']}h✓")
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def classify_phase(
    axis_readings: Dict[str, AxisReading],
    regime: RegimeReading,
    profile: AssetProfile,
    *,
    price_change_h24: Optional[float] = None,
    liquidity_growth: Optional[float] = None,
    beta: Optional[float] = None,
    divergences: Optional[List[Any]] = None,
    thresholds: Optional[Dict[str, Dict[str, Any]]] = None,
) -> PhaseTag:
    """主入口：返回 PhaseTag。"""
    rule_chain: List[str] = []

    # Profile overrides 合并默认阈值
    final_thresholds: Dict[str, Dict[str, Any]] = {
        stage: dict(DEFAULT_PHASE_THRESHOLDS[_PHASE_LABEL_TO_KEY[stage]]) for stage in PHASE_STAGES
    }
    overrides = getattr(profile, "phase_overrides", {}) or {}
    for stage, override in overrides.items():
        # 支持 "late_expansion" / "Late Expansion" 两种 key 写法
        key = _PHASE_LABEL_TO_KEY.get(stage, stage)
        if key in final_thresholds and isinstance(override, dict):
            # 用规范化 key 写入 final_thresholds
            label = next((l for l, k in _PHASE_LABEL_TO_KEY.items() if k == key), stage)
            final_thresholds[label].update(override)

    # 短路匹配（按 PHASE_STAGES 顺序；Peak 已置于 Late Expansion 之前）
    primary = "Unknown"
    confidence = 0.0
    if _stage_stealth(axis_readings, final_thresholds["Stealth"], rule_chain):
        primary = "Stealth"; confidence = 0.75
    elif _stage_expansion(axis_readings, final_thresholds["Expansion"], rule_chain, beta):
        primary = "Expansion"; confidence = 0.85
    elif _stage_peak(axis_readings, final_thresholds["Peak"], rule_chain, divergences or []):
        primary = "Peak"; confidence = 0.90
    elif _stage_late_expansion(axis_readings, final_thresholds["Late Expansion"], rule_chain, liquidity_growth):
        primary = "Late Expansion"; confidence = 0.85
    elif _stage_drawdown(axis_readings, final_thresholds["Drawdown"], rule_chain,
                          price_change_h24, liquidity_growth):
        primary = "Drawdown"; confidence = 0.85
    elif _stage_decay(axis_readings, final_thresholds["Decay"], rule_chain):
        primary = "Decay"; confidence = 0.75
    elif _stage_recovery(axis_readings, final_thresholds["Recovery"], rule_chain, beta):
        primary = "Recovery"; confidence = 0.75
    elif _stage_re_accumulation(axis_readings, final_thresholds["Re-accumulation"], rule_chain):
        primary = "Re-accumulation"; confidence = 0.75

    # Regime 强制降级
    downgrade_applied = False
    if primary != "Unknown":
        new_primary, downgrade_applied = apply_regime_downgrade(primary, regime.kind)
        if downgrade_applied:
            rule_chain.append(f"regime_downgrade:{primary}→{new_primary}")
            primary = new_primary
            confidence = min(confidence + 0.05, 0.95)

    if not rule_chain:
        rule_chain.append("no_rule_matched")

    return PhaseTag(
        primary=primary,
        confidence=confidence,
        rule_chain=rule_chain,
        regime_downgrade_applied=downgrade_applied,
    )