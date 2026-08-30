# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Terminal reporter：把分析结果渲染成可读的终端报告。"""

from __future__ import annotations

import os
from typing import Optional

from ..core.models import AnalysisResult

__all__ = ["render_console", "print_report"]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"


def _c(text: str, color: str, enabled: bool = True) -> str:
    return f"{color}{text}{RESET}" if enabled else text


def _fmt_usd(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    if value >= 1_000:
        return f"${value/1_000:,.1f}K"
    return f"${value:,.2f}"


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    if abs(value) < 0.0005:
        return "≈0.0%"
    return f"{value*100:+.1f}%"


def _fmt_ratio(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}×"


def _short_addr(addr: Optional[str]) -> str:
    if not addr:
        return "—"
    return addr if len(addr) <= 14 else f"{addr[:6]}…{addr[-4:]}"


def render_console(result: AnalysisResult, use_color: Optional[bool] = None) -> str:
    """渲染终端报告文本。"""
    if use_color is None:
        use_color = not os.environ.get("NO_COLOR")

    L: list[str] = []
    add = L.append

    add("")
    add(_c("═══ Attention Market Intelligence ═══", BOLD, use_color))
    add(f"  标的：{_c(result.subject, CYAN, use_color)}   （查询词：{result.query}）")
    m = result.market
    add(
        f"  Chain: {m.chain or '—'}   DEX: {m.dex or '—'}   "
        f"Pair: {_short_addr(m.pair_address)}   Contract: {_short_addr(m.base_address)}"
    )
    add("")

    # --- 同名候选（重名混淆预警）---
    if len(result.candidates) > 1:
        add(_c("  [!] 同名候选：检索到多个标的，请确认你要分析的是哪一个", YELLOW, use_color))
        for c in result.candidates:
            mark = "→" if c.get("selected") else " "
            add(
                f"      {mark} {c.get('chain')}/{c.get('dex')}: "
                f"{c.get('symbol') or '—'} ({(c.get('name') or '')[:18]})  "
                f"Addr={_short_addr(c.get('address'))}  Liq={_fmt_usd(c.get('liquidity_usd'))}"
            )
        add(_c("      提示：用 --chain 或 --contract 精确指定", DIM, use_color))
        add("")

    # --- E. Gate ---
    gate = result.gate
    if gate.verified:
        gate_color = GREEN if gate.applicable else RED
    else:
        gate_color = YELLOW      # 未验证 ≠ 通过
    add(_c("  [E] 链上门控", BOLD, use_color))
    score_text = f"{gate.score}/100" if gate.score is not None else "—（未验证）"
    add(f"      得分 {score_text}   " + _c(gate.display, gate_color, use_color))
    for f in gate.failed:
        add(f"      x {f}")
    for w in gate.warnings:
        add(_c(f"      ! {w}", DIM, use_color))
    add("")

    # --- Market ---
    add(_c("  [Market] 市场快照", BOLD, use_color))
    add(f"      价格 {m.price_usd if m.price_usd is not None else '—'}   "
        f"24h 涨跌 {_fmt_pct((m.price_change_h24 or 0)/100 if m.price_change_h24 else None)}")
    add(f"      池子真钱 {_fmt_usd(m.liquidity_usd)}   账面市值 {_fmt_usd(m.market_cap)}   "
        f"市值/真钱 {_fmt_ratio(m.mc_to_liquidity)}")
    add(f"      24h 成交额 {_fmt_usd(m.volume_h24)}   换手 {_fmt_ratio(m.turnover)}")
    add(f"      24h 交易 {_fmt_num(float(m.txns_h24_total) if m.txns_h24_total else None)} 笔   "
        f"参与地址 {_fmt_num(float(m.makers_h24) if m.makers_h24 else None)}")
    add("")

    # --- A. Attention ---
    a = result.attention
    add(_c("  [A] Attention Index", BOLD, use_color))
    add(f"      Level {a.level:.1f}/100" if a.level is not None else "      Level —")
    trend_label = {
        "accelerating_up": "加速聚集",
        "decelerating_up": "减速上涨 [!]",
        "declining": "衰退",
        "flat": "持平",
        "unknown": "未知",
    }.get(a.trend, a.trend)
    add(f"      Growth(1阶) {_fmt_pct(a.growth)}   Momentum(2阶) {_fmt_pct(a.momentum)}   → {trend_label}")
    if a.top_warning:
        add(_c(f"      [!] {a.top_warning}", YELLOW, use_color))
    if a.note:
        add(_c(f"      · {a.note}", DIM, use_color))
    add(f"      信号源：{', '.join(a.used_sources) or '—'}"
        + (f"   （缺失：{', '.join(a.missing_sources)}）" if a.missing_sources else ""))
    add("")

    # --- C. Conversion ---
    cv = result.conversion
    add(_c("  [C] Conversion（注意力 → 行为）", BOLD, use_color))
    add(f"      弹性 β = {cv.elasticity:.2f}" if cv.elasticity is not None else "      弹性 β = —")
    add(f"      判定：{cv.interpretation}")
    if cv.note:
        add(_c(f"      · {cv.note}", DIM, use_color))
    add("")

    # --- M. Quadrant ---
    q = result.quadrant
    add(_c("  [M] Attention × Market 象限", BOLD, use_color))
    add(f"      注意力：{q.attention_state}   市场：{q.market_state}")
    add(f"      → {q.label}")
    add(_c(f"      {q.description}", DIM, use_color))
    add("")

    # --- H. Half-Life ---
    h = result.halflife
    add(_c("  [H] Attention Half-Life", BOLD, use_color))
    if h.status == "ok" and h.halflife_hours:
        add(f"      t1/2 = {h.halflife_hours:.1f} 小时   事件类型：{h.event_class or '—'}"
            f"   R2={h.r_squared:.2f}" if h.r_squared is not None else f"      t1/2 = {h.halflife_hours:.1f} 小时")
    elif h.status == "not_decaying":
        add("      峰值之后仍在上升 —— 尚未进入衰减期")
    elif h.status == "insufficient_data":
        add("      峰值后数据点不足，无法拟合衰减")
    else:
        add("      不可用（缺少时间序列）")
    add("")

    # --- R. Risk ---
    r = result.risk
    risk_color = RED if r.score >= 75 else (YELLOW if r.score >= 55 else GREEN)
    add(_c("  [R] Risk", BOLD, use_color))
    add(f"      风险分 {_c(f'{r.score}/100', risk_color, use_color)}   等级：{_c(r.level, risk_color, use_color)}")
    for d in r.drivers[:6]:
        add(f"      · {d}")
    add("")

    # --- v0.3: T (Tag: Asset / Profile / Regime) ---
    regime = result.regime
    regime_color = {
        "Bull": GREEN, "Range": CYAN, "Bear": YELLOW, "Crisis": RED, "Unknown": DIM,
    }.get(regime.kind.value, DIM)
    add(_c("  [T] Asset / Profile / Regime", BOLD, use_color))
    add(f"      Asset: {result.subject}   Profile: {_c(result.profile_label or '—', CYAN, use_color)}")
    add(f"      Regime: {_c(regime.kind.value, regime_color, use_color)}"
        + (f"   risk_score={regime.risk_score:.0f}" if regime.risk_score is not None else ""))
    add("")

    # --- v0.3: Axis Readings (4 axes) ---
    if result.axis_readings:
        add(_c("  [Axis] 4-Axis Readings", BOLD, use_color))
        axis_order = ["attention", "onchain", "fundamental", "macro"]
        for k in axis_order:
            ar = result.axis_readings.get(k)
            if ar is None:
                continue
            tag = f"{k:11s}"
            if ar.unavailable:
                add(f"      {tag} {_c('unavailable', DIM, use_color)}   {_c(ar.reason or '—', DIM, use_color)}")
            else:
                level = f"{ar.level:5.1f}" if ar.level is not None else "   — "
                growth = _fmt_pct(ar.growth)
                mom = _fmt_pct(ar.momentum) if ar.momentum is not None else "   —  "
                z = f"{ar.z_score:+.2f}" if ar.z_score is not None else "  — "
                hl = f"t½={ar.half_life_h:.0f}h" if ar.half_life_h is not None else ""
                add(f"      {tag} L={level}  g={growth}  m={mom}  z={z}  {hl}")
        add("")

    # --- v0.3: D Divergence ---
    if result.divergences:
        add(_c("  [D] Divergence（跨轴背离）", BOLD, use_color))
        for d in result.divergences[:5]:
            sev_color = {"critical": RED, "warning": YELLOW, "info": DIM}.get(d.severity, DIM)
            tag = _c(f"[{d.severity}]", sev_color, use_color)
            add(f"      {tag} {d.name}   z_gap={d.z_gap:+.2f}   {_c(d.description, DIM, use_color)}")
        add("")

    # --- v0.3: P Phase ---
    p = result.phase
    if p.primary != "Unknown":
        add(_c("  [P] Phase", BOLD, use_color))
        phase_color = RED if p.primary in ("Peak",) else (
            YELLOW if p.primary in ("Late Expansion", "Drawdown") else (
                GREEN if p.primary in ("Expansion", "Recovery", "Re-accumulation") else CYAN))
        down_tag = _c(" [regime_downgrade]", YELLOW, use_color) if p.regime_downgrade_applied else ""
        add(f"      阶段：{_c(p.primary, phase_color, use_color)}   置信度 {p.confidence:.2f}{down_tag}")
        for rule in p.rule_chain[:5]:
            add(_c(f"        · {rule}", DIM, use_color))
        add("")

    # --- sources & notes ---
    if result.sources:
        add(_c("  数据来源：" + "、".join(result.sources), DIM, use_color))
    for n in result.notes:
        add(_c(f"  ! {n}", YELLOW, use_color))
    add(_c("  本工具为研究与分析框架，不构成任何投资建议。", DIM, use_color))
    add("")

    return "\n".join(L)


def print_report(result: AnalysisResult, use_color: Optional[bool] = None) -> None:
    """渲染并输出终端报告，同时处理 Windows GBK 环境的编码问题。"""
    import codecs
    _output = render_console(result, use_color=use_color)
    # Windows GBK 控制台无法显示某些 Unicode 字符（如 ▓、✗、½ 等）。
    # 用 errors='replace' 替换无法编码的字符，避免 UnicodeEncodeError。
    try:
        print(_output)
    except UnicodeEncodeError:
        # 降级：把 Unicode 字符替换为 ASCII 近似
        _safe = codecs.encode(_output, "ascii", "replace").decode("ascii")
        print(_safe)
