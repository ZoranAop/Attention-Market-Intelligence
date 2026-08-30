# RFC v0.3 · Digital Asset Intelligence Framework

> 状态：**草案 / 待 Review** · 目标版本：v0.3 · 预计 4–6 周
> 取代 v0.2 路线图中"v0.3"一节。本文是实施前的**唯一来源**，所有代码改动必须与本文一致。

---

## 0. 背景与动机

v0.2 把框架从"MEME 币专用"抽象为"通用金融资产生成式分析框架（UFAM）"，引入了 6 种 AssetKind 与对应的 AssetProfile，**门控/风险口径按画像分流**。

但在三类资产上跑实测时发现 v0.2 仍然偏窄：

1. **横切因素缺失**：在 2022 熊市（BTC -65%）和 2024 牛市中，同一只代币的"注意力→行为"传导效率相差 3–5 倍；当前框架没有任何"市场状态"的上下文。
2. **信号轴单维**：只把 `signals` 当作一个平铺字典，缺少对"四大类信号"的结构化区分：
   - **Attention**（场外热度）—— 已实现
   - **On-chain**（场内行为）—— 已实现
   - **Fundamental**（基本面：TVL/收入/费用）—— 占位未落地
   - **Macro**（宏观：DXY/利率/Funding/VIX）—— 占位未落地
3. **生命周期判定缺失**：象限（Expansion/Divergence/...）只是 Attention × Market 二维投影，缺少"Stealth / Late Expansion / Peak / Drawdown / Decay / Recovery / Re-accumulation"等阶段语义。
4. **跨轴背离不可量化**：当前只能看"注意力 vs 价格"的二维背离，无法回答"Attention 跑得比 Liquidity 快多少"这类问题。

**v0.3 的目标**：把框架从"MEME 工具"正式升级为

> **An open-source Digital Asset Intelligence framework for measuring how attention, adoption, capital, network activity, and market behavior interact across crypto assets.**

---

## 1. 顶层架构

```
                     Digital Asset（标的）
                            │
              ┌─────────────┴─────────────┐
              ↓                           ↓
        Asset Profile                Market Regime
              │                           │
   ┌──────────┼──────────┐                │
   ↓          ↓          ↓                ↓
Attention  Fundamental  On-chain        Macro
   │          │          │                │
   └──────────┼──────────┘                │
              ↓                           │
           Behavior ←─────────────────────┘
              ↓
       Market Response
              ↓
            Risk
              ↓
       Divergence + Phase
              ↓
        Intelligence
```

- **Profile** 决定"用什么口径"（权重、门控开关、Phase 阈值覆盖）
- **Regime** 决定"在什么宏观背景下解读"（乘数 / 强制降级）
- **Behavior = f(Attention, On-chain, Fundamental, Macro)** —— 4 轴汇合后产生行为判定
- **Risk** 由 v0.2 机制接管，仅新增"接受 axis_readings 作为可选输入"
- **Divergence + Phase** 是 v0.3 新增的两个判定层，最终汇总为 Intelligence

---

## 2. 数据模型扩展

### 2.1 新增枚举：`SignalAxis`

```python
class SignalAxis(str, Enum):
    ATTENTION   = "attention"      # 场外：Wiki/HN/Reddit/Search
    ONCHAIN     = "onchain"        # 场内：txns/makers/volume/holders
    FUNDAMENTAL = "fundamental"    # 基本面：TVL/Revenue/Fees（DeFi/L1）
    MACRO       = "macro"          # 宏观：DXY/UST2Y/Funding/VIX（L1/STABLE）
```

### 2.2 新增数据类：`AxisReading`

```python
@dataclass
class AxisReading:
    axis: SignalAxis
    level: Optional[float]         # 0–100
    growth: Optional[float]        # 1 阶（窗口可配）
    momentum: Optional[float]      # 2 阶
    half_life_h: Optional[float]    # 仅 attention 有意义
    z_score: Optional[float]       # 相对自身滚动窗口
    unavailable: bool = False
    reason: str = ""               # unavailable 时说明
    source_breakdown: Dict[str, Any] = field(default_factory=dict)
```

### 2.3 新增数据类：`DivergenceSignal`

```python
@dataclass
class DivergenceSignal:
    name: str                      # e.g. "Attention > Liquidity"
    leading_axis: SignalAxis
    lagging_axis: SignalAxis
    z_gap: float                   # z_leading - z_lagging
    severity: str                  # "info" | "warning" | "critical"
    description: str               # 模板渲染后的自然语言
```

