# Release v0.3.0 · Digital Asset Intelligence Framework

> **状态**：已发布 ✅  
> **核心定位升级**：从"注意力市场分析框架" → **Digital Asset Intelligence framework**  
> **测试**：82/82 通过（v0.2 原 37 个无修改通过 + v0.3 新增 45 个）  
> **完全向后兼容**：所有 v0.2 调用方无需任何修改

---

## 🎯 核心变更

把 v0.2 的单维"注意力分析"升级为：

> **An open-source Digital Asset Intelligence framework for measuring how attention, adoption, capital, network activity, and market behavior interact across crypto assets.**

四层新结构：

```
Digital Asset
   ├─ Asset Profile（资产类型 + 画像）
   └─ Market Regime（市场状态）
        ↓
4 Axes · Attention / On-chain / Fundamental / Macro
        ↓
Behavior
        ↓
Market Response → Risk
        ↓
Divergence + Phase（v0.3 新增判定层）
        ↓
Intelligence
```

---

## ✨ 新增功能

### 1. 4 大信号轴（`core/axes.py`）

- `SignalAxis` 枚举：`ATTENTION / ONCHAIN / FUNDAMENTAL / MACRO`
- `AxisReading` 数据类：level / growth / momentum / z_score / half_life_h
- `AssetProfile.axis_weights`：每个画像自带 4 轴权重（MEME 偏 attention 0.50，STABLECOIN 偏 macro 0.40）
- `AssetProfile.required_axes`：声明"必须"的轴；缺失则标 unavailable
- `derive_axis_weights_from_signals()`：v0.2 老 `signals` 字典自动派生 `axis_weights`（零迁移成本）

### 2. Market Regime（`core/regime.py`）

- `RegimeKind` 枚举：`Bull / Range / Bear / Crisis / Unknown`
- 6 信号合成 risk_score（BTC 30d / DXY 30d / UST2Y / Funding / VIX）
- Crisis 强制覆盖（VIX > 35 或 BTC < -25%）
- 信号缺失降级：≥4 个不可用 → Unknown
- `--regime` CLI 参数可显式覆盖自动检测

### 3. Phase 8 阶段（`core/phase.py`）

- `PHASE_STAGES`：Stealth / Expansion / Peak / Late Expansion / Drawdown / Decay / Recovery / Re-accumulation
- `PhaseTag` 数据类：primary / confidence / rule_chain / regime_downgrade_applied
- 纯规则映射（短路匹配）
- **Regime 强制降级**（RFC §5.4）：
  - Bear/Crisis + Late Expansion → Peak
  - Bull + Drawdown → Decay

### 4. Divergence（`core/divergence.py`）

- `detect_divergence()` 跨轴 z-score 背离
- 6 类预置规则：Attention > Liquidity / Attention > Behavior / Behavior > Attention / Macro > On-chain / Fundamental > Attention / Price > Liquidity
- 严重度：info / warning / critical
- 按 severity 排序返回

### 5. CLI 新增子命令

```bash
python -m attention_market analyze "PEPE" --regime bull
python -m attention_market regime                    # 只输出 Market Regime
python -m attention_market axes "PEPE"               # 只输出 4 轴读数
```

### 6. 报告层扩展

- **Console**：新增 `[T] Asset/Profile/Regime` · `[Axis] 4-Axis Readings` · `[D] Divergence` · `[P] Phase`
- **HTML**：4 个新卡片（Regime / 4-Axis / Divergence / Phase）
- **JSON**：`to_dict()` 向下兼容（v0.2 字段全保留，新增 `regime / axis_readings / divergences / phase`）

---

## 📊 测试覆盖

| 文件 | 旧测试 | v0.3 新增 | 总数 |
|------|--------|-----------|------|
| `test_core.py` | 15 | 0 | 15 |
| `test_generic.py` | 22 | 0 | 22 |
| `test_v03_axes.py` | — | 10 | 10 |
| `test_v03_regime.py` | — | 10 | 10 |
| `test_v03_phase.py` | — | 16 | 16 |
| `test_v03_divergence.py` | — | 9 | 9 |
| **合计** | **37** | **45** | **82** |

```
$ python -m pytest tests/ -q
.................................................................  [ 87%]
..........                                                           [100%]
82 passed in 0.23s
```

---

## 🔄 迁移指南（对 v0.2 使用方）

