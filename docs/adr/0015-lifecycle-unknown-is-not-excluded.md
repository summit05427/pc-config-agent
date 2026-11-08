# 生命周期分阶段分类，UNKNOWN 不自动等于不可推荐

## 背景

Stage 8 要求给出 `lifecycle_status`、`market_status` 与 `recommendation_status`。但实测数据基础不均衡：PCPartPicker 八张分类表**没有任何发布日期字段**；PassMark 只有 CPU 与 GPU 带 `release_date`，且该字段未逐条核实来源。机箱、散热器、电源、存储、内存、主板无法从现有数据直接推出生命周期。

## 决策

1. 生命周期分类分批推进：先 CPU / GPU（Socket、Chipset 人工代际表 + PassMark 日期佐证），再主板（Socket + Chipset），内存按 DDR 代际、存储按接口代际；散热器、机箱、电源首期允许 `UNKNOWN`。
2. 人工代际表放在 `scripts/pc-config/reference/platform-generations.json`，逐条带来源说明；允许 `manual-overrides.json` 覆盖，覆盖项计入报告。
3. **禁止**用 LLM 记忆或未经核实的推测补全生命周期；无法确定即 `UNKNOWN`。
4. `lifecycle_status=UNKNOWN` 不得自动推导 `recommendation_status=EXCLUDED`。推荐资格按类别分组独立判定：CPU/GPU 以代际为主，散热器/机箱/电源以关键规格完整性为主。
5. 质量报告必须给出八类各自的 UNKNOWN 数量与占比。

## 考虑过的替代方案

- **统一用发布时间阈值判定所有类别**：数据里没有发布日期，只能靠猜测，直接违反"不凭模型记忆补数据"。
- **只分类有数据的 CPU/GPU，其余直接 `EXCLUDED`**：会把大量规格完整、仍可购买现售配件的机箱与电源排除，推荐覆盖面反而变差。
- **引入外部资料补齐发布日期**：属于新一轮采集任务，超出 Stage 8 声明的"不采集"边界。

## 影响

- 首期四类池子的规模由"已分类类别 + 允许 UNKNOWN 的类别"共同决定，报告中的 UNKNOWN 占比是衡量后续治理进度的主指标。
- 推荐资格规则必须按类别编写，不能做成全局单一阈值；规则带 `rule_version`，便于回溯。
- 若后续补充到可靠发布日期，只需扩充代际表与规则，不改变字段契约。
