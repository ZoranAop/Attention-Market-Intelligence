# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Core data models for the Attention → Behavior → Market pipeline.

Design note: every numeric field is Optional and every provider may fail.
The framework never fabricates data — a missing signal stays missing and is
surfaced as ``unavailable`` in the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "SeriesPoint",
    "MarketSnapshot",
    "SecurityInfo",
    "AttentionMetrics",
    "HalfLifeResult",
    "ConversionMetrics",
    "QuadrantResult",
    "GateResult",
    "RiskResult",
    "AnalysisResult",
]


@dataclass
class SeriesPoint:
    """A single observation in a time series."""

    t: str  # ISO date or index label
    value: float


# ---------------------------------------------------------------------------
# Market layer
# ---------------------------------------------------------------------------


@dataclass
class MarketSnapshot:
    """Market-side observation (price / liquidity / activity)."""

    chain: Optional[str] = None
    dex: Optional[str] = None
    pair_address: Optional[str] = None
    base_symbol: Optional[str] = None
    base_name: Optional[str] = None
    base_address: Optional[str] = None
    quote_symbol: Optional[str] = None

    price_usd: Optional[float] = None
    liquidity_usd: Optional[float] = None
    market_cap: Optional[float] = None
    fdv: Optional[float] = None

    volume_h24: Optional[float] = None
    txns_h24_buys: Optional[int] = None
    txns_h24_sells: Optional[int] = None
    makers_h24: Optional[int] = None
    price_change_h24: Optional[float] = None
    pair_created_at: Optional[int] = None

    @property
    def txns_h24_total(self) -> Optional[int]:
        if self.txns_h24_buys is None and self.txns_h24_sells is None:
            return None
        return (self.txns_h24_buys or 0) + (self.txns_h24_sells or 0)

    @property
    def mc_to_liquidity(self) -> Optional[float]:
        """账面市值 / 池子真钱。倍数越大，说明估值越依赖边际定价（空气）。"""
        if self.market_cap and self.liquidity_usd:
            return self.market_cap / self.liquidity_usd
        return None

    @property
    def turnover(self) -> Optional[float]:
        """24h 成交量 / 市值。极高换手 = 热钱快进快出，而非沉淀资金。"""
        if self.volume_h24 and self.market_cap:
            return self.volume_h24 / self.market_cap
        return None


@dataclass
class SecurityInfo:
    """On-chain security / contract-level facts (model E gate inputs)."""

    available: bool = False          # False => 非 EVM 链或接口不可用
    is_honeypot: Optional[bool] = None
    is_mintable: Optional[bool] = None
    is_in_dex: Optional[bool] = None
    is_open_source: Optional[bool] = None
    lp_locked: Optional[bool] = None
    lp_owner_controlled: Optional[bool] = None
    holder_count: Optional[int] = None
    top_holder_percent: Optional[float] = None
    buy_tax: Optional[float] = None
    sell_tax: Optional[float] = None
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Analysis outputs
# ---------------------------------------------------------------------------


@dataclass
class AttentionMetrics:
    """① Attention Index + ② Attention Momentum (Level / Growth / Momentum)."""

    level: Optional[float] = None              # 0-100
    growth: Optional[float] = None             # 一阶：相对变化率
    momentum: Optional[float] = None           # 二阶：增速的变化（加速度）
    trend: str = "unknown"                     # accelerating_up / decelerating_up / declining / flat / unknown
    series: List[SeriesPoint] = field(default_factory=list)
    used_sources: List[str] = field(default_factory=list)
    missing_sources: List[str] = field(default_factory=list)
    note: Optional[str] = None

    @property
    def top_warning(self) -> Optional[str]:
        """减速上涨 = 顶部预警：注意力仍在增加，但新进场的人开始变少。"""
        if self.trend == "decelerating_up":
            return "加速度转负：注意力仍在增长但已减速 —— 顶部预警区"
        if self.trend == "declining":
            return "注意力进入衰退期，新增买盘正在枯竭"
        return None


@dataclass
class HalfLifeResult:
    """Attention Half-Life：注意力从峰值衰减到 50% 所需时间。"""

    halflife_hours: Optional[float] = None
    decay_constant: Optional[float] = None     # λ
    peak_index: Optional[int] = None
    peak_value: Optional[float] = None
    r_squared: Optional[float] = None
    status: str = "unavailable"                # ok / not_decaying / insufficient_data / unavailable
    event_class: Optional[str] = None          # breaking_news / celebrity / film / brand / tech_trend


@dataclass
class ConversionMetrics:
    """④ Conversion Index：注意力 → 实际行为的转化弹性 β。"""

    elasticity: Optional[float] = None         # β = Δlog(Action) / Δlog(Attention)
    r_squared: Optional[float] = None
    interpretation: str = "unavailable"
    note: Optional[str] = None


@dataclass
class QuadrantResult:
    """Attention × Market 二维状态矩阵。"""

    attention_state: str = "unknown"           # up / flat / down
    market_state: str = "unknown"              # up / flat / down
    quadrant: str = "Unknown"                  # Expansion / Divergence / Speculation / Decay / Neutral
    label: str = ""
    description: str = ""