### 2.4 新增数据类：`PhaseTag`

```python
@dataclass
class PhaseTag:
    primary: str                   # 8 阶段之一
    confidence: float              # 0–1
    rule_chain: List[str]          # 命中的规则链（用于调试）
    regime_downgrade_applied: bool # 是否被 Regime 强制降级
```

### 2.5 `AnalysisResult` 扩展（向后兼容）

```python
@dataclass
class AnalysisResult:
    ...  # 既有字段
    # v0.2 已加：
    asset_kind: str
    profile_label: str
    # v0.3 新增：
    regime: Optional[str]                       # Bull/Range/Bear/Crisis/Unknown
    regime_confidence: Optional[float]           # 0–1
    axis_readings: Dict[str, AxisReading]        # 4 轴
    divergences: List[DivergenceSignal]
    phase: Optional[PhaseTag]
```

---

## 3. AssetProfile 扩展

```python
@dataclass
class AssetProfile:
    ...  # 既有字段全部保留
    axis_weights: Dict[str, float] = field(default_factory=lambda: {
        "attention": 0.40, "onchain": 0.40, "fundamental": 0.10, "macro": 0.10,
    })
    required_axes: List[str] = field(default_factory=lambda: ["attention", "onchain"])
    phase_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    regime_overrides: Dict[str, Any] = field(default_factory=dict)
```

**优先级链**（与 v0.2 一致）：
```
profile.axis_weights > cfg["axes"] > DEFAULT_AXIS_WEIGHTS
```

### 3.1 各画像默认轴权重

| Profile | attention | onchain | fundamental | macro | required_axes |
|---------|-----------|---------|-------------|-------|----------------|
| MEME | 0.50 | 0.45 | 0.00 | 0.05 | [attention, onchain] |
| STABLECOIN | 0.20 | 0.30 | 0.10 | 0.40 | [macro, onchain] |
| L1 | 0.20 | 0.40 | 0.20 | 0.20 | [onchain, fundamental] |
| DEFI | 0.25 | 0.35 | 0.35 | 0.05 | [fundamental, onchain] |
| SECURITY | 0.20 | 0.10 | 0.50 | 0.20 | [fundamental] |
| UNKNOWN | 0.40 | 0.40 | 0.10 | 0.10 | [attention, onchain] |

> STABLECOIN 故意把 macro 权重拉到最高，因为脱锚事件与宏观流动性周期强相关。

---

## 4. Market Regime（`core/regime.py`）

### 4.1 信号与权重

| 信号 | 来源 | 权重 | 不可用时 |
|------|------|------|----------|
| BTC 30d 涨幅 | GeckoTerminal / CoinGecko | 0.35 | 跳过，按剩余等比分配 |
| DXY 30d 变化 | FRED | 0.20 | 同上 |
| UST 2Y 利率水平 | FRED | 0.075 | 同上 |
| UST 2Y 30d 变化 | FRED | 0.075 | 同上 |
| 平均 Funding Rate | Coinalyze | 0.20 | 同上 |
| VIX 当前 | FRED / CBOE | 0.10 | 同上 |

### 4.2 子分映射（线性插值 → 0–100，100 = 最 risk-off）

| 信号 | 0 分 | 50 分 | 100 分 |
|------|------|-------|--------|
| BTC 30d | ≥ +25% | 0% | ≤ -25% |
| DXY 30d | ≤ -3% | 0% | ≥ +3% |
| UST2Y 水平 | ≤ 3.0% | 4.5% | ≥ 5.5% |
| UST2Y 30d | ≤ -30bp | 0bp | ≥ +30bp |
| Funding | -0.02%/8h | 0 | -0.05%/8h |
| VIX | ≤ 12 | 20 | ≥ 35 |

加权求和 → `risk_score ∈ [0, 100]`，再分箱。

### 4.3 分类阈值

| Regime | risk_score | 触发条件（满足其一即可优先判定） |
|--------|------------|----------------------------------|
| **Crisis** | 80–100 | VIX > 35 **OR** BTC 30d < -25% **OR** 全市场 Funding < -0.05%/8h |
| **Bear** | 60–79 | risk_score ∈ [60, 80] **OR** BTC 30d ∈ [-25%, -10%] |
| **Range** | 40–59 | risk_score ∈ [40, 60] **AND** 无强趋势 |
| **Bull** | 0–39 | BTC 30d ∈ [+10%, +25%] **AND** Funding ∈ [-0.02%, +0.05%] |

### 4.4 不可用降级

