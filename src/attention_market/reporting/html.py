# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""HTML reporter：生成可保存、可分享的完整分析报告（含序列图）。"""

from __future__ import annotations

from html import escape
from typing import List, Optional, Sequence

from ..core.halflife import event_class_label
from ..core.models import AnalysisResult, SeriesPoint

__all__ = ["render_html", "write_html"]


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------


def _usd(v: Optional[float]) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"${v/1_000_000:,.2f}M"
    if v >= 1_000:
        return f"${v/1_000:,.1f}K"
    return f"${v:,.2f}"


def _num(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:,.0f}"


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v*100:+.1f}%"


def _ratio(v: Optional[float], suffix: str = "×") -> str:
    return "—" if v is None else f"{v:.1f}{suffix}"


# ---------------------------------------------------------------------------
# SVG line chart
# ---------------------------------------------------------------------------


def _sparkline(series: Sequence[SeriesPoint], w: int = 620, h: int = 200) -> str:
    """画注意力序列折线图（含峰值标注）。"""
    if len(series) < 2:
        return '<p class="muted">序列数据不足，无法绘制趋势图</p>'

    vals = [p.value for p in series]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi = lo + 1.0
    pad_l, pad_r, pad_t, pad_b = 46, 16, 22, 34
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b

    def xy(i: int, v: float) -> tuple[float, float]:
        x = pad_l + (i / (len(vals) - 1)) * plot_w
        y = pad_t + (1 - (v - lo) / (hi - lo)) * plot_h
        return x, y

    pts = [xy(i, v) for i, v in enumerate(vals)]
    path = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = f"{path} L{pts[-1][0]:.1f},{pad_t+plot_h:.1f} L{pts[0][0]:.1f},{pad_t+plot_h:.1f} Z"

    peak_idx = max(range(len(vals)), key=lambda i: vals[i])
    px, py = pts[peak_idx]

    grid = []
    for g in range(5):
        gy = pad_t + (g / 4) * plot_h
        grid.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" stroke="#eef0f3" stroke-width="1"/>')

    xlabels = []
    step = max(1, len(series) // 6)
    for i in range(0, len(series), step):
        x, _ = pts[i]
        xlabels.append(
            f'<text x="{x:.1f}" y="{h-12}" font-size="9.5" fill="#8b929c" text-anchor="middle">{escape(series[i].t[5:])}</text>'
        )

    return f'''<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" class="chart">
  <defs><linearGradient id="ga" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#2563eb" stop-opacity="0.22"/>
    <stop offset="100%" stop-color="#2563eb" stop-opacity="0.02"/></linearGradient></defs>
  {''.join(grid)}
  <path d="{area}" fill="url(#ga)"/>
  <path d="{path}" fill="none" stroke="#2563eb" stroke-width="2.2" stroke-linejoin="round"/>
  <circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="#d92d20"/>
  <text x="{px:.1f}" y="{py-10:.1f}" font-size="10.5" font-weight="700" fill="#d92d20" text-anchor="middle">峰值 {vals[peak_idx]:,.0f}</text>
  {''.join(xlabels)}
  <text x="8" y="{pad_t+6}" font-size="10" fill="#8b929c">{hi:,.0f}</text>
  <text x="8" y="{pad_t+plot_h}" font-size="10" fill="#8b929c">{lo:,.0f}</text>
</svg>'''


# ---------------------------------------------------------------------------
# quadrant matrix
# ---------------------------------------------------------------------------


def _quadrant_table(current: str) -> str:
    cells = [
        ("Expansion", "🔥 注意力驱动型增长", "注意力与市场同步上行，事件扩散期"),
        ("Divergence", "⚠️ 注意力与市场背离", "注意力仍在聚集但市场不买账"),
        ("Speculation", "⚠️ 价格脱离注意力", "注意力已衰减而价格仍涨，投机/控盘主导"),
        ("Decay", "❄️ 同步衰退", "注意力与市场同步下行，冷却阶段"),
    ]
    rows = []
    for i in range(0, len(cells), 2):
        tds = []
        for key, label, desc in cells[i:i + 2]:
            cls = "q-active" if key == current else "q"
            tds.append(f'<td class="{cls}"><b>{label}</b><br><span>{desc}</span></td>')
        rows.append(f"<tr>{''.join(tds)}</tr>")
    head_state = ["注意力 ↑", "注意力 ↓"]
    header = "".join(f'<th>{s}</th>' for s in head_state)
    return f'<table class="quad"><tr><th></th>{header}</tr>' + "".join(rows) + "</table>"


# ---------------------------------------------------------------------------
# main render
# ---------------------------------------------------------------------------


def render_html(result: AnalysisResult) -> str:
    m, a, g, r, q, h, cv = (
        result.market,
        result.attention,
        result.gate,
        result.risk,
        result.quadrant,
        result.halflife,
        result.conversion,
    )

    risk_cls = "danger" if r.score >= 75 else ("warn" if r.score >= 55 else "ok")

    gate_rows = "".join(f"<li>{escape(x)}</li>" for x in g.failed) or "<li class='muted'>无失败项</li>"
    warn_rows = "".join(f"<li class='muted'>{escape(x)}</li>" for x in g.warnings)
    note_rows = "".join(f"<li>{escape(x)}</li>" for x in result.notes)

    # 门控：未验证 ≠ 通过
    gate_score = f"{g.score}/100" if g.score is not None else "— 未验证"
    gate_cls = "ok" if (g.verified and g.applicable) else ("warn" if not g.verified else "danger")

    # 同名候选
    cand_html = ""
    if len(result.candidates) > 1:
        rows = []
        for c in result.candidates:
            sel = ' class="sel"' if c.get("selected") else ""
            rows.append(
                "<tr{sel}><td>{chain}/{dex}</td><td>{sym}</td><td>{name}</td>"
                "<td><code>{addr}</code></td><td>{liq}</td><td>{mc}</td></tr>".format(
                    sel=sel,
                    chain=escape(str(c.get("chain") or "—")),
                    dex=escape(str(c.get("dex") or "—")),
                    sym=escape(str(c.get("symbol") or "—")),
                    name=escape(str(c.get("name") or "")[:24]),
                    addr=(c.get("address") or "—")[:14],
                    liq=_usd(c.get("liquidity_usd")),
                    mc=_usd(c.get("market_cap")),
                )
            )
        cand_html = (
            '<h2>同名候选标的（重名混淆预警）</h2><div class="card">'
            "<p class='muted'>检索到多个同名/近似标的，当前分析的是高亮（→）的那一个。"
            "重名是此类分析最常见的陷阱，请用 <code>--chain</code> 或 <code>--contract</code> 精确指定。</p>"
            "<table><tr><th>链/DEX</th><th>符号</th><th>名称</th><th>合约</th>"
            "<th>池子真钱</th><th>市值</th></tr>" + "".join(rows) + "</table></div>"
        )

    trend_label = {
        "accelerating_up": "加速聚集",
        "decelerating_up": "减速上涨（顶部预警）",
        "declining": "衰退",
        "flat": "持平",
        "unknown": "未知",
    }.get(a.trend, a.trend)

    if h.status == "ok" and h.halflife_hours:
        hl_text = f"{h.halflife_hours:.1f} 小时"
        hl_sub = f"事件类型：{event_class_label(h.event_class)}"
    elif h.status == "not_decaying":
        hl_text, hl_sub = "尚未进入衰减期", "峰值之后注意力仍在上升"
    elif h.status == "insufficient_data":
        hl_text, hl_sub = "数据不足", "峰值后的观测点太少，无法拟合"
    else:
        hl_text, hl_sub = "不可用", "缺少时间序列（快照口径）"

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Attention Market · {escape(result.subject)}</title>
<style>
  :root{{--ink:#1f2329;--sub:#5b6168;--line:#e6e8eb;--accent:#2563eb;
        --danger:#d92d20;--warn:#f59e0b;--ok:#039855;--bg:#f7f8fa;}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.75;
    font-family:-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
  .wrap{{max-width:940px;margin:0 auto;padding:28px 20px 60px}}
  .hero{{background:linear-gradient(135deg,#1f2329,#3a4250);color:#fff;border-radius:16px;padding:26px 28px}}
  .hero h1{{margin:6px 0 4px;font-size:23px}}
  .hero .meta{{font-size:12.5px;opacity:.85;display:flex;gap:16px;flex-wrap:wrap;margin-top:8px}}
  h2{{font-size:18px;margin:30px 0 10px;padding-left:11px;border-left:4px solid var(--accent)}}
  .card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:12px 0}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:12px 0}}
  .kpi{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
  .kpi .lab{{font-size:12px;color:var(--sub)}}
  .kpi .val{{font-size:21px;font-weight:700;margin-top:2px}}
  .kpi .sub{{font-size:11.5px;color:var(--sub)}}
  table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0}}
  th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}}
  th{{background:#f1f3f5;color:var(--sub);font-weight:600}}
  tr.sel td{{background:#eef2ff;font-weight:600}}
  .muted{{color:var(--sub)}}
  .danger{{color:var(--danger)}} .warn{{color:#b25e09}} .ok{{color:var(--ok)}}
  .badge{{display:inline-block;padding:1px 9px;border-radius:6px;font-size:12px;font-weight:700}}
  .badge.danger{{background:#fff3f2;color:var(--danger)}}
  .badge.warn{{background:#fff7e6;color:#b25e09}}
  .badge.ok{{background:#e7f7ef;color:var(--ok)}}
  .chart{{width:100%;height:auto;background:#fff;border:1px solid var(--line);border-radius:10px;margin:8px 0}}
  table.quad td{{width:50%}}
  table.quad td.q{{color:var(--sub);background:#fafbfc}}
  table.quad td.q b{{color:var(--sub)}}
  table.quad td.q span{{font-size:12px;color:#8b929c}}
  table.quad td.q-active{{background:#eef2ff;font-weight:600}}
  table.quad td.q-active b{{color:var(--accent)}}
  table.quad td.q-active span{{font-size:12px;color:#5b6168}}
  ul{{margin:6px 0;padding-left:20px}} li{{margin:4px 0}}
  .foot{{margin-top:26px;font-size:12px;color:var(--sub);border-top:1px solid var(--line);padding-top:12px}}
  code{{background:#f1f3f5;padding:1px 5px;border-radius:4px;font-size:12.5px}}
</style>
</head>
<body><div class="wrap">

<div class="hero">
  <div style="font-size:12px;opacity:.8">ATTENTION MARKET INTELLIGENCE</div>
  <h1>{escape(result.subject)}</h1>
  <div class="meta">
    <span>查询词：{escape(result.query)}</span>
    <span>链：{escape(m.chain or '—')} / {escape(m.dex or '—')}</span>
    <span>生成时间：{escape(result.generated_at or '')}</span>
  </div>
</div>

<h2>总览：五个基础指数</h2>
<div class="grid">
  <div class="kpi"><div class="lab">① Attention Level</div>
    <div class="val">{a.level:.1f}<span style="font-size:13px;color:#8b929c">/100</span></div>
    <div class="sub">趋势：{trend_label}</div></div>
  <div class="kpi"><div class="lab">② Growth / Momentum</div>
    <div class="val">{_pct(a.growth)}</div>
    <div class="sub">二阶 {_pct(a.momentum)}</div></div>
  <div class="kpi"><div class="lab">④ Conversion β</div>
    <div class="val">{f"{cv.elasticity:.2f}" if cv.elasticity is not None else "—"}</div>
    <div class="sub">{escape(cv.interpretation)}</div></div>
  <div class="kpi"><div class="lab">Attention Half-Life</div>
    <div class="val" style="font-size:18px">{hl_text}</div>
    <div class="sub">{escape(hl_sub)}</div></div>
</div>
<div class="grid">
  <div class="kpi"><div class="lab">⑤ Market Response</div>
    <div class="val" style="font-size:17px">{escape(q.label)}</div>
    <div class="sub">{escape(q.description)}</div></div>
  <div class="kpi"><div class="lab">Risk Score</div>
    <div class="val {risk_cls}">{r.score}<span style="font-size:13px;color:#8b929c">/100</span> · {r.level}</div>
    <div class="sub">综合门控 / 流动性 / 估值 / 换手 / 注意力</div></div>
</div>

{cand_html}

<h2>E. 链上门控（前置）</h2>
<div class="card">
  <p>门控得分 <b class="{gate_cls}">{gate_score}</b>
     <span class="badge {gate_cls}">{escape(g.display)}</span></p>
  {'' if g.verified else '<p class="warn"><b>注意：</b>「未验证」表示拿不到链上安全数据（非 EVM 链或接口未覆盖），<b>不等于通过</b>。请在区块浏览器人工复核合约真伪。</p>'}
  <p style="margin-bottom:4px"><b>失败项：</b></p><ul>{gate_rows}</ul>
  {f'<p style="margin-bottom:4px"><b>提示：</b></p><ul>{warn_rows}</ul>' if warn_rows else ''}
</div>

<h2>注意力序列</h2>
<div class="card">
  {_sparkline(a.series)}
  <p class="muted" style="font-size:13px">
    信号源：{escape(', '.join(a.used_sources) or '—')}
    {('　缺失：' + escape(', '.join(a.missing_sources))) if a.missing_sources else ''}
    {('<br>' + escape(a.note)) if a.note else ''}
  </p>
  {f'<p class="warn"><b>⚠ {escape(a.top_warning)}</b></p>' if a.top_warning else ''}
</div>

<h2>Attention × Market 四象限</h2>
<div class="card">
  {_quadrant_table(q.quadrant)}
  <p class="muted" style="font-size:13px">
    当前：注意力 <b>{escape(q.attention_state)}</b> × 市场 <b>{escape(q.market_state)}</b>
    → <b>{escape(q.quadrant)}</b>
  </p>
</div>

<h2>市场快照</h2>
<div class="card">
  <table>
    <tr><th>指标</th><th>数值</th><th>解读</th></tr>
    <tr><td>池子真钱（流动性）</td><td>{_usd(m.liquidity_usd)}</td><td>池子里真实在场的钱 —— 庄家能卷走的上限</td></tr>
    <tr><td>账面市值</td><td>{_usd(m.market_cap)}</td><td>最后成交价 × 总供应量</td></tr>
    <tr><td>市值 / 真钱</td><td>{_ratio(m.mc_to_liquidity)}</td><td>倍数越大，账面估值越虚拟化</td></tr>
    <tr><td>24h 成交额</td><td>{_usd(m.volume_h24)}</td><td>—</td></tr>
    <tr><td>换手率</td><td>{_ratio(m.turnover)}</td><td>极高 = 热钱快进快出，非沉淀资金</td></tr>
    <tr><td>24h 交易笔数</td><td>{_num(float(m.txns_h24_total) if m.txns_h24_total else None)}</td><td>场内行为强度</td></tr>
    <tr><td>24h 参与地址</td><td>{_num(float(m.makers_h24) if m.makers_h24 else None)}</td><td>实际参与人数</td></tr>
    <tr><td>持有人数</td><td>{_num(float(result.security.holder_count) if result.security.holder_count else None)}</td><td>—</td></tr>
  </table>
</div>

<h2>风险驱动项</h2>
<div class="card"><ul>{''.join(f'<li>{escape(d)}</li>' for d in r.drivers)}</ul></div>

{f'<h2>备注</h2><div class="card"><ul>{note_rows}</ul></div>' if note_rows else ''}

<h2>数据来源与局限</h2>
<div class="card">
  <p><b>来源：</b>{escape('、'.join(result.sources) or '无')}</p>
  <ul class="muted">
    <li>「注意力」在本框架中是<b>间接代理指标</b>（搜索/社交/浏览量/链上活跃度），
        不是全网注意力的直接测量，且可能被刷量、水军、付费推广污染。</li>
    <li>历史序列依赖 GeckoTerminal；部分链（如 TRON/SunPump）不被覆盖，
        此时退化为快照口径，Growth / Momentum / Half-Life 不可用。</li>
    <li>本框架为<b>解释性与诊断性</b>工具，不是预测模型。</li>
  </ul>
</div>

<div class="foot">
  attention-market · Attention → Behavior → Market Intelligence Framework（研究用途）<br>
  本工具仅为链上与公开数据的核查分析，<b>不构成任何投资建议</b>。
  我国明确禁止虚拟货币交易炒作，相关代币不受法律保护，参与即自负全部损失。<br>
  <sub>Generated with WorkBuddy · {escape(result.generated_at or '')}</sub>
</div>

</div></body></html>'''


def write_html(result: AnalysisResult, path: str) -> str:
    html = render_html(result)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path
