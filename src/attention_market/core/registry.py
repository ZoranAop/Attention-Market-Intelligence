# ---------------------------------------------------------------------------
# attention-market · asset profile registry
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""资产画像（AssetProfile）注册表。

每种 AssetKind 对应一个 AssetProfile，描述：
  - 该类型使用的注意力信号源及权重
  - 是否启用合约门控
  - 风险分项权重
  - 风险分项口径（band）
  - 推荐的 Provider 列表
  - 附加说明（进报告）

框架通过 get_profile(kind) 调度，不写死数字。新增资产类型只需
register_profile() 即可，核心代码无需改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .asset import AssetKind

__all__ = [
    "AssetProfile",
    "get_profile",
    "register_profile",
    "list_profiles",
    "BUILTIN_PROFILES",
]


@dataclass
class AssetProfile:
    """一种资产类型的完整画像。"""

    kind: AssetKind
    label: str
    signals: Dict[str, float] = field(default_factory=dict)
    gate_enabled: bool = True
    risk_weights: Dict[str, float] = field(default_factory=dict)
    risk_bands: Dict[str, Dict[str, float]] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.label,
            "signals": dict(self.signals),
            "gate_enabled": self.gate_enabled,
            "risk_weights": dict(self.risk_weights),
            "risk_bands": {k: dict(v) for k, v in self.risk_bands.items()},
            "sources": list(self.sources),
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# 内置画像
# ---------------------------------------------------------------------------

# 这些画像的权重/口径是经验默认值，可在 config 中覆盖。

MEME_PROFILE = AssetProfile(
    kind=AssetKind.MEME,
    label="注意力驱动长尾代币（默认案例）",
    signals={
        "onchain_txns": 0.35,
        "onchain_makers": 0.15,
        "volume": 0.15,
        "wikipedia": 0.15,
        "hackernews": 0.10,
        "reddit": 0.10,
    },
    gate_enabled=True,
    risk_weights={
        "gate": 0.30,
        "liquidity_depth": 0.20,
        "mc_to_liquidity": 0.20,
        "turnover": 0.15,
        "attention_decay": 0.15,
    },
    risk_bands={
        "liquidity_depth_usd": {"very_low": 50_000, "ok": 1_000_000},
        "mc_to_liquidity_ratio": {"dangerous": 10, "caution": 3},
        "turnover_ratio": {"extreme": 3, "normal": 0.5},
    },
    sources=["dexscreener", "goplus", "geckoterminal", "wikipedia", "hackernews"],
    note="MEME 币：注意力几乎完全定价。门控（错币/蜜罐）+ 流动性 + 市值/池 三大支柱。",
)

STABLECOIN_PROFILE = AssetProfile(
    kind=AssetKind.STABLECOIN,
    label="稳定币（名义锚定，注意力权重低）",
    signals={
        # 稳定币的"注意力"是异常事件（脱锚、监管）而非常态讨论
        "volume": 0.50,
        "wikipedia": 0.20,
        "hackernews": 0.15,
        "reddit": 0.15,
    },
    gate_enabled=False,  # 不需要合约门控（稳定币合约已充分审计）
    risk_weights={
        "depeg": 0.50,                # 脱锚价差（核心）
        "issuer_reserve": 0.30,       # 发行方/储备信任
        "liquidity_depth": 0.20,      # 流动性深度
    },
    risk_bands={
        # 脱锚价差（绝对值，1.00 为锚定）
        # extreme: 极端脱锚（6.5%+）→ 风险分 100
        # caution: 关注区间（2%）→ 风险分 0
        # 5% 脱锚 → 约 67 分（高风险）
        "depeg": {"extreme": 0.065, "dangerous": 0.05, "caution": 0.02},
        "liquidity_depth_usd": {"very_low": 1_000_000, "ok": 100_000_000},
    },
    sources=["dexscreener", "geckoterminal", "coingecko"],
    note="稳定币：看脱锚价差，不看市值/池（那是稳定币设计的特性，不是失真）。",
)