- 全 6 个信号中 ≥ 4 个不可用 → `regime="Unknown"`，`regime_confidence=0.0`，**所有 Phase 不做 Regime 降级**
- 仅 1–2 个不可用 → 用剩余信号等比分配权重继续算，`confidence` 按可用信号比例折扣

---

## 5. Phase 判定（`core/phase.py`）

### 5.1 8 阶段定义

```
Stealth → Expansion → Late Expansion → Peak → Drawdown → Decay → Recovery → Re-accumulation
```

### 5.2 输入

每个 `AxisReading` 提供 `level / growth / momentum / z_score / half_life_h`。

### 5.3 默认阈值（`DEFAULT_PHASE_THRESHOLDS`）

| 阶段 | Attention | On-chain (Behavior) | Market (Liquidity+Price) | Regime 强制降级 |
|------|-----------|---------------------|--------------------------|------------------|
| **Stealth** | level < 30, growth > 0 | txns/volume 低位爬升 | price flat, liq 稳定 | — |
| **Expansion** | level 30–70, growth > 0 | behavior 增速 ≥ attention 增速 (β > 0.5) | price 上行, liq + | — |
| **Late Expansion** | level 60–90, **momentum 转负** | behavior 增速放缓 | price 仍上行, **liq 增速 < attention 增速** | — |
| **Peak** | level ≥ 80, **momentum < 0** | behavior 见顶 | price 顶部, **存在 attention-liq 背离** | **任何非 Bull regime → 直接 Peak** |
| **Drawdown** | level 50–80, growth < 0 | behavior 双降 | price -10% ~ -30%, **liq -5% ~ -20%** | — |
| **Decay** | level < 50, **half_life < 24h** | behavior 接近 0 | price 横盘或阴跌, liq 持续流出 | — |
| **Recovery** | z_score > 0（重新抬升） | β 重新 > 0 | price 转正, liq 回流 | — |
| **Re-accumulation** | level 40–65, **half_life > 72h** | makers 上升, behavior 平稳 | price 横盘, liq 缓慢堆积 | — |

### 5.4 强制降级规则

```python
def apply_regime_downgrade(phase, regime):
    # 熊市/危机中: Late Expansion 与 Peak 不可区分 → 强制 Peak
    if regime in ("Bear", "Crisis") and phase == "Late Expansion":
        return "Peak"
    # 牛市中: Drawdown 多数为洗盘 → 降级为 Decay
    if regime == "Bull" and phase == "Drawdown":
        return "Decay"
    return phase
```

### 5.5 判定顺序

短路匹配：`Stealth → Expansion → Late Expansion → Peak → Drawdown → Decay → Recovery → Re-accumulation`。
未命中 → `phase.primary="Unknown"`，`confidence=0.0`。

### 5.6 Phase × Regime 矩阵

| Phase \ Regime | Bull | Range | Bear | Crisis |
|---------------|------|-------|------|--------|
| Stealth | 早期建仓 | 等待 | 观望 | 不参与 |
| Expansion | 主升 | 区间突破 | 反转可能 | ⚠ |
| Late Expansion | 准备止盈 | ⚠ | 撤退 | 清仓 |
| Peak | 顶部 | 顶部 | 顶部 | 顶部 |
| Drawdown | Decay (降级) | 中继 | 主跌 | 崩盘 |
| Decay | 筑底 | 弱化 | 续跌 | 失速 |
| Recovery | 二波 | 反弹 | 死猫 | 不参与 |
| Re-accumulation | 下一轮准备 | 盘整 | 最后一跌可能 | — |

---

## 6. Divergence 判定（`core/divergence.py`）

### 6.1 跨轴 z-score 背离

```python
ATTENTION_VS_LIQUIDITY = {
    "name": "Attention > Liquidity",
    "leading": "attention", "lagging": "liquidity",
    "trigger": lambda r: r["attention"].z_score - r["liquidity"].z_score > 1.5,
    "severity": lambda gap: (
        "critical" if gap > 2.5 else
        "warning"  if gap > 1.5 else "info"
    ),
}
```

### 6.2 预置 6 类背离

| 名称 | leading | lagging | 含义 |
|------|---------|---------|------|
| Attention > Liquidity | attention | liquidity | 热度先于资金 |
| Attention > Behavior | attention | behavior | 看热闹不买 |
| Behavior > Attention | behavior | attention | 暗中建仓 |
| Macro > On-chain | macro | onchain | 宏观领先链上 |
| Fundamental > Attention | fundamental | attention | 价值未被定价 |
| Price > Liquidity | price | liquidity | 价格虚高 |

