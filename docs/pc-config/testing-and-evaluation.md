# PC 配置测试与评测

| 项 | 内容 |
| --- | --- |
| 状态 | Completed |
| 最后核验 | 2026-11-09 |
| 权威性 | 测试事实记录；命令与门禁以各服务配置及 CI 为准，实测数据来自 [`pc-config-e2e-2026-11.md`](../quality/pc-config-e2e-2026-11.md) |
| 主要证据 | `application-service/src/test/**/pcbuild/**`；`agent-service/tests/test_agent_graph.py`、`test_profiles.py`、`test_persistence.py`；`agent-service/evals/cases/example.yaml`、`pc-config-scenarios.yaml`；`frontend/src/features/chat/**/*.spec.*` |
| 关联 | 测试矩阵与业务指标见 [`pc-config-implementation-plan.md`](../planning/pc-config-implementation-plan.md) §8 |

## 1. 分层与门禁

| 层 | 范围 | 命令 | 门禁 / 实测 |
| --- | --- | --- | --- |
| Java 单测与接口测试 | `application-service/src/test/java/com/example/agent/pcbuild/**` | `cd application-service; .\mvnw.cmd -q verify` | 0 失败；实测 51 个测试类、403 用例全部 `Failures: 0, Errors: 0` |
| Agent 单测 | `agent-service/tests/**` | `uv --directory agent-service run ruff check app tests evals run.py`、`mypy`、`pytest -q --cov=app` | 覆盖率阈值 90%；实测 544 用例、92.34% |
| 前端 Vitest | `frontend/src/**/*.spec.*` | `corepack pnpm --dir frontend lint:ci`、`type-check`、`test:coverage` | lint/type-check 全通过；实测 74 文件、497 用例、行覆盖 92.8% |
| 前端 E2E（Playwright） | `frontend` 关键路径 | `corepack pnpm --dir frontend e2e:critical` | 本次未运行；沿用既有基线，PC 路径改由 Stage 5 HTTP/SSE 联调覆盖 |
| Stage 5 端到端（HTTP/SSE） | 三组自然语言输入 | 见 [`pc-config-e2e-2026-11.md`](../quality/pc-config-e2e-2026-11.md) | 通过：预算可行 / 预算不可行 / 缺信息追问，无 `error` 事件 |

> Java 核心 service 覆盖率建议 ≥ 70%（仓库规则建议值）；本次联调报告只断言 surefire 0 失败，未单列 Java 覆盖率数字。

## 2. Java PC 测试类与覆盖点

| 测试类 | 覆盖点 |
| --- | --- |
| `PcBuildApiTests` | 服务令牌 401；候选非空、未知类别 400；硬件详情 404 `40301`；跑分非空；报价 `MIXED_DEMO`、`CNY_FEN`、含核验价与演示价；validate 9 条规则且机箱限高为 `UNKNOWN`；缺类别 400；solve 落库并可回读；越权读取 `40302`；缺 `X-User-Token` `40306`；预算不足结构化失败；`requireVerifiedOffers` 不用演示价 |
| `BuildSolverTests` | 相同输入确定性一致；预算为硬上限（最低可行价、最低价 -1）；无预算走性价比；仅核验价时报告缺失类别；内存/存储下限过滤；`cooler_case_height=UNKNOWN` 不当作 `PASS`；八类各一条报价；`GENERAL` 结果与改造前一致；`AI_INFERENCE` 优先高显存、`PROGRAMMING` 优先多核；`RENDERING` 在 `renderMode=CPU/GPU` 下权重不同 |
| `CompatibilityValidatorTests` | 9 条规则基线；插槽、内存类型、板型、显卡长度、散热器插槽、散热限高、供电、M.2、内存条数各类失败；缺参数返回 `UNKNOWN`；空选择全部 `UNKNOWN`；检查顺序固定；每条结论 `riskLevel=BLOCKING`；`ruleVersion=pc-compat-2.0.0` |
| `BuildSnapshotPersistenceTests` | 所属用户可读回 8 个组件与兼容性报告；其他用户读取 `40302`；不存在的快照同样 `40302`；`requirements_snapshot` 含 `workloadProfile`、`renderMode`、`scoringVersion` |
| `PcFixtureRepositoryTests` | 分类计数之和等于目录总数；机箱 `maxCoolerHeightMm` 为 null；跑分非空；报价含核验价与演示价且演示价 `verifiedPrice=false`；报价在当日均可用 |

