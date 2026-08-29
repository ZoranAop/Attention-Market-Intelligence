# attention-market

**Attention Market Intelligence**

> An open-source framework for measuring how attention transforms into engagement, behavior,
> market activity, value, and risk.
>
> 一个开源的注意力市场分析框架，用于研究注意力如何转化为参与、行为、市场活动、价值与风险。

```
                    EVENT
                      │
                      ▼
                 ATTENTION
              ┌───────┼───────┐
              ▼       ▼       ▼
           Search   Social   News
              │       │       │
              └───────┼───────┘
                      ▼
                 ENGAGEMENT
                      │
                      ▼
                   INTENT
                      │
                      ▼
                   ACTION
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
          Purchase  Trade   Signup
              │       │       │
              └───────┼───────┘
                      ▼
                   MARKET
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
            Price    Value  Liquidity
                      │
                      ▼
                    RISK
```

---

## 为什么不是 "meme 工具"

Meme 币只是这套框架里**最极端、最容易观察**的一个案例——因为它的价格几乎完全由注意力驱动，
没有现金流、utility 或赎回权来干扰信号。

但同样的链条适用于任何"被注意力定价"的对象：

| 场景 | Attention 来源 | Action | Market 结果 |
|------|---------------|--------|------------|
| Meme / Token | 社交、搜索、热搜 | 买入 / 交易 | 价格、市值 |
| 股票 | 新闻、财报、研报 | 买卖 | 股价、成交量 |
| NFT | 社区、KOL | Mint / 竞价 | 地板价 |
| 电商 | 内容曝光、直播 | 下单 | GMV |
| App | 投放、口碑 | 下载 / 注册 | DAU、留存 |
| 游戏 | 讨论、直播 | 注册 / 充值 | 流水 |
| 影视 | 热搜、预告 | 购票 / 观看 | 票房 |
| 品牌 | 社交传播 | 购买 | 销量 |
| 创作者 | 粉丝关注 | 订阅 / 付费 | 收入 |
| 社会事件 | 新闻报道 | 行为改变 | 相关资产重定价 |

所以本项目要回答的核心问题只有一个：

> **"注意力值多少钱？"**

---

## 五个基础指数

| # | 指数 | 回答的问题 |
|---|------|-----------|
| ① | **Attention Index (AI)** | 现在有多少人在关注？ |
| ② | **Attention Momentum** | 关注度在加速还是减速？（Level / Growth / Momentum 三层） |
| ③ | **Engagement Index** | 关注之后，有多少人真的参与了？ |
| ④ | **Conversion Index** | 注意力有没有转化成实际行为？（注意力弹性 β） |
| ⑤ | **Market Response** | 市场对这些注意力作出了什么反应？ |

### 背离信号

| Attention | Market | 读法 |
|-----------|--------|------|
| ↑ | ↑ | 注意力驱动型增长，事件扩散期 |
| ↑ | ↓ | **Divergence** — 注意力在涨但市场不买账，预期落空 |
| ↓ | ↑ | **Speculation** — 价格脱离注意力基础，投机主导 |
| ↓ | ↓ | **Decay** — 注意力与市场同步衰退，进入冷却 |

### Attention Half-Life

注意力从峰值衰减到 50% 所需时间，用于区分事件的"续航力"：

| 事件类型 | 典型 Half-Life |
|---------|---------------|
| 突发新闻 | 小时级 |
| 明星事件 | 天级 |
| 影视作品 | 周级 |
| 品牌事件 | 月级 |
| 科技趋势 | 月 / 年级 |

---

## 快速开始

```bash
# 安装（仅需 Python 3.9+）
pip install -r requirements.txt

# 按名称分析一个代币（自动搜索 + 链上核查 + 注意力量化）
python -m attention_market analyze "我的女友景甜"

# 指定合约与链
python -m attention_market analyze --contract 0x49b79e9250797025f72f44d7286e267bc2a4b9ed --chain bsc

# 生成 HTML 报告
python -m attention_market analyze "PEPE" --html report.html

# 离线演示（不联网，用内置样例数据跑通全流程）
python -m attention_market demo --html demo.html

# 输出 JSON（供下游研究使用）
python -m attention_market analyze "PEPE" --json out.json
```

示例输出（终端）：

```
═══ Attention Market Intelligence · 我的女友景甜 ═══
  Chain: tron   Pair: SunSwap V3   Contract: CTUNfK…nQi

  [E] 链上门控            ⚠ 3 项未通过   → 模型适用性受限
  [A] Attention Level     62.4 / 100
      Growth (1st)        +18.3%   Momentum (2nd)   -6.1  ← 减速
  [C] Conversion β        0.42     （注意力部分转化）
  [M] Quadrant            ⚠ Speculation（注意力↓ + 价格↑）
  [H] Half-Life           31.5 h   （天级衰减 → 明星事件型）
  [R] Risk Score          78 / 100  —— 高危
```

---

## 架构

```
src/attention_market/
├── cli.py                 命令行入口：analyze / demo
├── core/
│   ├── models.py          数据模型（Snapshot / Series / Result）
│   ├── attention.py       Attention Index：Level / Growth / Momentum
│   ├── halflife.py        指数衰减拟合 → Attention Half-Life
│   ├── conversion.py      注意力弹性 β（Attention → Action）
│   ├── quadrant.py        Attention × Market 四象限
│   ├── gate.py            链上门控（合约真伪 / LP / mint / 集中度）
│   ├── risk.py            综合风险评分
│   └── pipeline.py        主流水线：Event → Attention → Action → Market → Risk
├── providers/             可插拔数据源（全部可降级）
│   ├── dexscreener.py     市场快照（多链，免费）
│   ├── geckoterminal.py   OHLCV 历史序列（免费）
│   ├── goplus.py          合约安全检测（免费）
│   ├── onchain_activity.py 场内行为代理：txns / volume / makers
│   └── web_attention.py   场外注意力代理：Wikipedia / HackerNews / Reddit
├── reporting/             console / html / json 三种输出
└── utils/                 http（重试 + fallback）、normalize（标准化）
```

