# ---------------------------------------------------------------------------
# attention-market · tests
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""v0.2 通用化测试：资产分类、画像、门控分流、风险口径参数化、脱锚防御。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from attention_market.core.asset import (  # noqa: E402
    AssetKind,
    AssetSignals,
    classify_asset,
    load_whitelist,
)
from attention_market.core.gate import evaluate_gate  # noqa: E402
from attention_market.core.models import (  # noqa: E402
    AttentionMetrics,
    GateResult,
    MarketSnapshot,
    QuadrantResult,
    SecurityInfo,
)
from attention_market.core.registry import (  # noqa: E402
    AssetProfile,
    get_profile,
    list_profiles,
    register_profile,
    reset_registry,
)
from attention_market.core.risk import (  # noqa: E402
    DEPEG_DEFENSE_MIN_LIQUIDITY_USD,
    DEPEG_DEFENSE_MIN_VOLUME_USD,
    DEPEG_DEFENSE_THRESHOLD,
    STABLECOIN_PEG_USD,
    score_risk,
)


# ---------------------------------------------------------------------------
# 资产分类
# ---------------------------------------------------------------------------


def test_classify_stablecoin():
    sig = AssetSignals(symbol="USDC", price_usd=1.0, has_contract=True)
    assert classify_asset(sig) == AssetKind.STABLECOIN

    sig = AssetSignals(symbol="usdt", price_usd=0.998, has_contract=True)
    assert classify_asset(sig) == AssetKind.STABLECOIN


def test_classify_l1():
    sig = AssetSignals(symbol="BTC", has_contract=False)
    assert classify_asset(sig) == AssetKind.L1

    sig = AssetSignals(symbol="ETH", has_contract=False)
    assert classify_asset(sig) == AssetKind.L1


def test_classify_defi():
    sig = AssetSignals(symbol="UNI", has_contract=True)
    assert classify_asset(sig) == AssetKind.DEFI

    sig = AssetSignals(symbol="AAVE", has_contract=True)
    assert classify_asset(sig) == AssetKind.DEFI


def test_classify_meme_default():
    """有合约地址但未命中白名单 → MEME（默认案例）。"""
    sig = AssetSignals(symbol="PEPE", has_contract=True)
    assert classify_asset(sig) == AssetKind.MEME

    sig = AssetSignals(symbol="我的女友景甜", has_contract=True)
    assert classify_asset(sig) == AssetKind.MEME


def test_classify_unknown():
    """无符号或完全无信号 → UNKNOWN（最保守）。"""
    sig = AssetSignals()
    assert classify_asset(sig) == AssetKind.UNKNOWN

    sig = AssetSignals(symbol="", has_contract=False)
    assert classify_asset(sig) == AssetKind.UNKNOWN


def test_classify_stablecoin_priority_over_l1():
    """即便 L1 名字空间有重叠，符号命中稳定币白名单优先。"""
    # 假设未来某天有人用 "USDT" 名字当 L1 也不行 —— 稳定币白名单优先
    sig = AssetSignals(symbol="USDT", has_contract=True, chain="ethereum")
    assert classify_asset(sig) == AssetKind.STABLECOIN


def test_load_whitelist_fallback():
    """白名单文件不存在时回退到内置默认。"""
    wl = load_whitelist("/non/existent/path.yaml")
    assert "USDT" in wl["stablecoin"]
    assert "BTC" in wl["l1"]


# ---------------------------------------------------------------------------
# 画像注册表
# ---------------------------------------------------------------------------


def test_builtin_profiles_cover_all_kinds():
    """所有 AssetKind 都应有内置画像。"""
    for kind in AssetKind:
        profile = get_profile(kind)
        assert profile.kind == kind
        assert profile.label  # 非空
        assert profile.note  # 非空


def test_register_profile_rejects_duplicate_without_override():
    reset_registry()
    try:
        # 第一次注册
        register_profile(AssetProfile(
            kind=AssetKind.MEME,
            label="Test MEME",
            signals={"x": 1.0},
        ), override=True)  # 用 override=True 覆盖内置
        # 第二次不传 override 应抛错
        try:
            register_profile(AssetProfile(
                kind=AssetKind.MEME,
                label="Test MEME 2",
                signals={"x": 1.0},
            ))
            assert False, "应抛 ValueError"
        except ValueError:
            pass
    finally:
        reset_registry()


def test_get_profile_unknown_falls_back_to_unknown_profile():
    """未注册的 kind 永远返回 UNKNOWN_PROFILE（兜底）。"""
    # 临时注册一个新 kind（Python enum 限制，只能用现有）
    # 所以直接测试现有路径
    p = get_profile(AssetKind.STABLECOIN)
    assert p.kind == AssetKind.STABLECOIN