> `liquidity` 与 `price` 在 v0.3 中作为 Market 轴的衍生信号（从 `onchain` 拆出），不单独建轴。

### 6.3 输出

返回 `List[DivergenceSignal]`，报告中按 `severity` 排序。`info` 默认折叠。

---

## 7. Provider 扩展

### 7.1 新增 Providers

| Provider | 用途 | 必选 Key | 失败降级 |
|----------|------|----------|----------|
| `providers/fundamental.py` | DeFiLlama TVL + Token Terminal Revenue | CoinGecko free（占位） | 轴标 unavailable |
| `providers/macro.py` | FRED UST2Y/DXY/VIX + Coinalyze Funding | 无（默认限流） | 轴标 unavailable |

### 7.2 现有 Provider 不动

`dexscreener / geckoterminal / goplus / onchain_activity / web_attention` 全部保留，仅 `web_attention` 拆为 `attention` provider（语义更清晰，但 API 不变）。

---

## 8. 报告层扩展

### 8.1 JSON

新增字段（向下兼容）：

```json
{
  "asset_kind": "meme",
  "profile_label": "注意力驱动长尾代币（默认案例）",
  "regime": "Bear",
  "regime_confidence": 0.78,
  "axis_readings": {
    "attention": { "level": 82.0, "growth": 0.18, "momentum": -0.04, "half_life_h": 31, "z_score": 1.9 },
    "onchain":   { "level": 70.0, "growth": 0.46, "z_score": 1.4 },
    "fundamental": { "unavailable": true, "reason": "non-defi asset" },
    "macro":     { "level": 35.0, "growth": -0.08, "z_score": -0.6 }
  },
  "divergences": [
    { "name": "Attention > Liquidity", "z_gap": 1.7, "severity": "warning", "description": "..." }
  ],
  "phase": {
    "primary": "Late Expansion",
    "confidence": 0.83,
    "rule_chain": ["attention.level∈[60,90]✓", "attention.momentum<0✓", "liq_gap>0✓"],
    "regime_downgrade_applied": false
  },
  "risk": { "score": 72, "level": "high", "drivers": [...] }
}
```

### 8.2 Console 输出顺序

```
[T]  Asset / Profile / Regime
[E]  Gate（门控）
[Axis] Attention / On-chain / Fundamental / Macro
[D]  Divergence（按严重度）
[P]  Phase（含 confidence + rule_chain）
[M]  Market（价格/流动性）
[H]  Half-Life
[β]  Conversion β
[R]  Risk
[C]  Conclusion（自动生成自然语言）
```

### 8.3 HTML

新增四个区：`Axis Readings` / `Divergence` / `Phase` / `Regime Context`。
原 `Risk` / `Gate` / `Market` 区块保留，向下兼容。

---

## 9. CLI 扩展

```bash
python -m attention_market analyze "PEPE" --regime bear   # 显式指定 regime
python -m attention_market analyze "PEPE" --no-regime     # 跳过 regime 计算
python -m attention_market regime                          # 只输出当前 regime
python -m attention_market axes "PEPE"                     # 只输出 4 轴读数
```

`--regime` 优先级：`--regime` 参数 > 自动检测 > `Unknown`。

---

## 10. 配置文件

新增 `config/default.yaml` 字段：

```yaml
axes:
  weights: { attention: 0.40, onchain: 0.40, fundamental: 0.10, macro: 0.10 }
  required: [attention, onchain]

regime:
  enabled: true
  providers: { fred: true, coinalyze: true }
  risk_bands:  # 覆盖默认值
    btc_30d: { bearish: -0.25, neutral: 0.0, bullish: 0.25 }

phase:
  thresholds_file: "config/phase_thresholds.yaml"  # 可选，覆盖 DEFAULT_PHASE_THRESHOLDS

divergence:
  z_gap_warning: 1.5
  z_gap_critical: 2.5
```

---

## 11. 优先级与向后兼容

### 11.1 必须保留的 v0.2 行为

- `AssetKind` 枚举值不变（MEME/STABLECOIN/L1/DEFI/SECURITY/UNKNOWN）
- `register_profile()` 旧签名可用
- `profile.signals` 旧字典字段保留（内部自动映射到 v0.3 轴）
- `AnalysisResult` 旧字段全保留

### 11.2 v0.3 默认行为

- `axis_weights` 默认值（见 §3.1）
- `required_axes` 默认值（见 §3.1）
- Regime 计算默认 **开启**（FRED 失败自动降级）
- Phase 计算默认 **开启**（基于轴读数 + Regime）

