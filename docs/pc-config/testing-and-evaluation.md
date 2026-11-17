# PC 配置测试与评测

| 项 | 内容 |
| --- | --- |
| 适用范围 | PC 配置模块的 Java / Agent / 前端测试与评测命令、用例语义 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文记录测试入口与断言语义；实际结果以各服务命令输出与 CI 为准 |
| 主要证据 | `application-service/src/test/java/com/example/agent/pcbuild/**`、`agent-service/tests/**`、`agent-service/evals/**`、`frontend/src/features/**/*.spec.*` |

## 1. 结论先行

- 单元与接口测试按服务分层执行，命令见 §2；本文不粘贴历史通过数，避免与当前分支漂移。
- Agent 评测在 `agent-service/evals/`：`--fake` 只校验 Profile、工具绑定与图结构；`--real` 才校验状态、字段与内容。
- 真实模式命令是 `python -m evals --real`，会产生真实 token 费用，默认不进 CI 门禁。
- 旧求解器的评测数字与用例已不代表现状，不得引用。

## 2. 命令

```powershell
# Java
cd application-service; .\mvnw.cmd -q verify

# Agent 静态检查与单测
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing

# Agent 评测
uv --directory agent-service run python -m evals --fake
uv --directory agent-service run python -m evals --real

# 前端
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage
corepack pnpm --dir frontend e2e:critical
```

## 3. Java 测试重点

| 测试类 | 覆盖点 |
| --- | --- |
| `PcBuildApiTests` | 服务令牌鉴权、候选/详情/跑分/报价接口、`compose` 落库与回读、`validate` / `validate-partial`、缺令牌与越权错误码 |
| `BuildSolveServiceTests` | `compose` 取最低有效价、硬冲突拒绝、超预算拒绝、失败不落库；`validate` / `validate-partial` 规则子集 |
| `CompatibilityValidatorTests` | 9 条规则 PASS/FAIL/UNKNOWN、字段缺失、规则顺序、`riskLevel=BLOCKING`、`ruleVersion=pc-compat-2.0.0` |
| `BuildSnapshotPersistenceTests` | 所属用户可读回、他人读取 `40302`、快照字段完整 |
| `PcCandidateAndPartialValidateTests` | 候选字段、`priceFen`、`missingFields`、部分校验只返回已执行规则 |
| `PcFixtureRepositoryTests` | 目录/报价/跑分计数一致、报价全部可解析、`data_status=PLATFORM_OBSERVED_ONLY` |

## 4. Agent 测试重点

| 文件 | 覆盖点 |
| --- | --- |
| `tests/test_agent_graph.py` | 图节点与路由、澄清跳过检索、成功路径渲染、失败文案、模型不可用兜底 |
| `tests/test_pc_architect.py` | LLM 提案 Schema、候选外 ID 拒绝、修正次数上限、`compose` 失败映射、不可修正失败 |
| `tests/test_pc_strategy.py` | 策略模型输出、默认策略与 `strategy_source=DEFAULT` |
| `tests/test_pc_quality.py` | CPU/GPU 档位、办公显卡上限、预算下限提示、重选上限 |
| `tests/test_pc_knowledge.py` | 知识检索引用、配额与空引用降级 |
| `tests/test_hitl.py` | 澄清/兼容性中断与恢复、非法答案、过期与后端约束 |
| `tests/test_tool_governance.py` | 超时、重试、权限、配额、脱敏与截断 |
| `tests/test_output_guard.py` | 分项与总价一致、预算自洽、非 PASS 不得宣称兼容、模型文案禁含数字/型号/渠道 |

## 5. 评测用例

用例位于 `agent-service/evals/cases/`：

| 文件 | 用途 |
| --- | --- |
| `example.yaml` | 格式样板 |
| `pc-config-scenarios.yaml` | PC 配置多场景回归 |

每条用例的 `expect` 至少写一项，否则加载期直接拒绝。可用断言：

