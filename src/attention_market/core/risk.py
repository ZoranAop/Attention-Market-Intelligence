# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Risk：把门控、流动性、估值虚高、换手与注意力衰减合成为一个风险分。

核心逻辑（对加密标的）：

    池子里真实在场的钱，就是庄家随时能卷走的钱，
    也是你一旦进场就再也拿不回来的钱。

因此「市值 / 真实流动性」倍数是最能说明"空气占比"的单一指标：
账面市值 = 最后成交价 × 总供应量，而真实资金只有池子里那点 U。
"""

from __future__ import annotations

from typing import Optional

from .models import AttentionMetrics, GateResult, MarketSnapshot, QuadrantResult, RiskResult

__all__ = ["score_risk", "RISK_LEVELS"]

RISK_LEVELS = [(75, "极高"), (55, "高"), (30, "中"), (0, "低")]

DEFAULT_WEIGHTS = {
    "gate": 0.30,
    "liquidity_depth": 0.20,
    "mc_to_liquidity": 0.20,
    "turnover": 0.15,
    "attention_decay": 0.15,
}


def _level(score: float) -> str:
    for threshold, name in RISK_LEVELS:
        if score >= threshold:
            return name
    return "低"


def _scale_band(value: float, worse: float, better: float) -> float:
    """把指标映射到 0-100 风险分：worse 端=100，better 端=0（线性，log 可选）。"""
    if better == worse:
        return 0.0
    if worse < better:  # 越小越危险（如流动性深度）
        if value <= worse:
            return 100.0
        if value >= better:
            return 0.0
        return (better - value) / (better - worse) * 100.0
    else:  # 越大越危险（如倍数）
        if value >= worse:
            return 100.0
        if value <= better:
            return 0.0
        return (value - better) / (worse - better) * 100.0


def score_risk(
    market: MarketSnapshot,
    gate: GateResult,
    attention: AttentionMetrics,
    quadrant: QuadrantResult,
    cfg: dict,
) -> RiskResult:
    """综合风险评分（0-100，越高越危险）。"""
    r_cfg = (cfg or {}).get("risk", {})
    weights = {**DEFAULT_WEIGHTS, **(r_cfg.get("weights") or {})}
    liq_bands = r_cfg.get("liquidity_depth_usd", {}) or {}
    mc_bands = r_cfg.get("mc_to_liquidity_ratio", {}) or {}
    to_bands = r_cfg.get("turnover_ratio", {}) or {}

    components: dict[str, float] = {}
    drivers: list[str] = []

    # 1) 门控（未验证时取中间值 50 —— 既不奖励也不惩罚"没有数据"）
    if gate.score is None:
        components["gate"] = 50.0
        drivers.append("链上门控未验证（缺少链上安全数据，非通过）")
    else:
        components["gate"] = float(100 - gate.score)
    if not gate.applicable:
        drivers.append("链上门控未通过（模型适用性受限）")
    for f in gate.failed[:3]:
        drivers.append(f)

    # 2) 流动性深度（越小越危险）
    if market.liquidity_usd is not None:
        very_low = float(liq_bands.get("very_low", 50_000))
        ok = float(liq_bands.get("ok", 1_000_000))
        components["liquidity_depth"] = _scale_band(market.liquidity_usd, very_low, ok)
        if market.liquidity_usd <= very_low:
            drivers.append(f"池子真钱仅 ${market.liquidity_usd:,.0f}（极易被抽空）")

    # 3) 市值 / 真实资金（越大越虚）
    ratio = market.mc_to_liquidity
    if ratio is not None:
        dangerous = float(mc_bands.get("dangerous", 10))
        caution = float(mc_bands.get("caution", 3))
        components["mc_to_liquidity"] = _scale_band(ratio, dangerous, caution)
        if ratio >= dangerous:
            drivers.append(f"市值/真实资金 = {ratio:.1f}×（账面估值高度虚拟化）")

    # 4) 换手率（越大越像热钱博弈）
    turnover = market.turnover
    if turnover is not None:
        extreme = float(to_bands.get("extreme", 3))
        components["turnover"] = _scale_band(turnover, extreme, 0.5)
        if turnover >= extreme:
            drivers.append(f"换手率 {turnover:.1f}×（快进快出的热钱博弈，非沉淀资金）")

    # 5) 注意力衰减状态
    att_score = 30.0
    if attention.trend == "declining":
        att_score = 90.0
        drivers.append("注意力已进入衰退期（新增买盘枯竭）")
    elif attention.trend == "decelerating_up":
        att_score = 70.0
        drivers.append("注意力增速放缓（加速度转负：顶部预警区）")
    elif attention.trend == "accelerating_up":
        att_score = 25.0
    elif attention.trend == "flat":
        att_score = 50.0
    components["attention_decay"] = att_score

    if quadrant.quadrant == "Speculation":
        drivers.append("价格脱离注意力基础（Speculation 象限）")
    elif quadrant.quadrant == "Divergence":
        drivers.append("注意力与市场背离（Divergence 象限）")

    # 加权（仅使用实际存在的分项，权重重归一化）
    total_w = sum(weights.get(k, 0.0) for k in components) or 1.0
    total = sum(weights.get(k, 0.0) * v for k, v in components.items()) / total_w
    total = max(0.0, min(100.0, total))

    if not drivers:
        drivers.append("未发现显著风险驱动项（仍需注意数据完整性）")

    return RiskResult(score=int(round(total)), level=_level(total), components=components, drivers=drivers)