@dataclass
class GateResult:
    """E. 链上门控：决定整套注意力模型是否适用于该标的。

    重要：``score=None`` 表示**未验证**（拿不到链上安全数据），
    与「通过」有本质区别 —— 绝不能把"没数据"显示成"100 分通过"。
    """

    score: Optional[int] = None
    failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    applicable: bool = False
    verified: bool = False                # True 仅当真正拿到了链上安全数据
    note: Optional[str] = None

    @property
    def display(self) -> str:
        """给报告用的状态文案。"""
        # 画像 gate_enabled=False 时，note 包含"不适用"，优先显示"不适用"
        if self.note and "不适用" in self.note:
            return "不适用（该资产类型不启用合约门控）"
        if not self.verified and not self.applicable:
            return "未验证（缺少链上安全数据 ≠ 通过）"
        if not self.verified and self.applicable:
            return "不适用（该资产类型不启用合约门控）"
        return "通过" if self.applicable else "未通过 · 模型不适用"


@dataclass
class RiskResult:
    """Risk：综合风险评分（0-100，越高越危险）。"""

    score: int = 0
    level: str = "未知"
    components: Dict[str, float] = field(default_factory=dict)
    drivers: List[str] = field(default_factory=list)
    # 通用化（v0.2）：标记风险评估所用的资产画像，便于报告展示
    asset_kind: Optional[str] = None
    profile_label: Optional[str] = None


@dataclass
class AnalysisResult:
    """Full pipeline output for one subject."""

    query: str
    subject: str
    market: MarketSnapshot = field(default_factory=MarketSnapshot)
    security: SecurityInfo = field(default_factory=SecurityInfo)
    attention: AttentionMetrics = field(default_factory=AttentionMetrics)
    halflife: HalfLifeResult = field(default_factory=HalfLifeResult)
    conversion: ConversionMetrics = field(default_factory=ConversionMetrics)
    quadrant: QuadrantResult = field(default_factory=QuadrantResult)
    gate: GateResult = field(default_factory=GateResult)
    risk: RiskResult = field(default_factory=RiskResult)
    sources: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    generated_at: Optional[str] = None
    # 同名候选标的（重名混淆是此类分析最常见的陷阱）
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    # 通用化（v0.2）：资产类型与画像标签
    asset_kind: Optional[str] = None
    profile_label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (used by the JSON reporter)."""
        return {
            "query": self.query,
            "subject": self.subject,
            "generated_at": self.generated_at,
            "market": {
                "chain": self.market.chain,
                "dex": self.market.dex,
                "pair_address": self.market.pair_address,
                "base_symbol": self.market.base_symbol,
                "base_name": self.market.base_name,
                "base_address": self.market.base_address,
                "price_usd": self.market.price_usd,
                "liquidity_usd": self.market.liquidity_usd,
                "market_cap": self.market.market_cap,
                "fdv": self.market.fdv,
                "volume_h24": self.market.volume_h24,
                "txns_h24_buys": self.market.txns_h24_buys,
                "txns_h24_sells": self.market.txns_h24_sells,
                "makers_h24": self.market.makers_h24,
                "price_change_h24": self.market.price_change_h24,
                "mc_to_liquidity": self.market.mc_to_liquidity,
                "turnover": self.market.turnover,
            },
            "security": {
                "available": self.security.available,
                "is_honeypot": self.security.is_honeypot,
                "is_mintable": self.security.is_mintable,
                "is_in_dex": self.security.is_in_dex,
                "is_open_source": self.security.is_open_source,
                "lp_locked": self.security.lp_locked,
                "lp_owner_controlled": self.security.lp_owner_controlled,
                "holder_count": self.security.holder_count,
                "top_holder_percent": self.security.top_holder_percent,
                "token_name": self.security.token_name,
                "token_symbol": self.security.token_symbol,
            },
            "attention": {
                "level": self.attention.level,
                "growth": self.attention.growth,
                "momentum": self.attention.momentum,
                "trend": self.attention.trend,
                "used_sources": self.attention.used_sources,
                "missing_sources": self.attention.missing_sources,
                "note": self.attention.note,
                "series": [{"t": p.t, "value": p.value} for p in self.attention.series],
            },
            "halflife": {
                "halflife_hours": self.halflife.halflife_hours,
                "decay_constant": self.halflife.decay_constant,
                "r_squared": self.halflife.r_squared,
                "status": self.halflife.status,
                "event_class": self.halflife.event_class,
            },
            "conversion": {
                "elasticity": self.conversion.elasticity,
                "r_squared": self.conversion.r_squared,
                "interpretation": self.conversion.interpretation,
            },
            "quadrant": {
                "attention_state": self.quadrant.attention_state,
                "market_state": self.quadrant.market_state,
                "quadrant": self.quadrant.quadrant,
                "label": self.quadrant.label,
                "description": self.quadrant.description,
            },
            "gate": {
                "score": self.gate.score,
                "failed": self.gate.failed,
                "warnings": self.gate.warnings,
                "applicable": self.gate.applicable,
                "note": self.gate.note,
            },
            "risk": {
                "score": self.risk.score,
                "level": self.risk.level,
                "components": self.risk.components,
                "drivers": self.risk.drivers,
                "asset_kind": self.risk.asset_kind,
                "profile_label": self.risk.profile_label,
            },
            "sources": self.sources,
            "notes": self.notes,
            "candidates": self.candidates,
            "asset_kind": self.asset_kind,
            "profile_label": self.profile_label,
        }