### 11.3 测试要求

- v0.2 原 37 测试**无修改通过**
- v0.3 新增 ≥ 25 测试覆盖：4 轴 / Regime / Phase / Divergence / 向后兼容
- 总测试 ≥ 62 个

---

## 12. 文件改动清单

```
新增  src/attention_market/core/regime.py        Regime 分类（6 信号 + 4 档）
新增  src/attention_market/core/axes.py           4 轴统一接口
新增  src/attention_market/core/divergence.py     z-score 跨轴背离（6 类）
新增  src/attention_market/core/phase.py          8 阶段 + Regime 降级
新增  src/attention_market/providers/fundamental.py  DeFiLlama + 占位
新增  src/attention_market/providers/macro.py        FRED + Coinalyze
新增  config/phase_thresholds.yaml               可选阈值覆盖
新增  tests/test_v03_axes.py                     ≥8 测试
新增  tests/test_v03_regime.py                   ≥6 测试
新增  tests/test_v03_phase.py                    ≥8 测试
新增  tests/test_v03_divergence.py               ≥3 测试

修改  src/attention_market/core/models.py        新增 AxisReading/DivergenceSignal/PhaseTag
修改  src/attention_market/core/asset.py         新增 SignalAxis 枚举（保留 AssetKind）
修改  src/attention_market/core/registry.py      AssetProfile 新增 axis_weights/required_axes/phase_overrides/regime_overrides
修改  src/attention_market/core/pipeline.py      接入 4 轴 → divergence → phase → risk
修改  src/attention_market/core/risk.py          接受 axis_readings（按需归一化）
修改  src/attention_market/core/__init__.py      导出新模块
修改  src/attention_market/cli.py                新增 --regime / regime / axes 子命令
修改  src/attention_market/reporting/console.py  输出顺序扩展
修改  src/attention_market/reporting/html.py     4 个新区块
修改  src/attention_market/reporting/json.py     字段扩展（向下兼容）
修改  src/attention_market/config/default.yaml   axes/regime/phase/divergence 段
修改  README.md                                   路由图小节替换为指向本 RFC
```

---

## 13. 风险与已知限制

| 风险 | 缓解 |
|------|------|
| FRED API 限流 | 缓存 1h + 失败降级为"Unknown" |
| DeFiLlama 覆盖不全（TRON 链无 TVL） | 该轴 unavailable；DeFi 资产在 TRON 会被自动降级为 MEME |
| Phase 8 阶段规则过拟合 | `phase_overrides` 可按 Profile 调整；并通过回测持续校准 |
| Regime 误判（小样本） | `regime_confidence < 0.5` 时不做 Phase 强制降级 |
| 旧画像使用 `signals` 而非 `axis_weights` | pipeline 自动从 `signals` 派生 `axis_weights`（attention=wiki+hn+reddit, onchain=txns+makers+volume, 其余 0） |

---

## 14. 落地步骤（实施时按此顺序）

1. `core/models.py` —— 新增枚举/数据类
2. `core/asset.py` —— 新增 `SignalAxis`
3. `core/registry.py` —— `AssetProfile` 扩展
4. `core/axes.py` —— 4 轴统一接口（先用合成数据跑通）
5. `core/regime.py` —— Regime + 降级
6. `core/divergence.py` —— 6 类背离
7. `core/phase.py` —— 8 阶段 + Regime 降级
8. `core/pipeline.py` —— 串接
9. `core/risk.py` —— 接受 axis_readings
10. `providers/fundamental.py` / `providers/macro.py`
11. `reporting/*` 三层输出
12. `cli.py` 子命令
13. `config/default.yaml` + `config/phase_thresholds.yaml`
14. `tests/test_v03_*.py` 4 个文件
15. 跑全量测试 + 更新 README 与 RELEASE

---

## 15. 开放问题（实施前需最终决定）

- [ ] FRED 是否真用免费端点？还是用占位 provider + YAML 配置开关？
- [ ] Phase 规则是否先在 MEME/STABLECOIN 两个画像上跑回测再上线？
- [ ] `axis_weights` 与 v0.2 `signals` 的派生关系：是否暴露给用户 override，还是内部硬映射？
- [ ] TRON dog 币（v0.2 已跑通 5 个案例）是否作为 v0.3 Phase 规则的回归测试 fixture？

---

> **审批要点**：阈值表（§4.2 / §5.3 / §6.1）、6 种新预置画像权重（§3.1）、Phase × Regime 矩阵（§5.6）。