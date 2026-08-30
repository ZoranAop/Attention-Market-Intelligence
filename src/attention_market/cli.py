# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Command line interface.

    python -m attention_market analyze "我的女友景甜"
    python -m attention_market analyze --contract 0x... --chain bsc --html out.html
    python -m attention_market demo --html demo.html
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from .core.pipeline import analyze, analyze_demo
from .reporting import print_report, render_console, write_html, write_json
from .utils.config import load_config

__all__ = ["main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="attention-market",
        description="Attention Market Intelligence — 注意力 → 行为 → 市场 分析框架",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- analyze ----
    p = sub.add_parser("analyze", help="分析一个标的（按名称或合约地址）")
    p.add_argument("query", nargs="?", help="代币名称 / 符号（如 PEPE、我的女友景甜）")
    p.add_argument("--contract", help="合约地址（与 query 二选一，优先使用）")
    p.add_argument("--chain", help="限定链（bsc / ethereum / solana / tron ...）")
    p.add_argument("--config", help="自定义配置文件路径（YAML）")
    p.add_argument("--html", help="输出 HTML 报告到该路径")
    p.add_argument("--json", dest="json_out", help="输出 JSON 到该路径")
    p.add_argument("--no-color", action="store_true", help="关闭终端颜色")
    # v0.3
    p.add_argument("--regime", choices=["bull", "range", "bear", "crisis", "unknown"],
                   help="显式指定 regime（跳过自动检测；RFC v0.3 §9）")
    p.add_argument("--no-regime", action="store_true",
                   help="跳过 regime 计算（所有 Phase 不做 Regime 强制降级）")

    # ---- demo ----
    d = sub.add_parser("demo", help="离线演示（不联网，使用内置合成数据）")
    d.add_argument("--config", help="自定义配置文件路径（YAML）")
    d.add_argument("--html", help="输出 HTML 报告到该路径")
    d.add_argument("--json", dest="json_out", help="输出 JSON 到该路径")
    d.add_argument("--no-color", action="store_true", help="关闭终端颜色")

    # ---- v0.3: regime (单跑 regime) ----
    r = sub.add_parser("regime", help="只输出当前 Market Regime（v0.3）")
    r.add_argument("--config", help="自定义配置文件路径（YAML）")
    r.add_argument("--no-color", action="store_true", help="关闭终端颜色")

    # ---- v0.3: axes (单跑 4 轴读数) ----
    ax = sub.add_parser("axes", help="只输出 4 轴读数（v0.3）")
    ax.add_argument("query", nargs="?", help="代币名称 / 符号")
    ax.add_argument("--contract", help="合约地址")
    ax.add_argument("--chain", help="限定链")
    ax.add_argument("--config", help="自定义配置文件路径（YAML）")
    ax.add_argument("--no-color", action="store_true", help="关闭终端颜色")

    return parser


def _emit(result, args) -> None:
    """统一的输出逻辑：终端 + 可选 HTML / JSON。"""
    print_report(result, use_color=not args.no_color)

    if getattr(args, "html", None):
        try:
            path = write_html(result, args.html)
            print(f"[ok] HTML 报告已生成：{path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] HTML 报告生成失败：{exc}", file=sys.stderr)

    if getattr(args, "json_out", None):
        try:
            path = write_json(result, args.json_out)
            print(f"[ok] JSON 已生成：{path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] JSON 生成失败：{exc}", file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(getattr(args, "config", None))

    if args.cmd == "analyze":
        if not args.query and not args.contract:
            parser.error("analyze 需要提供 query 或 --contract")
        query = args.query or args.contract
        print(f"[..] 正在检索并分析：{query}")
        # v0.3: 在 cfg 中注入 regime override（--regime 优先于自动检测）
        if getattr(args, "regime", None):
            cfg = _inject_regime(cfg, args.regime)
        if getattr(args, "no_regime", False):
            cfg = _inject_no_regime(cfg)
        result = analyze(
            query=query,
            cfg=cfg,
            contract=args.contract,
            chain=args.chain,
        )
        _emit(result, args)
        return 0

    if args.cmd == "demo":
        print("[..] 离线演示模式（合成数据，不联网）")
        result = analyze_demo(cfg)
        _emit(result, args)
        return 0

    if args.cmd == "regime":
        return _cmd_regime(args, cfg)

    if args.cmd == "axes":
        return _cmd_axes(args, cfg)

    parser.error(f"未知命令：{args.cmd}")
    return 2


# ---------------------------------------------------------------------------
# v0.3 helpers
# ---------------------------------------------------------------------------


def _inject_regime(cfg: dict, regime: str) -> dict:
    """把 CLI 的 --regime 注入 cfg，使 pipeline 跳过自动检测走指定值。"""
    cfg = dict(cfg or {})
    cfg["regime"] = {**(cfg.get("regime") or {}), "override": regime.lower()}
    return cfg


def _inject_no_regime(cfg: dict) -> dict:
    cfg = dict(cfg or {})
    cfg["regime"] = {**(cfg.get("regime") or {}), "override": "unknown"}
    return cfg


def _cmd_regime(args, cfg: dict) -> int:
    """regime 子命令：只计算当前 Market Regime。"""
    print("[..] 计算 Market Regime（v0.3）")
    try:
        from .core.regime import classify_regime, RegimeSignal
        from .core.models import RegimeKind
        # 默认全 unavailable（占位）
        signals = {
            "btc_30d": RegimeSignal("btc_30d", None, available=False),
            "dxy_30d": RegimeSignal("dxy_30d", None, available=False),
            "ust2y_level": RegimeSignal("ust2y_level", None, available=False),
            "ust2y_chg": RegimeSignal("ust2y_chg", None, available=False),
            "funding": RegimeSignal("funding", None, available=False),
            "vix": RegimeSignal("vix", None, available=False),
        }
        regime = classify_regime(
            signals,
            weights=(cfg.get("regime") or {}).get("weights"),
            bands=(cfg.get("regime") or {}).get("risk_bands"),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[err] regime 计算失败：{exc}", file=sys.stderr)
        return 1
    print(f"Regime: {regime.kind.value}   risk_score={regime.risk_score}   confidence={regime.confidence:.2f}")
    print(f"可用信号 ({len(regime.available_signals)}/6)：{', '.join(regime.available_signals) or '—'}")
    if regime.missing_signals:
        print(f"缺失信号：{', '.join(regime.missing_signals)}")
    return 0


def _cmd_axes(args, cfg: dict) -> int:
    """axes 子命令：只输出 4 轴读数。"""
    if not args.query and not args.contract:
        parser_error = build_parser()
        parser_error.error("axes 需要提供 query 或 --contract")
    query = args.query or args.contract
    print(f"[..] 正在分析 4 轴读数：{query}")
    result = analyze(query=query, cfg=cfg, contract=args.contract, chain=args.chain)
    if not result.axis_readings:
        print("[warn] 无可用轴读数")
        return 0
    for k in ("attention", "onchain", "fundamental", "macro"):
        ar = result.axis_readings.get(k)
        if ar is None:
            continue
        if ar.unavailable:
            print(f"  {k:11s}  unavailable: {ar.reason or '—'}")
        else:
            print(
                f"  {k:11s}  L={ar.level if ar.level is not None else '—':>5}  "
                f"g={ar.growth}  m={ar.momentum}  z={ar.z_score}  "
                f"t½={ar.half_life_h}h"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
