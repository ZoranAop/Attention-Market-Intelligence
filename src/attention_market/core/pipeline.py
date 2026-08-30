# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""主流水线：Event → Attention → Engagement → Action → Market → Value → Risk

编排原则：
  1. 任何数据源失败都不中断流程，对应指标标记为 unavailable；
  2. 有历史序列 → 计算 Growth / Momentum / Half-Life / 转化率；
     无历史序列 → 退化为「快照口径」，只给 Level，并明确标注其余指标不可用；
  3. 链上门控（E）不通过时，后续结论全部标注「模型适用性受限」。
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional, Sequence

from ..providers import dexscreener, geckoterminal, goplus, onchain_activity, web_attention
from ..utils.normalize import align_series
from .asset import AssetKind, AssetSignals, classify_asset, load_whitelist
from .attention import (
    DEFAULT_RANGES,
    build_attention_metrics,
    geometric_aggregate,
    scale_signal,
)
from .conversion import compute_conversion
from .gate import evaluate_gate
from .halflife import estimate_half_life
from .models import (
    AnalysisResult,
    AttentionMetrics,
    MarketSnapshot,
    SecurityInfo,
    SeriesPoint,
)
from .quadrant import classify_quadrant
from .registry import get_profile
from .risk import score_risk
# v0.3
from .axes import compute_axis_readings
from .divergence import detect_divergence
from .models import RegimeKind, RegimeReading
from .phase import classify_phase
from .regime import RegimeSignal, classify_regime

__all__ = ["analyze", "analyze_demo"]


# ---------------------------------------------------------------------------
# 通用化辅助：资产分类 + 画像解析
# ---------------------------------------------------------------------------


def _resolve_whitelist_path(cfg: dict) -> Optional[str]:
    """从 cfg 中取白名单文件路径（可被 config 覆盖）。"""
    return ((cfg or {}).get("assets") or {}).get("whitelist_path")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _pick_labels(*series: Optional[Sequence[SeriesPoint]]) -> List[str]:
    """选最长的一条序列作为时间轴。"""
    best: List[str] = []
    for s in series:
        if not s:
            continue
        labels = [p.t for p in s]
        if len(labels) > len(best):
            best = labels
    return best


def _snapshot_level(
    snapshot_signals: Dict[str, Optional[float]],
    weights: Dict[str, float],
    ranges: Dict,
) -> Optional[float]:
    """无历史序列时的兜底：用 24h 快照信号按绝对标定算一个 Level。"""
    num = den = 0.0
    for name, value in snapshot_signals.items():
        score = scale_signal(name, value, ranges)
        if score is None:
            continue
        w = float(weights.get(name, 0.0))
        num += w * score
        den += w
    return (num / den) if den > 0 else None


def _normalize_price_change(value: Optional[float]) -> Optional[float]:
    """归一化 24h 涨跌幅到 [-1, 1] 范围。"""
    if value is None:
        return None
    if abs(value) > 1.5:
        return value / 100.0
    return value


def _compute_regime_or_unknown(cfg: dict) -> RegimeReading:
    """计算 Market Regime。

    v0.3 默认走「无 provider 信号 → Unknown」路径，因为 FRED/Coinalyze
    接入在 v0.3.1 后续小版本（RFC §10 / §14 step 10）。这样 pipeline 在
    没有外部信号时仍能完整跑通，且 Phase 不会做 Regime 强制降级。

    CLI 优先级（RFC §9）：--regime override > 自动检测 > Unknown
    """
    try:
        regime_cfg = (cfg or {}).get("regime", {}) or {}
        override = (regime_cfg.get("override") or "").lower().strip()
        if override:
            try:
                kind = RegimeKind(override.capitalize() if override != "unknown" else "Unknown")
            except ValueError:
                kind = RegimeKind.UNKNOWN
            return RegimeReading(
                kind=kind,
                risk_score=None,
                confidence=0.0,
                note=f"manual override via CLI/config: {override}",
            )
        signals = {
            "btc_30d": RegimeSignal("btc_30d", None, available=False),
            "dxy_30d": RegimeSignal("dxy_30d", None, available=False),
            "ust2y_level": RegimeSignal("ust2y_level", None, available=False),
            "ust2y_chg": RegimeSignal("ust2y_chg", None, available=False),
            "funding": RegimeSignal("funding", None, available=False),
            "vix": RegimeSignal("vix", None, available=False),
        }
        return classify_regime(
            signals,
            weights=regime_cfg.get("weights"),
            bands=regime_cfg.get("risk_bands"),
        )
    except Exception:  # noqa: BLE001
        return RegimeReading(
            kind=RegimeKind.UNKNOWN,
            risk_score=None,
            confidence=0.0,
            note="regime computation failed",
        )


