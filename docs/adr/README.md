# 架构决策记录（ADR）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-11 |
| 权威性 | 本文件是 `docs/adr/` 的索引；决策内容以各 ADR 正文为准，阶段状态与遗留问题见 [roadmap](../planning/roadmap.md) |
| 编号约定 | 四位递增；已合并或废弃的编号不复用，历史由 Git 保留 |

## 1. 现行 ADR

| 编号 | 标题 | 范围 |
| --- | --- | --- |
| [0001](./0001-frontend-direct-to-agent.md) | 前端经 Nginx 直连 Agent，Java 不代理 SSE | 模板 |
| [0004](./0004-extension-config-file-first.md) | 模板扩展配置采用文件优先 | 模板 |
| [0005](./0005-agent-profile-first-class.md) | Agent Profile 是模板的一等扩展点 | 模板 |
| [0006](./0006-mechanism-vs-content-boundary.md) | 模板给机制，接入方给内容 | 模板 |
| [0007](./0007-session-store-seam.md) | 会话读写收口到单一 SessionStore seam | 模板 |
| [0008](./0008-unified-model-egress-litellm.md) | 唯一模型出口收敛到 LiteLLM | 模板 |
| [0027](./0027-pc-config-decisions.md) | PC 配置模块决策合并记录 | PC 配置 |
| [0028](./0028-llm-led-build-selection.md) | 选型决策权迁移到 LLM，Java 保留事实与验证权威 | PC 配置 |
| [0029](./0029-stage1-quality-gate-baseline-alternative.md) | Stage 1 质量门槛以可复算指标替代不可复现的求解器基线对比 | PC 配置 |
| [0030](./0030-multi-agent-call-budget.md) | 复杂场景单轮 LLM 调用上限放宽到 7 次，简单路径保持 5 次 | PC 配置 |

## 2. 合并与空缺说明

- PC 配置模块的决策（原 0009–0026）已合并为 [0027](./0027-pc-config-decisions.md)，各节标题保留原编号，便于从 Git 历史追溯。
- 空缺编号（含 0002、0003）与原 PC 决策文件均不再单独维护；编号不复用。
- 新增 PC 决策优先以新 ADR 记录并回链 0027；模板类决策继续单独成文。

## 3. 维护规则

- 一个 ADR 只做一个决策，包含背景、决策、替代方案与后果。
- 决策被取代时新增 ADR，并在新旧两处互相标注；不直接改写已生效的决策正文。
- 涉及运行时契约的决策必须同步 [api-contract.md](../api-contract.md)、Agent Schema、前端类型与测试。
- 实测偏差登记到 [roadmap §8](../planning/roadmap.md)，不通过修改 ADR 描述掩盖。