| 使用方 | 改动 |
|--------|------|
| CLI 调用方 | 无需改动 —— 新增 `--regime` / `--no-regime` 是可选 |
| JSON 消费方 | 无需改动 —— `to_dict()` 向下兼容，新增字段都可选 |
| Python API | 无需改动 —— `score_risk()` 新增 axis_readings/regime 是 keyword-only |
| YAML 配置 | 无需改动 —— 新增 `axes / regime / phase / divergence` 段是可选 |
| 自定义画像 | **可选** —— 新增 `axis_weights / required_axes / phase_overrides / regime_overrides` 字段，旧字段全保留 |

### 新增 JSON 字段示例

```json
{
  "asset_kind": "meme",
  "profile_label": "注意力驱动长尾代币（默认案例）",
  "regime": {"kind": "Bull", "risk_score": 19.2, "confidence": 1.0, ...},
  "axis_readings": {
    "attention": {"level": 52.3, "growth": -0.629, "z_score": -1.26, ...},
    "onchain":   {"level": 82.1, "growth": 0.510, ...},
    "fundamental": {"unavailable": true, "reason": "v0.3 占位：Fundamental 轴待 DeFiLlama/Token Terminal 接入"},
    "macro": {"unavailable": true, "reason": "v0.3 占位：Macro 轴待 FRED/Coinalyze 接入"}
  },
  "divergences": [
    {"name": "Behavior > Attention", "z_gap": 2.28, "severity": "warning", ...},
    {"name": "Price > Liquidity", "z_gap": 2.04, "severity": "warning", ...}
  ],
  "phase": {"primary": "Unknown", "confidence": 0.0, "rule_chain": ["no_rule_matched"], "regime_downgrade_applied": false}
}
```

---

## 📝 文件变更清单

### 新增

```
src/attention_market/core/axes.py            4 轴统一接口
src/attention_market/core/regime.py          Market Regime (6 信号 → 4 档)
src/attention_market/core/divergence.py      跨轴 z-score 背离 (6 类)
src/attention_market/core/phase.py           8 阶段 + Regime 降级
src/attention_market/providers/fundamental.py DeFiLlama + Token Terminal 占位
src/attention_market/providers/macro.py      FRED + Coinalyze 占位
src/attention_market/config/phase_thresholds.yaml  可选阈值覆盖
tests/test_v03_axes.py                       10 测试
tests/test_v03_regime.py                     10 测试
tests/test_v03_phase.py                      16 测试
tests/test_v03_divergence.py                 9 测试
RFC_v0.3.md                                  完整设计规格
RELEASE_v0.3.0.md                            本文件
```

### 修改

```
src/attention_market/core/models.py         新增 SignalAxis/RegimeKind/AxisReading/DivergenceSignal/PhaseTag/RegimeReading
src/attention_market/core/asset.py          re-export SignalAxis
src/attention_market/core/registry.py       AssetProfile 扩展 axis_weights/required_axes/phase_overrides/regime_overrides
src/attention_market/core/pipeline.py       接入 4 轴 → divergence → phase → risk
src/attention_market/core/risk.py           score_risk 接受 axis_readings/regime (keyword-only)
src/attention_market/reporting/console.py   新增 [T]/[Axis]/[D]/[P] 区块
src/attention_market/reporting/html.py      新增 4 个 HTML 卡片
src/attention_market/cli.py                 新增 --regime/--no-regime + regime/axes 子命令
src/attention_market/config/default.yaml    新增 axes/regime/phase/divergence 段
README.md                                   路由图小节替换为 v0.3 摘要
```

---

## ⚠️ 已知限制

- **Fundamental / Macro 轴当前 unavailable**：v0.3.1 接入 DeFiLlama / FRED / Coinalyze 后可用
- **Phase 规则是经验阈值**：需要 v0.3.2 跑回测校准
- **Regime 默认全信号 unavailable**：CLI `--regime` 可手动指定
- **同一标的多次运行时 Phase 可能变化**：依赖 attention.momentum 等瞬时指标

---

## 🙏 致谢

v0.3 在 v0.2 基础上把框架定位从"注意力工具"升级为"Digital Asset Intelligence framework"，核心方法论借鉴了：
- 多因子资产定价中的"宏观/基本面/技术面"分层
- 市场微观结构中的 Phase 划分
- Regime Switching Models 在宏观对冲基金中的实践

---

## 下一步（v0.4 路线图）

- FRED / Coinalyze 真实数据源接入
- DeFiLlama / Token Terminal 接入
- Web Dashboard
- 跨资产回测（≥20 样本校准 Phase 阈值）
- 股票/商品/外汇场景（复用画像机制）

完整 MIT License —— 见 [LICENSE](LICENSE)。