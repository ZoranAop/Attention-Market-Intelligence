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
        add(f"      ✗ {f}")
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
        "decelerating_up": "减速上涨 ⚠",
        "declining": "衰退",
        "flat": "持平",
        "unknown": "未知",
    }.get(a.trend, a.trend)
    add(f"      Growth(1阶) {_fmt_pct(a.growth)}   Momentum(2阶) {_fmt_pct(a.momentum)}   → {trend_label}")
    if a.top_warning:
        add(_c(f"      ⚠ {a.top_warning}", YELLOW, use_color))
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
        add(f"      t½ = {h.halflife_hours:.1f} 小时   事件类型：{h.event_class or '—'}"
            f"   拟合 R²={h.r_squared:.2f}" if h.r_squared is not None else f"      t½ = {h.halflife_hours:.1f} 小时")
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

    # --- sources & notes ---
    if result.sources:
        add(_c("  数据来源：" + "、".join(result.sources), DIM, use_color))
    for n in result.notes:
        add(_c(f"  ! {n}", YELLOW, use_color))
    add(_c("  本工具为研究与分析框架，不构成任何投资建议。", DIM, use_color))
    add("")

    return "\n".join(L)


def print_report(result: AnalysisResult, use_color: Optional[bool] = None) -> None:
    print(render_console(result, use_color=use_color))
