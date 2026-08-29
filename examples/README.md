# 示例输出

本目录存放 `attention-market` 的示例报告，用于展示三种典型场景下的输出形态。

| 文件 | 场景 | 说明 |
|------|------|------|
| `demo_report.html` | 离线演示 | 内置合成数据（事件爆发 → 见顶 → 指数衰减），不联网即可复现完整链路 |
| `demo_report.json` | 离线演示 | 同一份结果的 JSON 输出（供下游研究/回测使用） |
| `demo_console_output.txt` | 离线演示 | 终端输出原文 |
| `case_jingtian_tron.html` | 真实案例（TRON） | 「我的女友景甜」在 SunSwap 上的版本 —— 事件驱动型新币 |
| `case_pepe.html` | 真实案例（Ethereum） | PEPE —— 成熟 meme 币，有完整历史序列 |

## 复现

```bash
# 离线演示（无需网络）
python -m attention_market demo --html examples/demo_report.html

# 真实案例
python -m attention_market analyze "我的女友景甜" --chain tron --html examples/case_jingtian_tron.html
python -m attention_market analyze "PEPE" --html examples/case_pepe.html
```

## 案例要点

### case_jingtian_tron（事件驱动型新币）

完美符合「注意力期货」模型：

- 池子真钱远小于账面市值 —— 账面估值高度虚拟化
- 无历史 OHLCV（TRON/SunPump 不被 GeckoTerminal 覆盖）→ 退化为快照口径，
  Growth / Momentum / Half-Life 标记为不可用，而非编造数值
- GoPlus 不覆盖非 EVM 链 → 门控显示「未验证」，而非「通过」

### case_pepe（成熟 meme 币）

- 有完整历史序列 → Growth / Momentum / Half-Life 均可用
- 门控命中真实红旗：**LP 由项目方地址控制**（可随时抽池）
- 场外注意力（Hacker News）近期为 0 → 半衰期自动回退到**场内行为序列**口径
- 同一次查询检索到多个同名标的（ethereum / solana 多个版本）
  —— 这正是「重名混淆」陷阱的实证，必须用 `--chain` 或 `--contract` 精确指定

> ⚠️ 所有案例数据均为特定时点的快照，且仅用于演示框架能力，不构成任何投资建议。
