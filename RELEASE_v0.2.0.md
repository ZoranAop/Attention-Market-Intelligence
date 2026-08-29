# v0.2.0 — 通用化版本：从 MEME 框架到 UFAM

**发布日期**: 2026-08-29
**标签**: `v0.2.0`
**测试**: 37/37 通过（15 个原版 + 22 个新增）

---

## 核心变更

本版本将框架从「MEME 币专用」重构为**通用金融资产生成式分析框架（UFAM）**。
新增**资产类型 + 画像**抽象层，让门控与风险按资产类型分流。

**最关键的改变**：MEME 币从「框架默认场景」降级为「众多资产类型中的一个具体案例」。

---

## ✨ 新增功能

### 1. 资产类型分类器（`core/asset.py`）

新增 `AssetKind` 枚举，包含 6 种资产类型：

| 类型 | 说明 |
|---|---|
| `MEME` | 注意力驱动长尾代币（默认案例） |
| `STABLECOIN` | 名义锚定稳定币（USDT/USDC/DAI） |
| `L1` | 原生 Layer-1 资产（BTC/ETH/SOL） |
| `DEFI` | DeFi 协议代币（UNI/AAVE/CRV） |
| `SECURITY` | 证券类（RWA / 现金流定价） |
| `UNKNOWN` | 无法判定（最保守处理） |

`classify_asset(signals, whitelist)` 按白名单优先级判定类型。

### 2. 画像注册表（`core/registry.py`）

新增 `AssetProfile` 数据类 + `register_profile()` API：

- 每种类型一套画像（含 signals / gate_enabled / risk_weights / risk_bands / sources / note）
- 通过 `get_profile(kind)` 调度
- `register_profile()` 扩展机制——新增资产类型无需改核心代码

### 3. 门控按类型分流（`core/gate.py`）

- `MEME` / `DeFi` / `UNKNOWN`：完整合约门控
- `Stablecoin` / `L1` / `Security`：跳过合约门控，由该类型专属口径接管

### 4. 风险口径参数化 + 脱锚防御（`core/risk.py`）

- 风险分项权重 = 画像 > config > 默认
- 稳定币新增**脱锚**分项（核心）+ **发行方/储备**分项
- L1 新增**波动率**分项
- DeFi 预留**基本面**分项
- **脱锚可信度防御**：极端脱锚（>20%）且池子/成交极小 → 标"疑似数据源错误"，不污染总分

### 5. 白名单配置（`config/assets.whitelist`）

YAML 格式的资产白名单，可独立覆盖而不改代码。

---

## 🐛 修复的真实问题

| 资产 | v0.1 行为 | v0.2 修复 | 测试覆盖 |
|---|---|---|---|
| **USDC** | 风险 48/100（误判） | 风险 25/100（低） | `test_risk_stablecoin_uses_depeg_not_mc_ratio` |
| **USDT**（极端脱锚） | 风险 55/100（误判"高"） | 脱锚防御触发，标"需人工复核" | `test_risk_stablecoin_depeg_defense` |
| **BTC**（ETH 链） | 门控通过（解析到同名 ERC-20） | L1 画像绕过合约门控 | `test_gate_l1_skips_contract_gate` |
| **UNI** | 走 MEME 口径（缺基本面） | 走 DeFi 画像（门控+基本面） | `test_classify_defi` |

---

## 📊 测试覆盖

```
tests/test_core.py     原版 15 项（无修改即通过）✅
tests/test_generic.py  新增 22 项（v0.2 通用化）✅
─────────────────────
总计                   37/37 通过 ✅
```

新增测试覆盖：
- 资产分类（稳定币/L1/DeFi/MEME/UNKNOWN/优先级）
- 画像注册与覆盖（含 override 防误覆盖）
- 门控按类型分流（4 种场景）
- 风险口径参数化（5 种场景）
- 脱锚防御（极端 + 防御 + 严重脱锚）
- 离线 demo 完整性
- 优先级链（画像 > config > 默认）
- 向后兼容（无 profile 调用）

---

## 🔄 迁移指南

**v0.2 是完全向后兼容的**。所有 v0.1 调用无需任何修改即可继续工作。

| 使用方 | 是否需要改动 |
|---|---|
| 旧 CLI 调用方（`analyze "PEPE"`） | ❌ 无需——输出多 `asset_kind` 字段，其他不变 |
| 旧 JSON 消费方 | ❌ 无需——旧字段全保留，新增 `asset_kind` / `profile_label` |
| 旧 Python API 调用方 | ⚙️ 可选——不传 profile 即保持 v0.1 行为，传 profile 启用新功能 |
| 旧配置文件 | ❌ 无需——白名单通过 `config/assets.whitelist` 单独管理 |

### JSON 报告新字段（向下兼容）

```json
{
  "asset_kind": "stablecoin",            // 新增
  "profile_label": "稳定币（名义锚定）",  // 新增
  "risk": {
    "score": 25,
    "level": "低",
    "components": {...},                 // 因画像而异
    "drivers": [...],
    "asset_kind": "stablecoin",          // 新增
    "profile_label": "稳定币（名义锚定）"  // 新增
  }
}
```

---

## 📝 文件变更清单

```
新增  src/attention_market/core/asset.py        资产分类器 + AssetKind 枚举
新增  src/attention_market/core/registry.py     AssetProfile 注册表
新增  config/assets.whitelist                  白名单配置
新增  tests/test_generic.py                    通用化测试（22 项）

修改  src/attention_market/core/gate.py        门控按画像分流
修改  src/attention_market/core/risk.py        风险口径参数化 + 脱锚防御
修改  src/attention_market/core/models.py      AnalysisResult 新增字段
修改  src/attention_market/core/pipeline.py    主流程接入画像
修改  src/attention_market/core/__init__.py    导出新模块
修改  pyproject.toml                           版本号 0.1.0 → 0.2.0
修改  README.md                                加入 v0.2 通用化说明
```

---

## ⚠️ 已知限制

1. **稳定币候选池选择** —— DexScreener 多个池子时按流动性选，应优先选"最接近锚定价"（v0.3 计划）
2. **L1 价格/流动性** —— DexScreener 覆盖有限，需 CoinGecko 接入（v0.3 计划）
3. **issuer_reserve 状态** —— pipeline 当前默认 `partial`，需实际核验（v0.3 计划）
4. **跨资产类型回测** —— 仅有 MEME 币的等价回测（v0.3 计划）

详见 README 第十二节。

---

## 🙏 致谢

本版本遵循"诚实标注"原则——所有改动都附带真实数据验证与测试覆盖。
UFAM 不是"理论架构"，是**已经能在 PEPE / USDC / USDT 上跑出合理结论**的可用框架。

---

## 下一步（v0.3 路线图）

- 接入 DeFiLlama（TVL）+ Token Terminal（收入）→ D2 估值锚落地
- 接入 CoinGecko（币种元数据）→ 改进 L1 候选池选择
- 接入 FRED（利率/DXY）→ D6 宏观基础
- 跨资产类型回测（20+ 样本）
- 报告展示层优化

完整 MIT License——见 [LICENSE](LICENSE)。
