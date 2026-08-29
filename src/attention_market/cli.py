# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# Generated with WorkBuddy (https://workbuddy.cn)
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

    # ---- demo ----
    d = sub.add_parser("demo", help="离线演示（不联网，使用内置合成数据）")
    d.add_argument("--config", help="自定义配置文件路径（YAML）")
    d.add_argument("--html", help="输出 HTML 报告到该路径")
    d.add_argument("--json", dest="json_out", help="输出 JSON 到该路径")
    d.add_argument("--no-color", action="store_true", help="关闭终端颜色")

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

    parser.error(f"未知命令：{args.cmd}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