def _compute_axis_readings(
    att: AttentionMetrics,
    market: MarketSnapshot,
    halflife,
    conversion,
    profile,
    regime: RegimeReading,
):
    """统一包装：异常时返回空 dict（保证 pipeline 不中断）。"""
    try:
        return compute_axis_readings(
            attention=att,
            market=market,
            halflife=halflife,
            conversion=conversion,
            profile=profile,
            regime=regime,
        )
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------


def analyze(
    query: str,
    cfg: dict,
    contract: Optional[str] = None,
    chain: Optional[str] = None,
) -> AnalysisResult:
    """分析一个标的：按名称或合约地址。"""
    cfg = cfg or {}
    sources: List[str] = []
    notes: List[str] = []

    # ---------------- 1. Market ----------------
    if contract:
        pairs = dexscreener.fetch_by_contract(contract, cfg)
        if not pairs:
            pairs = dexscreener.search_pairs(contract, cfg)
    else:
        pairs = dexscreener.search_pairs(query, cfg)

    if chain:
        filtered = [p for p in pairs if (p.get("chainId") or "").lower() == chain.lower()]
        if filtered:
            pairs = filtered

    best = dexscreener.pick_best_pair(pairs)
    market: MarketSnapshot = dexscreener.parse_pair(best) if best else MarketSnapshot()

    # 同名候选：重名混淆是此类分析最常见的陷阱（"我的女友景甜"已出现多个链上版本）
    # 按流动性取前 5，并确保「实际选中的那个」一定出现在列表里
    def _liq(p: Dict[str, Any]) -> float:
        try:
            return float(((p.get("liquidity") or {}).get("usd")) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    ranked = sorted(pairs or [], key=_liq, reverse=True)
    top = ranked[:5]
    if best is not None:
        ids = {id(p) for p in top}
        if id(best) not in ids:
            top = top[:4] + [best]

    candidates: List[Dict[str, Any]] = []
    for p in top:
        snap = dexscreener.parse_pair(p)
        candidates.append(
            {
                "chain": snap.chain,
                "dex": snap.dex,
                "symbol": snap.base_symbol,
                "name": snap.base_name,
                "address": snap.base_address,
                "pair": snap.pair_address,
                "liquidity_usd": snap.liquidity_usd,
                "market_cap": snap.market_cap,
                "selected": p is best,
            }
        )

    if best:
        sources.append("DexScreener(市场快照)")
        subject = market.base_name or market.base_symbol or query
        n_chains = len({c.get("chain") for c in candidates if c.get("chain")})
        if len(candidates) > 1:
            notes.append(
                f"[!] 检索到 {len(candidates)} 个同名/近似标的（分布在 {n_chains} 条链）——"
                f"默认选取流动性最高的一个。重名混淆是常见陷阱，"
                f"请用 --chain 或 --contract 精确指定你要分析的那个"
            )
    else:
        subject = query
        notes.append("未在任何 DEX 检索到该标的 —— 市场侧数据全部缺失，结论不可用于任何判断")

    # ---------------- 1.5 资产分类（通用化 v0.2 新增） ----------------
    # 在门控之前先判定资产类型，门控与后续风险都按画像分流
    whitelist = load_whitelist(_resolve_whitelist_path(cfg))
    asset_signals = AssetSignals(
        symbol=market.base_symbol,
        name=market.base_name,
        chain=market.chain,
        has_contract=bool(market.base_address),
        market_cap=market.market_cap,
        price_usd=market.price_usd,
    )
    asset_kind = classify_asset(asset_signals, whitelist)
    profile = get_profile(asset_kind)
    notes.append(f"[{asset_kind.value}] {profile.label}")

    # ---------------- 2. Gate (model E) ----------------
    sec_status = "no_address"
    if market.base_address:
        raw, sec_status = goplus.fetch_security_ex(market.base_address, market.chain or "", cfg)
        security: SecurityInfo = goplus.parse_security(raw)
        if raw:
            sources.append("GoPlus(合约安全)")
    else:
        security = SecurityInfo(available=False)

    if security.available and security.token_symbol and market.base_symbol:
        if security.token_symbol.lower() != market.base_symbol.lower():
            notes.append(
                f"[!] 合约真实标识与检索结果不一致：合约读出 "
                f"「{security.token_name} / {security.token_symbol}」，而交易对显示为 "
                f"「{market.base_name} / {market.base_symbol}」—— 高度疑似错币/诱饵，请人工复核"
            )

    g_cfg = cfg.get("gate", {}) or {}
    gate = evaluate_gate(
        security,
        market,
        penalties=g_cfg.get("penalties"),
        concentration_threshold=g_cfg.get("concentration_threshold", 0.30),
        fail_score=g_cfg.get("fail_score", 50),
        asset_kind=asset_kind,
        profile=profile,
    )
    # 把"拿不到数据"的具体原因说清楚 —— 不同原因的风险含义完全不同
    if not security.available:
        reason = {
            "not_found": "GoPlus 未收录该合约（极新，或不存在于此链）—— 新币本身就是风险信号",
            "unsupported_chain": f"GoPlus 不覆盖 {market.chain} 链（非 EVM）",
            "http_error": "GoPlus 接口请求失败/超时",
            "disabled": "GoPlus 数据源在配置中被关闭",
            "no_address": "未获取到合约地址",
        }.get(sec_status, "链上安全数据不可用")
        gate.warnings.append(f"{reason} —— 门控未验证，不等于通过")

    # ---------------- 3. History (OHLCV) ----------------
    tf_pref = (cfg.get("providers", {}).get("geckoterminal", {}) or {}).get("ohlcv_timeframe", "day")
    ohlcv = geckoterminal.fetch_ohlcv(market.chain or "", market.pair_address or "", cfg)
    volume_series: List[SeriesPoint] = []
    if ohlcv:
        # 日线的最后一根是「当日未走完」的 candle，成交量只有几小时累计值，
        # 会把 Growth/Momentum 严重扭曲（实测出现过 -90% 的假信号）—— 丢弃。
        drop_last = tf_pref == "day"
        volume_series = geckoterminal.ohlcv_to_series(ohlcv, column=5, drop_last=drop_last)
        sources.append("GeckoTerminal(OHLCV历史)")
        if drop_last:
            notes.append("已丢弃当日未走完的 K 线（避免 Growth/Momentum 被不完整数据扭曲）")
    else:
        notes.append(
            "未获取到历史 OHLCV（该链可能不被 GeckoTerminal 覆盖）"
            " —— 退化为快照口径：Growth / Momentum / Half-Life 不可用"
        )

    # ---------------- 4. Off-chain attention ----------------
    att_cfg = cfg.get("attention", {}) or {}
    weights: Dict[str, float] = att_cfg.get("weights") or {}
    ranges = {**DEFAULT_RANGES, **(att_cfg.get("reference_ranges") or {})}

    search_term = query or market.base_name or market.base_symbol or ""
    wiki = web_attention.wikipedia_series(search_term, cfg) if search_term else None
    hn = web_attention.hackernews_series(search_term, cfg) if search_term else None
    rd = web_attention.reddit_series(search_term, cfg) if search_term else None
    if wiki:
        sources.append("Wikipedia Pageviews(场外注意力)")
    if hn:
        sources.append("HackerNews(场外注意力)")
    if rd:
        sources.append("Reddit(场外注意力)")

    # ---------------- 5. Attention Index ----------------
    labels = _pick_labels(volume_series, wiki, hn, rd)
    att_metrics: AttentionMetrics

    series_signals: Dict[str, List[Optional[float]]] = {}
    if labels:
        if volume_series:
            series_signals["volume"] = align_series(volume_series, labels)
        if wiki:
            series_signals["wikipedia"] = align_series(wiki, labels)
        if hn:
            series_signals["hackernews"] = align_series(hn, labels)
        if rd:
            series_signals["reddit"] = align_series(rd, labels)

    if series_signals and len(labels) >= 2:
        att_metrics = build_attention_metrics(series_signals, weights, labels, cfg)
        if not att_metrics.used_sources:
            att_metrics.note = "注意力信号源全部缺失，指数不可用"
    else:
        # 快照兜底：只给 Level
        snap = onchain_activity.snapshot_signals(market)
        level = _snapshot_level(snap, weights, ranges)
        att_metrics = AttentionMetrics(
            level=level,
            trend="unknown",
            used_sources=[k for k, v in snap.items() if v is not None],
            missing_sources=[k for k, v in snap.items() if v is None],
            note="仅 24h 快照，无时间序列：Level 可用，Growth / Momentum / Half-Life 不可用",
        )
        if snap.get("onchain_txns") or snap.get("volume"):
            sources.append("DexScreener(场内行为快照)")

    # ---------------- 6. Half-Life & Conversion ----------------
    hps = geckoterminal.hours_per_step(tf_pref)
    hl_cfg = cfg.get("halflife", {}) or {}

    # 半衰期必须在**原始注意力信号**上拟合，不能在标定后的 Index 上
    # （log 标定会把指数衰减压成线性衰减，导致 t½ 被系统性高估）
    ext_names = ("wikipedia", "hackernews", "reddit")
    ext_signals = {k: v for k, v in series_signals.items() if k in ext_names}

    hl_series: List[SeriesPoint] = []
    hl_source = "场外注意力信号"
    if ext_signals:
        raw_att = geometric_aggregate(ext_signals, weights, labels)
        hl_series = [
            SeriesPoint(t=labels[i], value=v)
            for i, v in enumerate(raw_att)
            if v is not None and v > 0
        ]
    # 场外信号存在但全为 0（例如近期无人讨论）时，回退到场内行为序列
    if not hl_series and series_signals.get("volume"):
        raw_att = series_signals["volume"]
        hl_source = "场内行为序列（场外注意力无有效数据，退化为行为口径）"
        hl_series = [
            SeriesPoint(t=labels[i], value=v)
            for i, v in enumerate(raw_att)
            if v is not None and v > 0
        ]
    if not hl_series:
        hl_source = "标定后指数（无原始序列，仅供参考）"
        hl_series = [p for p in att_metrics.series if p.value and p.value > 0]
    halflife = estimate_half_life(
        hl_series,
        hours_per_step=hps,
        min_points_after_peak=int(hl_cfg.get("min_points_after_peak", 3)),
        benchmarks=hl_cfg.get("benchmarks_hours"),
    )
    if halflife.status == "ok":
        notes.append(f"半衰期拟合口径：{hl_source}")

    conv_cfg = cfg.get("conversion", {}) or {}
    # 场外注意力序列（用于 β 的自变量）
    ext_series: List[SeriesPoint] = []
    for cand in (wiki, hn, rd):
        if cand:
            ext_series = cand
            break

    if ext_series and volume_series:
        conversion = compute_conversion(
            ext_series,
            volume_series,
            high=float(conv_cfg.get("high", 0.8)),
            low=float(conv_cfg.get("low", 0.2)),
        )
    else:
        conversion = compute_conversion([], [])
        conversion.note = "缺少场外注意力序列或场内行为序列，转化率（β）不可用"

    # ---------------- 7. Quadrant ----------------
    q_cfg = cfg.get("quadrant", {}) or {}
    price_change = market.price_change_h24
    if price_change is not None:
        price_change = price_change / 100.0 if abs(price_change) > 1.5 else price_change
    quadrant = classify_quadrant(
        att_metrics.growth,
        price_change,
        attention_threshold=q_cfg.get("attention_threshold", 0.05),
        market_threshold=q_cfg.get("market_threshold", 0.02),
    )

    # ---------------- 8. Risk ----------------
    # 通用化（v0.2）：稳定币需要发行方/储备核验状态
    issuer_reserve_status: Optional[str] = None
    if asset_kind == AssetKind.STABLECOIN:
        # 占位：实际接入需查询 MakerDAO PSM、USDC 储备报告等
        # 当前默认 "partial" 以体现"未完全核验"状态
        issuer_reserve_status = "partial"

    risk = score_risk(
        market,
        gate,
        att_metrics,
        quadrant,
        cfg,
        asset_kind=asset_kind,
        profile=profile,
        issuer_reserve_status=issuer_reserve_status,
    )
    # 把画像信息写入 RiskResult
    risk.asset_kind = asset_kind.value
    risk.profile_label = profile.label

    if not gate.applicable:
        notes.append("链上门控未通过 —— 以下注意力结论仅供参考，模型不适用于该标的")

    # ---------------- 9. v0.3 · Regime / 4 Axes / Divergence / Phase ----------------
    regime = _compute_regime_or_unknown(cfg)
    axis_readings = _compute_axis_readings(
        att_metrics, market, halflife, conversion, profile, regime,
    )
    divergences = detect_divergence(axis_readings, market=market)
    phase = classify_phase(
        axis_readings,
        regime,
        profile,
        price_change_h24=_normalize_price_change(price_change),
        liquidity_growth=axis_readings.get("onchain").growth if axis_readings.get("onchain") else None,
        beta=conversion.elasticity,
        divergences=divergences,
    )

    return AnalysisResult(
        query=query,
        subject=subject,
        market=market,
        security=security,
        attention=att_metrics,
        halflife=halflife,
        conversion=conversion,
        quadrant=quadrant,
        gate=gate,
        risk=risk,
        sources=sources,
        notes=notes,
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        candidates=candidates,
        asset_kind=asset_kind.value,
        profile_label=profile.label,
        # v0.3
        regime=regime,
        axis_readings=axis_readings,
        divergences=divergences,
        phase=phase,
    )


# ---------------------------------------------------------------------------
# offline demo
# ---------------------------------------------------------------------------


def analyze_demo(cfg: dict) -> AnalysisResult:
    """离线演示：用合成的「事件爆发 → 见顶 → 衰减」序列跑通全流程（不联网）。

    用于自检与教学：任何人在任何环境都能立刻看到完整输出长什么样。
    """
    cfg = cfg or {}
    days = 21
    end = _dt.date.today()
    labels = [(end - _dt.timedelta(days=days - 1 - i)).isoformat() for i in range(days)]

    # 注意力：前 8 天爆发上升，第 9 天见顶，之后指数衰减
    peak_idx = 8
    attention_values: List[float] = []
    for i in range(days):
        if i <= peak_idx:
            v = 20.0 * (1.6 ** i)
        else:
            v = 20.0 * (1.6 ** peak_idx) * (0.78 ** (i - peak_idx))
        attention_values.append(v)

    # 场内行为：滞后 1 天，且转化存在损耗（β < 1）
    # 乘 2000 是为了让量级落在真实成交额的标定区间内（USD 千级以上）。
    # 乘常数不改变 log-log 回归的斜率，因此不影响 β = 0.55 这一设定。
    action_values = [
        max(1.0, (attention_values[i - 1] if i > 0 else attention_values[0]) ** 0.55) * 2000.0
        for i in range(days)
    ]

    att_series = [SeriesPoint(t=labels[i], value=attention_values[i]) for i in range(days)]
    act_series = [SeriesPoint(t=labels[i], value=action_values[i]) for i in range(days)]

    att_cfg = cfg.get("attention", {}) or {}
    weights = att_cfg.get("weights") or {}
    signals = {
        "wikipedia": [v for v in attention_values],
        "volume": [v for v in action_values],
    }
    att_metrics = build_attention_metrics(signals, weights, labels, cfg)
    att_metrics.used_sources = ["wikipedia(demo)", "volume(demo)"]
    att_metrics.note = (
        "[!] 演示模式：使用内置合成数据（模拟事件爆发→见顶→指数衰减），不代表任何真实标的"
    )

    hl_cfg = cfg.get("halflife", {}) or {}
    # 同样必须在原始信号上拟合，而非标定后的 Index
    raw_att = geometric_aggregate({"wikipedia": attention_values}, weights, labels)
    hl_series = [
        SeriesPoint(t=labels[i], value=v)
        for i, v in enumerate(raw_att)
        if v is not None and v > 0
    ]
    halflife = estimate_half_life(
        hl_series,
        hours_per_step=24.0,
        min_points_after_peak=int(hl_cfg.get("min_points_after_peak", 3)),
        benchmarks=hl_cfg.get("benchmarks_hours"),
    )

    conv_cfg = cfg.get("conversion", {}) or {}
    conversion = compute_conversion(
        att_series,
        act_series,
        high=float(conv_cfg.get("high", 0.8)),
        low=float(conv_cfg.get("low", 0.2)),
    )

    quadrant = classify_quadrant(
        att_metrics.growth,
        0.08,
        attention_threshold=(cfg.get("quadrant", {}) or {}).get("attention_threshold", 0.05),
        market_threshold=(cfg.get("quadrant", {}) or {}).get("market_threshold", 0.02),
    )

    market = MarketSnapshot(
        chain="demo",
        dex="demo",
        base_symbol="DEMO",
        base_name="Attention Demo Asset",
        price_usd=0.00042,
        liquidity_usd=132_130.0,
        market_cap=1_862_030.0,
        volume_h24=9_780_000.0,
        txns_h24_buys=4_200,
        txns_h24_sells=3_100,
        makers_h24=2_640,
        price_change_h24=8.0,
    )
    security = SecurityInfo(
        available=True,
        is_honeypot=False,
        is_mintable=True,          # 演示一项红旗
        is_in_dex=True,
        is_open_source=False,
        lp_locked=None,
        lp_owner_controlled=None,
        holder_count=1_402,
        top_holder_percent=0.34,
        token_name="Attention Demo Asset",
        token_symbol="DEMO",
    )
    g_cfg = cfg.get("gate", {}) or {}
    gate = evaluate_gate(
        security,
        market,
        penalties=g_cfg.get("penalties"),
        concentration_threshold=g_cfg.get("concentration_threshold", 0.30),
        fail_score=g_cfg.get("fail_score", 50),
    )
    # 通用化（v0.2）：演示默认按 MEME 画像
    demo_kind = AssetKind.MEME
    demo_profile = get_profile(demo_kind)
    risk = score_risk(
        market,
        gate,
        att_metrics,
        quadrant,
        cfg,
        asset_kind=demo_kind,
        profile=demo_profile,
    )
    risk.asset_kind = demo_kind.value
    risk.profile_label = demo_profile.label

    return AnalysisResult(
        query="demo",
        subject="Attention Demo Asset (DEMO)",
        market=market,
        security=security,
        attention=att_metrics,
        halflife=halflife,
        conversion=conversion,
        quadrant=quadrant,
        gate=gate,
        risk=risk,
        sources=["内置合成数据（离线演示）"],
        notes=[
            "演示模式：全部数值为合成数据，用于展示完整分析链路与输出格式",
            "市场侧数字刻意对齐一次真实核查样本（池子真钱 $132,130 / 账面市值 $1,862,030 ≈ 14×）以便对照",
            f"[{demo_kind.value}] {demo_profile.label}",
        ],
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        asset_kind=demo_kind.value,
        profile_label=demo_profile.label,
        # v0.3
        regime=_compute_regime_or_unknown(cfg),
        axis_readings=_compute_axis_readings(
            att_metrics, market, halflife, conversion, demo_profile,
            regime=_compute_regime_or_unknown(cfg),
        ),
        divergences=detect_divergence(
            _compute_axis_readings(
                att_metrics, market, halflife, conversion, demo_profile,
                regime=_compute_regime_or_unknown(cfg),
            ),
            market=market,
        ),
        phase=classify_phase(
            _compute_axis_readings(
                att_metrics, market, halflife, conversion, demo_profile,
                regime=_compute_regime_or_unknown(cfg),
            ),
            _compute_regime_or_unknown(cfg),
            demo_profile,
            price_change_h24=0.08,
            liquidity_growth=None,
            beta=conversion.elasticity,
            divergences=[],
        ),
    )
