# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""E. 链上门控模型（前置过滤）。

注意力定价模型只对**真币**成立。在错币、假币、诱饵合约上做注意力量化，
等于给空气定价 —— 这是本项目最重要的一条经验：

    某 BSC「买入教程」给出的 0x49b79e9250797025f72f44d7286e267bc2a4b9ed，
    经 GoPlus 实测为 PancakeSwap 的 Cake-LP 池子份额代币
    （token_name="Pancake LPs" / 持有人 5 / is_in_dex=0 / is_mintable=1），
    与它所声称的 meme 币毫无关系。

门控不通过 ⇒ 后续 A/B/C/D 全部模型不适用。
"""

from __future__ import annotations

from typing import List

from .models import GateResult, MarketSnapshot, SecurityInfo

__all__ = ["evaluate_gate"]

DEFAULT_PENALTIES = {
    "not_in_dex": 40,                # 不在 DEX 交易（错币/诱饵的典型特征）
    "is_honeypot": 50,               # 蜜罐：能买不能卖
    "mintable": 25,                  # 可无限增发
    "lp_not_locked": 20,             # LP 未锁定
    "lp_owner_controlled": 25,       # LP 在项目方钱包（可随时 rug）
    "high_holder_concentration": 15, # 持有人高度集中
    "contract_unverified": 10,       # 合约未开源
    "extreme_tax": 15,               # 买卖税过高
}

FAIL_LABELS = {
    "not_in_dex": "未在 DEX 交易（疑为错币/诱饵合约）",
    "is_honeypot": "蜜罐风险：可能能买不能卖",
    "mintable": "合约可无限增发（mint 权限未放弃）",
    "lp_not_locked": "LP 未锁定",
    "lp_owner_controlled": "LP 由项目方地址控制（可随时抽池）",
    "high_holder_concentration": "持有人高度集中（前十大占比过高）",
    "contract_unverified": "合约未开源/未验证",
    "extreme_tax": "买卖税率过高",
}


def evaluate_gate(
    security: SecurityInfo,
    market: MarketSnapshot,
    penalties: dict | None = None,
    concentration_threshold: float = 0.30,
    fail_score: int = 50,
    tax_threshold: float = 0.10,
) -> GateResult:
    """从 100 分开始扣分，低于 fail_score 判定「模型不适用」。"""
    penalties = {**DEFAULT_PENALTIES, **(penalties or {})}
    score = 100
    failed: List[str] = []
    warnings: List[str] = []

    def ding(key: str) -> None:
        nonlocal score
        score -= int(penalties.get(key, 0))
        failed.append(FAIL_LABELS.get(key, key))

    if not security.available:
        # 关键：拿不到安全数据 ≠ 通过。必须显式标记为「未验证」，
        # 否则会给出一个虚假的安全感（这正是错币得以流通的原因之一）。
        # 具体原因由 pipeline 补充（not_found / unsupported_chain / http_error …），
        # 这里只留一句通用的兜底提示。
        warnings.append("链上安全数据不可用 —— 门控未验证，不等于通过，请在区块浏览器人工复核合约真伪")
        if market.liquidity_usd is None or market.liquidity_usd <= 0:
            warnings.append("无法获取流动性数据，无法确认池子真实性")
        return GateResult(
            score=None,
            failed=failed,
            warnings=warnings,
            applicable=True,     # 不阻断分析，但结论可靠性下降
            verified=False,
            note="门控未验证：缺少链上安全数据，市场侧结论仅供参考",
        )

    # 硬性否决项：无论总分多少，只要命中就直接判定「模型不适用」
    hard_fail = False
    if security.is_in_dex is False:
        ding("not_in_dex")
        hard_fail = True
    if security.is_honeypot is True:
        ding("is_honeypot")
        hard_fail = True
    if security.is_mintable is True:
        ding("mintable")
    if security.is_open_source is False:
        ding("contract_unverified")
    if security.lp_locked is False:
        ding("lp_not_locked")
    if security.lp_owner_controlled is True:
        ding("lp_owner_controlled")
    if security.top_holder_percent is not None and security.top_holder_percent > concentration_threshold:
        ding("high_holder_concentration")
    for tax in (security.buy_tax, security.sell_tax):
        if tax is not None and tax > tax_threshold:
            ding("extreme_tax")
            break

    if security.is_honeypot is None:
        warnings.append("蜜罐检测不可用")
    if security.lp_locked is None:
        warnings.append("LP 锁仓状态未能核实（应人工在区块浏览器确认）")

    score = max(0, min(100, score))
    applicable = (not hard_fail) and score >= fail_score
    note = None
    if hard_fail:
        note = "命中硬性否决项（错币/蜜罐）—— 注意力模型不适用于该标的"
    elif not applicable:
        note = "门控未通过：注意力模型不适用于该标的"
    return GateResult(
        score=score,
        failed=failed,
        warnings=warnings,
        applicable=applicable,
        verified=True,
        note=note,
    )