## 3. Agent 测试与评测

| 文件 | 覆盖点 |
| --- | --- |
| `tests/test_agent_graph.py` | 图恰好六个节点；澄清路径跳过检索；成功路径渲染确定性 Markdown 并产出 `build_result`；理由含数字被拒；无候选；上游错误；无解保持预算硬约束；校验失败重解一次后成功；重解后仍失败；校验上游故障保留方案并标 `UNKNOWN`；无模型时降级解析；运行时对象不落状态；用量上报；模型配置缺失时仍装配 PC 图 |
| `tests/test_profiles.py` | 默认 Profile 为 `pc-config` 且绑定五个 PC 工具；未知 Profile 报错；新增 YAML 可被发现；内置 Profile 仅 `pc-config`；`id` 必须与文件名一致 |
| `tests/test_persistence.py` | 以 `PCConfigState` 做 checkpointer 往返；未启用 Postgres 时 `pytest.skip`，不伪造通过 |
| `tests/test_hitl.py` | HITL 门控：开启必须配 postgres 后端；未开启时澄清仍走原路径；澄清中断 → 恢复后完成求解且补充信息并入同一条用户消息；空答案被拒；未知兼容性中断可终止；图重建（等价进程重启）后中断仍可恢复；恢复请求校验（禁用 / 内存后端 / 无中断 / ID 不匹配 / 过期） |
| `tests/test_hitl_postgres.py` | 真实 Postgres 重启演练：触发中断后丢弃连接池与图，用全新连接池 + 新图从 checkpoint 恢复并完成求解；未设 `AGENT_TEST_POSTGRES_URL` 时跳过 |

`test_hitl_postgres.py` 需要真实库，本地这样跑（连接串 host 用 IPv4 字面量，原因见该文件模块注释）：

```powershell
$env:AGENT_TEST_POSTGRES_URL = "postgresql://agent:<password>@127.0.0.1:15433/agent_service"
uv --directory agent-service run pytest tests/test_hitl_postgres.py -q
```

评测用例位于 `agent-service/evals/cases/`：`example.yaml` 是格式样板，`pc-config-scenarios.yaml` 覆盖 Stage 11 §4.2 的十类场景。

| 断言 | 语义 | 校验模式 |
| --- | --- | --- |
| `tool_called` | 本轮调用过指定工具 | `--fake` |
| `tool_sequence` | 指定工具按顺序出现（子序列，允许中间插入检索等辅助工具） | `--fake` 只校验已注册且被 Profile 绑定 |
| `workflow_status` | 图最终状态；给列表时任一命中即通过 | `--real` |
| `missing_slots` | `requirements` 与 `validation_result` 的 `missing_fields` 并集包含期望槽位 | `--real` |
| `structured_fields` | 按点路径读取最终状态并与期望值严格比对（bool / 数字 / 字符串不互认） | `--real` |
| `price_consistency` | 分项 `priceFen` 合计等于 `totalPriceFen`，且不超 `budgetMaxFen` | `--real` |
| `must_contain` / `must_not_contain` | 回答中出现 / 不出现指定片段 | `--real` |
| `max_latency_ms` / `max_tokens` | 单条用例（含多轮）的耗时与 token 预算；Provider 未返回 usage 时记 `skipped` | `--real` |

`turns` 字段让同一用例在同一 `thread_id` 上追加轮次，用于「改预算 / 补槽位」等多轮场景。

> 假模型模式只校验结构与 Profile 绑定，状态与内容断言一律如实记为 `skipped`；真实模型校验用 `python -m evals --real`。按 U-03 结论，CI 只跑 `--fake`，`--real` 由本地手动执行并与基线对比。

### 3.1 反馈到评测用例（人工确认后入集）

用户「踩」是最贴近真实失败样本的来源，但不能自动变成带断言的用例：