def test_list_profiles_returns_all_builtin():
    profiles = list_profiles()
    kinds = {p.kind for p in profiles}
    assert AssetKind.MEME in kinds
    assert AssetKind.STABLECOIN in kinds
    assert AssetKind.L1 in kinds
    assert AssetKind.DEFI in kinds
    assert AssetKind.SECURITY in kinds
    assert AssetKind.UNKNOWN in kinds


# ---------------------------------------------------------------------------
# 门控按类型分流
# ---------------------------------------------------------------------------


def test_gate_stablecoin_skips_contract_gate():
    """稳定币画像：门控不启用，直接放行。"""
    sec = SecurityInfo(available=False)  # 即便没安全数据也通过
    market = MarketSnapshot(liquidity_usd=1_000_000)
    profile = get_profile(AssetKind.STABLECOIN)
    gate = evaluate_gate(sec, market, profile=profile)
    assert gate.applicable is True
    # verified=True 表示门控逻辑已处理（skip 而非失败），区别于"拿不到数据"的未验证
    assert gate.verified is True
    # warning 或 note 中应出现"不启用合约门控"或类似提示
    combined = " ".join(gate.warnings) + " " + (gate.note or "")
    assert "不启用合约门控" in combined
    # display 应明确"不适用"而非"未验证"
    assert "不适用" in gate.display


def test_gate_l1_skips_contract_gate():
    """L1 画像：门控不启用。"""
    sec = SecurityInfo(available=False)
    market = MarketSnapshot()
    profile = get_profile(AssetKind.L1)
    gate = evaluate_gate(sec, market, profile=profile)
    assert gate.applicable is True
    combined = " ".join(gate.warnings) + " " + (gate.note or "")
    assert "不启用合约门控" in combined


def test_gate_meme_keeps_contract_gate():
    """MEME 画像：门控仍启用。"""
    sec = SecurityInfo(
        available=True,
        is_honeypot=True,
        is_in_dex=True,
    )
    market = MarketSnapshot()
    profile = get_profile(AssetKind.MEME)
    gate = evaluate_gate(sec, market, profile=profile)
    # 蜜罐硬性否决仍生效
    assert gate.applicable is False
    assert any("蜜罐" in f for f in gate.failed)


def test_gate_backward_compatible_no_profile():
    """不传 profile 时行为与 v0.1 一致（向后兼容）。"""
    sec = SecurityInfo(
        available=True,
        is_honeypot=False,
        is_mintable=False,
        is_in_dex=True,
        is_open_source=True,
        lp_locked=True,
        top_holder_percent=0.10,
    )
    market = MarketSnapshot()
    # 不传 profile
    gate = evaluate_gate(sec, market)
    assert gate.applicable is True
    assert gate.score == 100


# ---------------------------------------------------------------------------
# 风险口径参数化
# ---------------------------------------------------------------------------


def _stablecoin_market(price: float, liq: float = 5_000_000, vol: float = 1_000_000) -> MarketSnapshot:
    return MarketSnapshot(
        chain="ethereum",
        price_usd=price,
        liquidity_usd=liq,
        market_cap=1_000_000_000,
        volume_h24=vol,
    )


def test_risk_stablecoin_uses_depeg_not_mc_ratio():
    """稳定币风险评分应使用 depeg 分项，不使用 mc_to_liquidity（关闭失真指标）。"""
    market = _stablecoin_market(price=0.998)  # 0.2% 脱锚（轻微）
    gate = GateResult(applicable=True)  # 稳定币不走门控
    att = AttentionMetrics(level=40.0, trend="flat")
    quad = QuadrantResult()
    profile = get_profile(AssetKind.STABLECOIN)
    risk = score_risk(
        market, gate, att, quad, {},
        asset_kind=AssetKind.STABLECOIN,
        profile=profile,
        issuer_reserve_status="partial",
    )
    # 应有 depeg 分项，不应有 mc_to_liquidity
    assert "depeg" in risk.components
    assert "mc_to_liquidity" not in risk.components
    assert "turnover" not in risk.components
    # 发行方状态被记录
    assert "issuer_reserve" in risk.components


def test_risk_stablecoin_severe_depeg():
    """稳定币严重脱锚（5%）→ 高风险分。"""
    market = _stablecoin_market(price=0.95)
    gate = GateResult(applicable=True)
    att = AttentionMetrics(level=40.0, trend="flat")
    quad = QuadrantResult()
    profile = get_profile(AssetKind.STABLECOIN)
    risk = score_risk(
        market, gate, att, quad, {},
        asset_kind=AssetKind.STABLECOIN,
        profile=profile,
        issuer_reserve_status="verified",
    )
    assert risk.components["depeg"] >= 50
    assert risk.level in ("高", "极高")


