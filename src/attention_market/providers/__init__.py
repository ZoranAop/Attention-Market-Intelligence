# ---------------------------------------------------------------------------
# attention-market · Attention → Behavior → Market Intelligence Framework
# Part of the Attention Market Intelligence project.
# SPDX-License-Identifier: MIT
# ---------------------------------------------------------------------------
"""Pluggable data providers.

约定（新增 provider 时请遵守）：

  1. 每个 provider 模块暴露 `fetch_*(..., cfg)` 形式的纯函数；
  2. **任何失败都返回 None**，绝不抛异常、绝不返回伪造数据；
  3. 读取自身开关：cfg['providers'][<name>]['enabled']；
  4. 免费优先 —— 需要 API Key 的源默认关闭，在 config 中显式启用。

当前可用：
  dexscreener       市场快照（多链，免费）
  geckoterminal     OHLCV 历史序列（免费，部分链不支持）
  goplus            合约安全检测（EVM，免费）
  onchain_activity  场内行为代理（交易笔数 / 参与地址 / 成交额）
  web_attention     场外注意力代理（Wikipedia / HackerNews / Reddit）
"""

from . import dexscreener, geckoterminal, goplus, onchain_activity, web_attention

__all__ = ["dexscreener", "geckoterminal", "goplus", "onchain_activity", "web_attention"]