| 断言 | 语义 | 生效模式 |
| --- | --- | --- |
| `tool_called` | 本轮调用过指定工具 | `--fake` 校验已注册且被 Profile 绑定 |
| `tool_sequence` | 工具按顺序出现（子序列） | `--fake` |
| `workflow_status` | 图终态；给列表时任一命中即通过 | `--real` |
| `missing_slots` | `missing_fields` 包含期望槽位 | `--real` |
| `structured_fields` | 按点路径严格比对最终状态 | `--real` |
| `price_consistency` | 分项合计等于总价且不超预算 | `--real` |
| `must_contain` / `must_not_contain` | 回答包含 / 不包含指定片段 | `--real` |
| `interrupt_type` | 在指定 HITL 交互上暂停 | `--real` |
| `max_latency_ms` / `max_tokens` | 单条用例耗时与 token 预算 | `--real` |

`turns` 字段支持同一 `thread_id` 多轮；`resume` 字段支持 HITL 恢复用例。假模型模式无法验证的断言记为 `skipped`，不记为 `passed`。

### 门禁指标

`--real` 报告额外输出七个口径：`p95 时延`、`单轮最大 LLM 调用`、`tokens`、`成本`、`硬约束通过率`、`质量评审通过率`、`修正成功率`。文本报告单独一行展示，`--json` 落在 `metrics` 字段，单条用例还带 `llm_calls`、`cost`、`workflow_status`、`repair_count`、`quality_passed`、`hard_constraint`。

- 调用次数与 token 来自 LangChain 回调，覆盖结构化、文本兜底与流式三条路径；状态消息不带 `usage_metadata` 时以回调为准。
- 成本按 `EVALS__PRICE_INPUT_PER_MILLION` / `EVALS__PRICE_OUTPUT_PER_MILLION`（每百万 token 单价，取自模型目录）折算；未配置时显示「未定价」，不以 0 冒充已核算。
- 硬约束通过率取 `compatibility_report` 的逐条结论：全 PASS 才算通过，出现 `UNKNOWN` 一律计入 UNKNOWN 桶、不算通过；未产出配置的用例不参与分母。
- 质量评审通过率为 [ADR 0029](../adr/0029-stage1-quality-gate-baseline-alternative.md) 的替代口径：`quality_review.issues` 为空且 `retry=false` 才算通过，`quality_passed` 为空的用例（未进入评审）不参与分母。
- 修正成功率只统计 `architect_repair_count > 0` 且 `expects_success=true` 的用例，成功以图终态 `success` 为准；负向用例与未进入修正的用例不参与分母。

### RAG 检索评测

RAG 未启用或检索器构造失败时整组记为 `skipped`、退出码 0，不伪装成通过；单条检索异常只算该条未命中。指标为 `recall@5`（top5 命中任一期望来源）与 `MRR@5`，默认阈值 0.8 / 0.6，未达标退出码 1。

`uv --directory agent-service run python -m evals.rag_eval --cases evals/rag_cases/rag-baseline.yaml`

## 6. 前端测试重点

| 文件 | 覆盖点 |
| --- | --- |
| `build-result-card.spec.tsx` | 8 类明细、总价、预算、理由、链接、价格来源标识、`UNKNOWN` 弱化样式、缺失字段占位 |
| `build-result-cache.spec.ts` | 同会话正文命中、跨会话隔离、淘汰与历史映射 |
| `agent-runtime.spec.ts` | `done.build_result` 挂载、畸形数据不阻断、失败回退 Markdown |
| `frontend/e2e/build-visual.spec.ts` | 八件配置、价格提示、无解回退、HITL 表单的视觉基线 |

## 7. 已知未覆盖

- 真实市场核验价的端到端验证：当前无 `OWNER_VERIFIED`，只能验证平台观测价链路。
- 真实模型评测的 CI 门禁：`--real` 仍需本地手动执行。
- 性能压测（并发 SSE、快照表增长）。
- Java 覆盖率数字门禁：当前只要求测试全绿，未配置 `jacoco check`。

## 8. 相关文档

- Agent 工作流：[agent-workflows.md](../services/agent-service/agent-workflows.md)
- 兼容规则：[compatibility-rules.md](./compatibility-rules.md)
- 数据现状：[data.md](./data.md)