L1_PROFILE = AssetProfile(
    kind=AssetKind.L1,
    label="原生 Layer-1 资产",
    signals={
        "onchain_txns": 0.40,        # L1 链上交易是核心
        "volume": 0.30,              # 成交额
        "wikipedia": 0.15,
        "hackernews": 0.10,
        "reddit": 0.05,
    },
    gate_enabled=False,  # L1 没有合约地址（wrapped 形式例外）
    risk_weights={
        "volatility": 0.35,          # 波动率（L1 核心风险）
        "attention_decay": 0.20,     # 注意力衰减
        "liquidity_depth": 0.15,
        "mc_to_liquidity": 0.15,
        "turnover": 0.15,
    },
    risk_bands={
        "volatility": {"extreme": 0.80, "high": 0.50, "normal": 0.25},
        "liquidity_depth_usd": {"very_low": 1_000_000, "ok": 50_000_000},
        "mc_to_liquidity_ratio": {"dangerous": 20, "caution": 5},
    },
    sources=["dexscreener", "geckoterminal", "coingecko", "wikipedia"],
    note="L1：无合约地址，看宏观链上指标（波动率 + 链上交易 + 注意力衰减）。",
)

DEFI_PROFILE = AssetProfile(
    kind=AssetKind.DEFI,
    label="DeFi 协议代币（注意力 + 基本面）",
    signals={
        "onchain_txns": 0.30,
        "volume": 0.20,
        "wikipedia": 0.20,
        "hackernews": 0.15,
        "reddit": 0.15,
    },
    gate_enabled=True,
    risk_weights={
        "gate": 0.20,
        "liquidity_depth": 0.20,
        "mc_to_liquidity": 0.15,
        "turnover": 0.10,
        "attention_decay": 0.15,
        "fundamental": 0.20,          # 协议收入/TVL（占位）
    },
    risk_bands={
        "liquidity_depth_usd": {"very_low": 200_000, "ok": 5_000_000},
        "mc_to_liquidity_ratio": {"dangerous": 8, "caution": 3},
    },
    sources=["dexscreener", "goplus", "geckoterminal", "defillama"],
    note="DeFi：注意力 + 基本面（TVL/收入）混合定价，门控 + 基本面双口径。",
)

SECURITY_PROFILE = AssetProfile(
    kind=AssetKind.SECURITY,
    label="证券类（现金流定价）",
    signals={
        "wikipedia": 0.35,
        "hackernews": 0.20,
        "reddit": 0.15,
        "volume": 0.30,
    },
    gate_enabled=False,  # 链上不是核心信号
    risk_weights={
        "fundamental_valuation": 0.40,  # 现金流折现
        "volatility": 0.30,
        "attention_decay": 0.30,
    },
    risk_bands={},
    sources=["coingecko", "wikipedia", "hackernews"],
    note="证券类：现金流定价为主，基本面估值 + 波动率 + 注意力衰减（占位）。",
)

UNKNOWN_PROFILE = AssetProfile(
    kind=AssetKind.UNKNOWN,
    label="未知资产（最保守处理）",
    signals={},
    gate_enabled=True,  # 保守起见仍走门控
    risk_weights={
        "gate": 0.50,
        "liquidity_depth": 0.30,
        "mc_to_liquidity": 0.20,
    },
    risk_bands={},
    sources=[],
    note="无法判定类型：默认保守画像，所有结论标注「可靠性下降」。",
)


BUILTIN_PROFILES: Dict[AssetKind, AssetProfile] = {
    AssetKind.MEME: MEME_PROFILE,
    AssetKind.STABLECOIN: STABLECOIN_PROFILE,
    AssetKind.L1: L1_PROFILE,
    AssetKind.DEFI: DEFI_PROFILE,
    AssetKind.SECURITY: SECURITY_PROFILE,
    AssetKind.UNKNOWN: UNKNOWN_PROFILE,
}


# ---------------------------------------------------------------------------
# 注册表 API
# ---------------------------------------------------------------------------


_REGISTRY: Dict[AssetKind, AssetProfile] = dict(BUILTIN_PROFILES)


def register_profile(profile: AssetProfile, override: bool = False) -> None:
    """注册/覆盖一个画像。

    ``override=False`` 时若已存在同 kind 画像，抛 ValueError（防止误覆盖）。
    ``override=True`` 时强制覆盖（用于外部插件/扩展）。
    """
    if profile.kind in _REGISTRY and not override:
        raise ValueError(
            f"画像 {profile.kind.value!r} 已注册；如需覆盖请显式传 override=True"
        )
    _REGISTRY[profile.kind] = profile


def get_profile(kind: AssetKind) -> AssetProfile:
    """获取画像。未注册的 kind 永远返回 UNKNOWN_PROFILE（兜底）。"""
    return _REGISTRY.get(kind, UNKNOWN_PROFILE)


def list_profiles() -> Sequence[AssetProfile]:
    """列出所有已注册画像（只读副本）。"""
    return tuple(_REGISTRY.values())


def reset_registry() -> None:
    """重置为内置画像（主要用于测试）。"""
    _REGISTRY.clear()
    _REGISTRY.update(BUILTIN_PROFILES)
