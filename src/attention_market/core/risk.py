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

通用化改造（v0.2）：
  - 风险分项权重 = 默认 + config 覆盖 + 画像覆盖（画像优先级最高）
  - 稳定币新增分项：脱锚价差（核心）+ 发行方/储备信任
  - L1 新增分项：波动率
  - 证券类新增分项：基本面估值（占位）
  - 脱锚可信度防御：极端脱锚(>20%)且池子/成交极小时，标记为
    "疑似错误池价格，请复核"，不误判极高风险
"""

from __future__ import annotations

from typing import Optional

from .asset import AssetKind
from .models import AttentionMetrics, GateResult, MarketSnapshot, QuadrantResult, RiskResult
from .registry import AssetProfile, get_profile

__all__ = ["score_risk", "RISK_LEVELS"]

RISK_LEVELS = [(75, "极高"), (55, "高"), (30, "中"), (0, "低")]

DEFAULT_WEIGHTS = {
    "gate": 0.30,
    "liquidity_depth": 0.20,
    "mc_to_liquidity": 0.20,
    "turnover": 0.15,
    "attention_decay": 0.15,
}

# 稳定币锚定价格（按符号索引）。绝大多数主流稳定币锚定 1.00。
STABLECOIN_PEG_USD: float = 1.0

# 脱锚防御阈值：脱锚幅度超过此值且池子/成交极小，视为数据错误
DEPEG_DEFENSE_THRESHOLD: float = 0.20
DEPEG_DEFENSE_MIN_LIQUIDITY_USD: float = 10_000.0
DEPEG_DEFENSE_MIN_VOLUME_USD: float = 1_000.0


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


def _compute_depeg(
    market: MarketSnapshot,
    bands: dict,
) -> tuple[Optional[float], bool, Optional[str]]:
    """计算脱锚价差风险分。

    返回 (score, suspect, suspect_note)：
      - score: 脱锚分项 0-100
      - suspect: True 表示触发了"疑似错误池价格"防御
      - suspect_note: 防御说明
    """
    if market.price_usd is None:
        return None, False, None

    depeg = abs(market.price_usd - STABLECOIN_PEG_USD)
    extreme = float(bands.get("extreme", 0.20))
    dangerous = float(bands.get("dangerous", 0.05))
    caution = float(bands.get("caution", 0.01))

    # 脱锚防御：极端脱锚 + 池子/成交极小 = 疑似数据错误
    liq = market.liquidity_usd or 0.0
    vol = market.volume_h24 or 0.0
    suspect = (
        depeg > DEPEG_DEFENSE_THRESHOLD
        and liq < DEPEG_DEFENSE_MIN_LIQUIDITY_USD
        and vol < DEPEG_DEFENSE_MIN_VOLUME_USD
    )
    if suspect:
        return None, True, (
            f"疑似数据源错误池价格：脱锚 {depeg:.1%} 但池子仅 ${liq:,.0f}、"
            f"24h 成交 ${vol:,.0f} —— 请人工复核，未参与风险评分"
        )

    score = _scale_band(depeg, extreme, caution)
    return score, False, None


def score_risk(
    market: MarketSnapshot,
    gate: GateResult,
    attention: AttentionMetrics,
    quadrant: QuadrantResult,
    cfg: dict,
    asset_kind: Optional[AssetKind] = None,
    profile: Optional[AssetProfile] = None,
    depeg_status: Optional[str] = None,
    issuer_reserve_status: Optional[str] = None,
) -> RiskResult:
    """综合风险评分（0-100，越高越危险）。

    通用化（v0.2）：
      - 优先使用画像的 risk_weights / risk_bands（profile > cfg > 默认）
      - 稳定币走专属分项（脱锚 + 发行方 + 流动性），关闭市值/池/换手等失真指标
      - L1 走专属分项（波动率 + 注意力 + 流动性），不强制看市值/池
    """
    r_cfg = (cfg or {}).get("risk", {})

    # 解析画像（profile > asset_kind > 默认）
    if profile is None and asset_kind is not None:
        profile = get_profile(asset_kind)
    elif profile is None:
        profile = None

    # 权重：默认 < config < 画像
    if profile is not None and profile.risk_weights:
        weights = dict(profile.risk_weights)
    else:
        weights = {**DEFAULT_WEIGHTS, **(r_cfg.get("weights") or {})}

    # 分项口径：默认 < config < 画像
    if profile is not None and profile.risk_bands:
        bands = {k: dict(v) for k, v in profile.risk_bands.items()}
    else:
        bands = {}
    cfg_bands = {
        "liquidity_depth_usd": r_cfg.get("liquidity_depth_usd", {}) or {},
        "mc_to_liquidity_ratio": r_cfg.get("mc_to_liquidity_ratio", {}) or {},
        "turnover_ratio": r_cfg.get("turnover_ratio", {}) or {},
    }
    for k, v in cfg_bands.items():
        if v and (k not in bands or not bands[k]):
            bands[k] = v

    components: dict[str, float] = {}
    drivers: list[str] = []

    # ============================================================
    # 通用化分派：按画像决定使用哪些分项
    # ============================================================
    is_stablecoin = profile is not None and profile.kind == AssetKind.STABLECOIN
    is_security = profile is not None and profile.kind == AssetKind.SECURITY
    is_l1 = profile is not None and profile.kind == AssetKind.L1

    # 1) 门控（所有启用门控的类型；稳定币/L1/证券通常 gate_enabled=False）
    if profile is None or profile.gate_enabled:
        if gate.score is None:
            components["gate"] = 50.0
            drivers.append("链上门控未验证（缺少链上安全数据，非通过）")
        else:
            components["gate"] = float(100 - gate.score)
        if not gate.applicable:
            drivers.append("链上门控未通过（模型适用性受限）")
        for f in gate.failed[:3]:
            drivers.append(f)

    # 2) 流动性深度（通用：越小越危险）
    liq_bands = bands.get("liquidity_depth_usd", {})
    if "liquidity_depth" in weights and market.liquidity_usd is not None:
        very_low = float(liq_bands.get("very_low", 50_000))
        ok = float(liq_bands.get("ok", 1_000_000))
        components["liquidity_depth"] = _scale_band(market.liquidity_usd, very_low, ok)
        if market.liquidity_usd <= very_low:
            drivers.append(f"池子真钱仅 ${market.liquidity_usd:,.0f}（极易被抽空）")

    # 3) 市值 / 真实资金（仅对长尾/非稳定币资产启用 —— 稳定币这值本身就该很大）
    if not is_stablecoin and "mc_to_liquidity" in weights:
        ratio = market.mc_to_liquidity
        if ratio is not None:
            mc_b = bands.get("mc_to_liquidity_ratio", {})
            dangerous = float(mc_b.get("dangerous", 10))
            caution = float(mc_b.get("caution", 3))
            components["mc_to_liquidity"] = _scale_band(ratio, dangerous, caution)
            if ratio >= dangerous:
                drivers.append(f"市值/真实资金 = {ratio:.1f}×（账面估值高度虚拟化）")

    # 4) 换手率（稳定币换手率天然高，不应作为风险信号）
    if not is_stablecoin and "turnover" in weights:
        turnover = market.turnover
        if turnover is not None:
            to_b = bands.get("turnover_ratio", {})
            extreme = float(to_b.get("extreme", 3))
            components["turnover"] = _scale_band(turnover, extreme, 0.5)
            if turnover >= extreme:
                drivers.append(f"换手率 {turnover:.1f}×（快进快出的热钱博弈，非沉淀资金）")

    # 5) 注意力衰减状态（通用）
    if "attention_decay" in weights:
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

    # ============================================================
    # 通用化新增分项
    # ============================================================

    # 6) 脱锚价差（仅稳定币）
    depeg_suspect = False  # 记录防御状态，用于在 drivers 末尾输出
    if is_stablecoin and "depeg" in weights:
        depeg_bands = bands.get("depeg", {"extreme": 0.20, "dangerous": 0.05, "caution": 0.01})
        depeg_score, suspect, suspect_note = _compute_depeg(market, depeg_bands)
        if suspect:
            depeg_suspect = True
            drivers.append(suspect_note or "脱锚疑似数据错误")
            # 防御触发：把流动性也置为"待复核"中间值，避免被极端池子污染
            if "liquidity_depth" in components:
                components["liquidity_depth"] = 50.0
        elif depeg_score is not None:
            components["depeg"] = depeg_score
            if depeg_score >= 75:
                drivers.append(f"脱锚价差风险分 {depeg_score:.0f}/100（极端脱锚）")
            elif depeg_score >= 50:
                drivers.append(f"脱锚价差风险分 {depeg_score:.0f}/100（高度警惕）")

    # 7) 发行方/储备信任（仅稳定币，pipeline 传入字符串状态）
    if is_stablecoin and "issuer_reserve" in weights:
        s = (issuer_reserve_status or "unknown").lower()
        if s == "verified":
            components["issuer_reserve"] = 20.0
        elif s == "partial":
            components["issuer_reserve"] = 50.0
            drivers.append("发行方/储备链上核验未完成（部分确认）")
        elif s == "unverified":
            components["issuer_reserve"] = 80.0
            drivers.append("发行方/储备未核验（无法确认兑付能力）")
        else:
            components["issuer_reserve"] = 60.0
            drivers.append("发行方/储备核验状态未知")

    # 8) 波动率（L1 / 证券）
    if (is_l1 or is_security) and "volatility" in weights:
        # 从价格 24h 变化粗略估计波动率（更精确的实现需要历史 OHLCV）
        vol_b = bands.get("volatility", {"extreme": 0.80, "high": 0.50, "normal": 0.25})
        extreme = float(vol_b.get("extreme", 0.80))
        high = float(vol_b.get("high", 0.50))
        normal = float(vol_b.get("normal", 0.25))
        if market.price_change_h24 is not None:
            # 24h 变化作为短期波动率代理
            change = abs(market.price_change_h24 / 100.0)
            components["volatility"] = _scale_band(change, extreme, normal)
            if change >= extreme:
                drivers.append(f"24h 波动 {change:.1%}（极端波动）")

    # 9) 基本面估值（DeFi / 证券，占位）
    if "fundamental" in weights:
        # 真实实现需要接入 DeFiLlama/TokenTerminal 等基本面数据源
        # 此处用占位：未接入时记中间分，并提示
        components["fundamental"] = 50.0
        drivers.append("基本面分项：占位（需接入 DeFiLlama/TokenTerminal 等数据源）")

    # 象限提示
    if quadrant.quadrant == "Speculation":
        drivers.append("价格脱离注意力基础（Speculation 象限）")
    elif quadrant.quadrant == "Divergence":
        drivers.append("注意力与市场背离（Divergence 象限）")

    # 脱锚状态外层标注
    if depeg_suspect or depeg_status == "suspect":
        drivers.append("[!] 脱锚防御已触发：当前风险分不计入脱锚分项，请人工复核池子价格")

    # 加权（仅使用实际存在的分项，权重重归一化）
    if not components:
        # 没有任何分项时返回最低风险
        return RiskResult(score=0, level="低", components={}, drivers=["无可用风险分项（数据缺失）"])

    total_w = sum(weights.get(k, 0.0) for k in components) or 1.0
    total = sum(weights.get(k, 0.0) * v for k, v in components.items()) / total_w
    total = max(0.0, min(100.0, total))

    if not drivers:
        drivers.append("未发现显著风险驱动项（仍需注意数据完整性）")

    return RiskResult(
        score=int(round(total)),
        level=_level(total),
        components=components,
        drivers=drivers,
    )