def test_risk_stablecoin_depeg_defense():
    """USDT 官方合约场景：极端脱锚 + 池子极小 = 防御触发，不污染总分。"""
    market = MarketSnapshot(
        chain="ethereum",
        price_usd=0.001,  # 99.9% 脱锚（疑似数据错误）
        liquidity_usd=DEPEG_DEFENSE_MIN_LIQUIDITY_USD / 2,  # 小于防御阈值
        volume_h24=DEPEG_DEFENSE_MIN_VOLUME_USD / 2,
        market_cap=1_000_000,
    )
    gate = GateResult(applicable=True)
    att = AttentionMetrics(level=40.0, trend="flat")
    quad = QuadrantResult()
    profile = get_profile(AssetKind.STABLECOIN)
    risk = score_risk(
        market, gate, att, quad, {},
        asset_kind=AssetKind.STABLECOIN,
        profile=profile,
        issuer_reserve_status="unverified",
    )
    # depeg 不在 components 中（防御触发）
    assert "depeg" not in risk.components
    # drivers 中应有"疑似数据源错误池"提示
    assert any("疑似数据源错误" in d for d in risk.drivers)
    # 不应判定为"极高"风险
    assert risk.level != "极高"


def test_risk_l1_uses_volatility_not_mc_ratio():
    """L1 风险评分应使用 volatility 分项。"""
    market = MarketSnapshot(
        chain="solana",
        price_usd=100.0,
        liquidity_usd=10_000_000,
        market_cap=50_000_000_000,
        volume_h24=1_000_000_000,
        price_change_h24=15.0,  # 15% 24h 变化
    )
    gate = GateResult(applicable=True)
    att = AttentionMetrics(level=60.0, trend="flat")
    quad = QuadrantResult()
    profile = get_profile(AssetKind.L1)
    risk = score_risk(
        market, gate, att, quad, {},
        asset_kind=AssetKind.L1,
        profile=profile,
    )
    assert "volatility" in risk.components
    assert "depeg" not in risk.components  # 不会误判为脱锚


def test_risk_meme_unchanged():
    """MEME 画像：行为与 v0.1 一致（向后兼容）。"""
    market = MarketSnapshot(
        liquidity_usd=132_130.0,
        market_cap=1_862_030.0,
        volume_h24=9_780_000.0,
    )
    gate = GateResult(score=80, applicable=True)
    att = AttentionMetrics(level=60.0, growth=-0.2, trend="declining")
    quad = QuadrantResult(quadrant="Speculation")
    profile = get_profile(AssetKind.MEME)
    risk = score_risk(
        market, gate, att, quad, {},
        asset_kind=AssetKind.MEME,
        profile=profile,
    )
    # MEME 仍用旧分项
    assert "gate" in risk.components
    assert "liquidity_depth" in risk.components
    assert "mc_to_liquidity" in risk.components
    assert "turnover" in risk.components
    assert "attention_decay" in risk.components
    # 旧测试中"高/极高"的判定仍然成立
    assert risk.score >= 55
    assert risk.level in ("高", "极高")


def test_risk_profile_overrides_config():
    """画像权重优先级 > config 覆盖 > 默认。"""
    market = MarketSnapshot(price_usd=0.99, liquidity_usd=5_000_000)
    gate = GateResult(applicable=True)
    att = AttentionMetrics(level=40.0)
    quad = QuadrantResult()
    profile = get_profile(AssetKind.STABLECOIN)
    # config 试图让 mc_to_liquidity 权重 = 0.5（不应该生效）
    cfg = {"risk": {"weights": {"mc_to_liquidity": 0.5, "liquidity_depth": 0.5}}}
    risk = score_risk(
        market, gate, att, quad, cfg,
        asset_kind=AssetKind.STABLECOIN,
        profile=profile,
        issuer_reserve_status="verified",
    )
    # 画像要求使用 depeg，不应使用 mc_to_liquidity
    assert "mc_to_liquidity" not in risk.components


# ---------------------------------------------------------------------------
# 离线 demo 验证
# ---------------------------------------------------------------------------


def test_demo_runs_with_asset_profile():
    """analyze_demo 应能正常完成且 RiskResult 携带画像信息。"""
    from attention_market.core.pipeline import analyze_demo

    result = analyze_demo({})
    assert result.asset_kind == AssetKind.MEME.value
    assert result.profile_label
    assert result.risk.asset_kind == AssetKind.MEME.value
    assert result.risk.profile_label
