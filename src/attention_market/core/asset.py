# ---------------------------------------------------------------------------
# attention-market · asset classifier
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""资产类型分类器。

设计动机：
原框架的指标口径被写死成"加密长尾代币（meme）"——门控、风险、注意力
信号源都假设标的是一个 ERC-20/BEP-20 合约。这导致对稳定币、原生 L1
等资产出现系统性失真（USDC 被误判为"中等风险"，USDT 官方合约触发
极端脱锚误报等）。

通用化的核心思路：在主分析链路前加一层"资产类型"抽象，让框架只
提供调度机制，具体指标权重、门控规则、风险口径都交由每种资产类型
的画像（profile）决定。
"""

from __future__ import annotations

import enum
import os
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "AssetKind",
    "AssetSignals",
    "classify_asset",
    "load_whitelist",
    "DEFAULT_WHITELIST",
    # v0.3 re-export
    "SignalAxis",
]


# v0.3: SignalAxis lives in models.py (canonical) but is re-exported here so
# callers can `from .asset import SignalAxis` without an extra import.
from .models import SignalAxis  # noqa: E402


class AssetKind(str, enum.Enum):
    """资产类型枚举。

    MEME 仍保留，但定位从"框架默认场景"降级为"众多案例之一"。
    实际命中频率最高的应该是 STABLECOIN 和 L1（因为市值最大）。
    """

    MEME = "meme"                  # 注意力驱动长尾代币（默认案例）
    STABLECOIN = "stablecoin"      # 名义锚定稳定币
    L1 = "l1"                      # 原生 Layer-1 资产
    DEFI = "defi"                  # DeFi 协议代币
    SECURITY = "security"          # 证券类（基本面定价）
    UNKNOWN = "unknown"            # 无法判定（最保守处理）


# ---------------------------------------------------------------------------
# 信号聚合
# ---------------------------------------------------------------------------


class AssetSignals:
    """判定资产类型所需的原始信号。

    这些信号在 pipeline 早期即可廉价获取，不依赖链上安全/历史 OHLCV。
    """

    __slots__ = (
        "symbol",
        "name",
        "chain",
        "has_contract",
        "market_cap",
        "price_usd",
    )

    def __init__(
        self,
        symbol: Optional[str] = None,
        name: Optional[str] = None,
        chain: Optional[str] = None,
        has_contract: bool = False,
        market_cap: Optional[float] = None,
        price_usd: Optional[float] = None,
    ) -> None:
        self.symbol = (symbol or "").strip().upper() if symbol else ""
        self.name = (name or "") if name else ""
        self.chain = (chain or "").lower() if chain else ""
        self.has_contract = has_contract
        self.market_cap = market_cap
        self.price_usd = price_usd

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "chain": self.chain,
            "has_contract": self.has_contract,
            "market_cap": self.market_cap,
            "price_usd": self.price_usd,
        }


# ---------------------------------------------------------------------------
# 默认白名单
# ---------------------------------------------------------------------------


# 稳定币：符号命中即认定。允许大小写不敏感匹配。
DEFAULT_STABLECOIN_SYMBOLS: frozenset = frozenset(
    {
        "USDT", "USDC", "DAI", "BUSD", "TUSD", "USDP", "GUSD", "FRAX",
        "USDD", "SUSD", "MIM", "UST", "USDN", "FEI", "LUSD", "SDAI",
        "PYUSD", "FDUSD", "USDX", "OUSD", "DOLA", "GHO", "CRVUSD",
    }
)

# 原生 L1：通常没有 ERC-20 合约（"wrapped" 形式例外），通过符号识别
DEFAULT_L1_SYMBOLS: frozenset = frozenset(
    {
        "BTC", "WBTC", "ETH", "WETH", "SOL", "AVAX", "MATIC", "POL",
        "DOT", "ADA", "NEAR", "ATOM", "APT", "SUI", "SEI", "TON",
        "TRX", "BNB", "WBNB", "FTM", "ALGO", "XLM", "XRP", "LTC",
        "BCH", "ETC", "ICP", "HBAR", "FIL", "EOS", "XTZ", "NEO",
    }
)

# 主流 DeFi 协议代币：能进入前十生态、市值较高、有协议收入
DEFAULT_DEFI_SYMBOLS: frozenset = frozenset(
    {
        "UNI", "AAVE", "CRV", "MKR", "SNX", "COMP", "LDO", "RPL",
        "DYDX", "GMX", "GRT", "BAL", "SUSHI", "YFI", "1INCH", "ENS",
        "CVX", "FXS", "STG", "RDNT",
    }
)

# 证券类：传统 RWA 锚定或合规证券代币
DEFAULT_SECURITY_SYMBOLS: frozenset = frozenset(
    {
        # 暂为空，预留扩展
    }
)


DEFAULT_WHITELIST: Dict[str, Sequence[str]] = {
    "stablecoin": sorted(DEFAULT_STABLECOIN_SYMBOLS),
    "l1": sorted(DEFAULT_L1_SYMBOLS),
    "defi": sorted(DEFAULT_DEFI_SYMBOLS),
    "security": sorted(DEFAULT_SECURITY_SYMBOLS),
}


def load_whitelist(config_path: Optional[str] = None) -> Dict[str, Sequence[str]]:
    """从配置文件加载白名单（如 config/assets.whitelist）。

    配置文件为 YAML 格式：
        stablecoin: [USDT, USDC, ...]
        l1: [BTC, ETH, ...]
        defi: [UNI, AAVE, ...]
        security: [...]

    任何失败都返回内置默认白名单（白名单本身是"乐观"判定，
    失败回退到默认是更安全的选择）。
    """
    if not config_path or not os.path.isfile(config_path):
        return DEFAULT_WHITELIST
    try:
        import yaml  # type: ignore

        with open(config_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        result: Dict[str, List[str]] = {}
        for key in ("stablecoin", "l1", "defi", "security"):
            entries = data.get(key) or DEFAULT_WHITELIST.get(key, [])
            result[key] = [str(s).upper() for s in entries]
        return result
    except Exception:  # noqa: BLE001
        return DEFAULT_WHITELIST


# ---------------------------------------------------------------------------
# 分类器
# ---------------------------------------------------------------------------


def classify_asset(
    signals: AssetSignals,
    whitelist: Optional[Dict[str, Sequence[str]]] = None,
) -> AssetKind:
    """根据资产信号判定类型。

    分类规则（按优先级）：
    1. STABLECOIN：符号命中稳定币白名单 —— 即便价格偏离（疑似脱锚）
       也按稳定币处理（让脱锚风险分项去管，不要被分类误判带偏）
    2. L1：符号命中 L1 白名单 → 原生资产，看宏观链上指标
    3. SECURITY：符号命中证券白名单
    4. DEFI：符号命中 DeFi 白名单（有协议收入/TVL）
    5. MEME：有合约地址但未命中以上白名单 → 注意力驱动长尾代币
       （这是默认案例，绝大多数土狗币落在此类）
    6. UNKNOWN：无任何信号 → 最保守处理，标"可靠性下降"
    """
    wl = whitelist or DEFAULT_WHITELIST
    sym = (signals.symbol or "").upper()

    if not sym:
        return AssetKind.UNKNOWN

    # 1. 稳定币优先（即使价格已偏离锚定，仍按稳定币处理）
    if sym in wl.get("stablecoin", ()):
        return AssetKind.STABLECOIN

    # 2. 原生 L1
    if sym in wl.get("l1", ()):
        return AssetKind.L1

    # 3. 证券类
    if sym in wl.get("security", ()):
        return AssetKind.SECURITY

    # 4. 主流 DeFi
    if sym in wl.get("defi", ()):
        return AssetKind.DEFI

    # 5. 有合约地址但未命中白名单 → 注意力定价案例
    if signals.has_contract:
        return AssetKind.MEME

    # 6. 完全无法判定
    return AssetKind.UNKNOWN