### 设计原则

1. **免费优先、零配置可跑** —— 默认只使用无需 API Key 的公开数据源；付费/易限流的源默认关闭。
2. **Provider 可插拔 + 优雅降级** —— 任一数据源失败，指标标记为 `unavailable` 而非崩溃。
3. **诚实标注** —— 报告会明确区分「已核实」「代理指标」「数据缺失」，不把推测写成事实。

### 工程笔记：五个关键教训

这些是实盘跑数据时踩出来的坑，每一个都会**静默地产出错误结论**，因此单独记录：

**1. Growth / Momentum 必须在原始信号上算，不能在标定后的指数上。**
Attention Index 为便于横向比较做了 log10 压缩 + 截断到 0-100，
这一变换会把原始信号 75% 的涨幅压成指数上 24% 的涨幅 —— 真实动态被严重低估。
因此本项目：**Level 用标定指数（可横向比），Growth/Momentum 用各信号自身变化率的加权平均（保真实动态）**。

**2. 半衰期必须在原始信号上拟合，否则会被系统性高估。**
log 标定会把**指数衰减压成线性衰减**，在其上拟合 λ 得到的半衰期严重偏大
（实测：真实 t½=67h 的序列，在标定指数上拟合出 186h，误差近 3 倍）。
跨量纲信号聚合必须用**加权几何平均**而非算术平均 —— 几何聚合保持乘性变化率，
对指数衰减仍得指数衰减。

**3. 「拿不到数据」绝不能显示成「通过」。**
当 GoPlus 不覆盖某条链（如 TRON）时，门控若默认给 100 分，等于发放虚假安全感。
本项目用 `score=None` + `verified=False` 显式区分：
**未验证 ≠ 通过**。并进一步区分原因（未收录 / 非 EVM 链 / 接口失败）——
「未被收录」本身就是风险信号（合约极新）。

**4. 最后一根日线 K 是「当日未走完」的 candle。**
GeckoTerminal 返回的最新日线只累计了几小时成交量，
直接采用会让 Growth 出现 -90% 量级的假信号。本项目默认丢弃该根并显式标注。

**5. 同名标的是常态，不是例外。**
一次查询「我的女友景甜」返回 6 个标的，横跨 bsc / tron / robinhood 三条链；
查「PEPE」同样返回多个版本。因此工具**必须列出候选**并强制用户用
`--chain` / `--contract` 精确指定，而不是默默挑流动性最高的那个。

### 数据源与局限

| Provider | 用途 | Key | 说明 |
|----------|------|-----|------|
| DexScreener | 价格 / 流动性 / 成交量 / 交易数 | 免费 | 覆盖多链，含 TRON |
| GeckoTerminal | OHLCV 历史序列 | 免费 | 部分链不支持，缺失时降级为快照模式 |
| GoPlus | 蜜罐 / mint / LP 锁仓 / 持有人 | 免费 | EVM 链（BSC/ETH…），非 EVM 不可用 |
| Wikipedia Pageviews | 场外注意力代理 | 免费 | 仅对有人物/事件条目的对象有效 |
| Hacker News | 场外注意力代理 | 免费 | 偏科技 / crypto 话题 |
| Reddit | 场外注意力代理 | 免费 | 默认关闭（限流），可在 config 启用 |

> ⚠️ **重要**：本项目的"注意力"是**间接代理指标（proxy）**，不是真实的全网注意力测量。
> 所有注意力信号（讨论量、搜索量、浏览量）都可能被刷量、水军、付费推广污染。
> 指标的用途是**诊断与比较**，不是预测。

---

## 配置

见 `config/default.yaml`：注意力源权重、象限阈值、风险权重、半衰期基准均可调整。

```yaml
attention:
  weights:
    onchain_txns: 0.40      # 场内行为（最难伪造）
    volume: 0.20
    wikipedia: 0.15
    hackernews: 0.15
    reddit: 0.10
quadrant:
  attention_threshold: 0.05   # ±5% 视为持平
  market_threshold: 0.02
```

---

## 路线图

- [ ] 更多 Attention Provider（Google Trends、X/Twitter、Telegram、微博指数）
- [ ] 多对象横向对比（`compare` 命令：同一事件下的多个标的）
- [ ] 事件标注数据集（记录热点事件 → 注意力曲线 → 市场结果的完整案例）
- [ ] 非加密场景适配（股票、App、影视票房的 Attention→Action 映射）
- [ ] Web Dashboard（时间序列可视化 + 背离预警）

---

## 免责声明

本项目是**研究与分析框架**，不是投资工具，不提供任何投资建议。

- 加密货币相关功能仅用于链上数据核查与风险教育。我国明确禁止虚拟货币交易炒作，
  相关代币不受法律保护，参与即自负全部损失。
- 所有注意力指标为间接代理，可被操纵，不应作为任何决策的唯一依据。

---

## License

MIT — 见 [LICENSE](LICENSE)。

---

<sub>Project scaffold generated with <b>WorkBuddy</b> (https://workbuddy.cn).</sub>
