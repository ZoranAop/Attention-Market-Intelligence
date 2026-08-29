# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Configuration loader.

优先级：--config 指定 > 包内 config/default.yaml > 内置空配置（全部走代码默认值）
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml

__all__ = ["default_config_path", "load_config"]


def default_config_path() -> str:
    """包内 config/default.yaml 的路径（安装后可通过 importlib.resources 访问）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.normpath(os.path.join(here, "..", "config"))
    return os.path.join(pkg_dir, "default.yaml")


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """加载 YAML 配置；任何失败都返回空 dict（代码内有完整默认值）。"""
    target = path or default_config_path()
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}