1. 管理端「用户反馈」页按评分/原因/时间筛选后「导出 CSV」（`MessageFeedbackService.exportCsv`，最多 10000 行）。
2. 在仓库根执行：

```powershell
uv --directory agent-service run python scripts/feedback/export_eval_cases.py <feedback-*.csv>
```

脚本只处理「踩」，用 `消息ID`（`{thread_id}:{seq}`）到 Agent 库 `session_messages` 取同一会话中该助手消息之前最近的一条用户消息作为 `input`，输出到 `agent-service/evals/cases-pending/`，并在终端汇总「无会话正文 / 输入过长 / 消息ID非法」的跳过数。

3. **必须人工补全 `expect`**（草稿里固定写 `expect: {}` 并标记 TODO），确认后移动到 `agent-service/evals/cases/` 才会被 `python -m evals` 加载。

之所以不直接写进 `cases/`：`evals/schema.py` 要求 `expect` 至少一项真实断言，自动填充等于编造期望，会让评测集悄悄失效。`cases-pending/` 不参与加载与门禁。

## 4. 前端测试

| 文件 | 覆盖点 |
| --- | --- |
| `components/build-result-card.spec.tsx`（11 例） | 硬件明细/总价/预算/理由/购买链接；`MOCK_DEMO` 顶部横幅与行内标识；仅凭正文提示也显示横幅；`UNKNOWN` 虚线弱化且不使用成功色；无链接占位；缺失型号占位行；数据完整性与价格免责声明常驻；用途标签；`UNKNOWN+BLOCKING` 显示「待核验」；新增字段缺失时仍正常渲染 |
| `runtime/build-result-cache.spec.ts`（5 例） | 同会话同正文命中；正文或会话不同不命中；`forget` 后失效；容量淘汰最早会话；历史映射把缓存卡片挂回同一助手消息 |
| `runtime/agent-runtime.spec.ts` | `done` 携带 `build_result` 时挂到当前助手消息且畸形数据不阻断；`build_result` 结构异常时按普通回答完成、不回填卡片 |

## 5. E2E 证据

- 报告：[`pc-config-e2e-2026-11.md`](../quality/pc-config-e2e-2026-11.md)。
- 三组用例：预算可行（`tool_call=13`、`tool_result=13`、`token=1`、`done=1`，含 `build_result`）；预算不可行（12/12/1/1，无 `build_result`，明确不放宽预算）；缺关键信息（`token=1`、`done=1`）。三组均无 `error`。
- 接口侧核对：`solve` 15000 元成功、3000 元返回 `BUDGET_EXCEEDED`、`video_editing` 归一化为 `CREATIVE`、非法场景 400、快照回读 8 个组件、缺用户令牌 401 `40306`。

## 6. 已知未覆盖项

- 【部分实现】真实数据 E2E：运行时目录 **402** 款、报价 **402** 条（2026-11-12 实测，`data_status=PLATFORM_OBSERVED_ONLY`）。已消除演示价与孤儿报价，但 159 条价格为规格档位/榜单估算，仍无人工逐件核验价；在人工核验收口前，任何“真实市场配置已通过”的表述都不成立。见 [roadmap](../planning/roadmap.md) §5.4。
- 【已采集】求解性能基线由 `BuildSolverBenchmarkTests` 采集（候选数、评估组合数、中位/P95 耗时），断言只校验确定性的计数，不断言耗时以免 CI 抖动。数字见 [Stage 10 质量报告 §5](../quality/pc-config-stage-10-report.md)。
- 【部分实现】浏览器视觉回归：`frontend/e2e/build-visual.spec.ts` 已用断言锁定八件配置、演示价提示、无解回退与 HITL 表单四组界面，并留存截图；仍缺像素级截图对比、跨浏览器与窄屏人工验收。
- 【未实现】性能压测（并发求解、SSE 长连接、快照表增长）。
- 【未实现】真实模型评测的 CI 门禁；当前仅 `--fake` 校验工具绑定，语义断言需人工 `--real`。
- 【未实现】Java 覆盖率数字门禁；现有报告只保证测试全绿。
