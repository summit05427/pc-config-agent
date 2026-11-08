# PC 配置测试与评测

| 项 | 内容 |
| --- | --- |
| 状态 | Completed |
| 最后核验 | 2026-11-08 |
| 权威性 | 测试事实记录；命令与门禁以各服务配置及 CI 为准，实测数据来自 [`pc-config-e2e-2026-11.md`](../quality/pc-config-e2e-2026-11.md) |
| 主要证据 | `application-service/src/test/**/pcbuild/**`；`agent-service/tests/test_agent_graph.py`、`test_profiles.py`、`test_persistence.py`；`agent-service/evals/cases/example.yaml`；`frontend/src/features/chat/**/*.spec.*` |
| 关联 | 测试矩阵与业务指标见 [`pc-config-implementation-plan.md`](../planning/pc-config-implementation-plan.md) §8 |

## 1. 分层与门禁

| 层 | 范围 | 命令 | 门禁 / 实测 |
| --- | --- | --- | --- |
| Java 单测与接口测试 | `application-service/src/test/java/com/example/agent/pcbuild/**` | `cd application-service; .\mvnw.cmd -q verify` | 0 失败；实测 50 个 surefire 报告全部 `Failures: 0, Errors: 0` |
| Agent 单测 | `agent-service/tests/**` | `uv --directory agent-service run ruff check app tests evals run.py`、`mypy`、`pytest -q --cov=app` | 覆盖率阈值 90%；实测 504 用例、92.23% |
| 前端 Vitest | `frontend/src/**/*.spec.*` | `corepack pnpm --dir frontend lint:ci`、`type-check`、`test:coverage` | lint/type-check 全通过；实测 74 文件、483 用例、行覆盖 92.64% |
| 前端 E2E（Playwright） | `frontend` 关键路径 | `corepack pnpm --dir frontend e2e:critical` | 本次未运行；沿用既有基线，PC 路径改由 Stage 5 HTTP/SSE 联调覆盖 |
| Stage 5 端到端（HTTP/SSE） | 三组自然语言输入 | 见 [`pc-config-e2e-2026-11.md`](../quality/pc-config-e2e-2026-11.md) | 通过：预算可行 / 预算不可行 / 缺信息追问，无 `error` 事件 |

> Java 核心 service 覆盖率建议 ≥ 70%（仓库规则建议值）；本次联调报告只断言 surefire 0 失败，未单列 Java 覆盖率数字。

## 2. Java PC 测试类与覆盖点

| 测试类 | 覆盖点 |
| --- | --- |
| `PcBuildApiTests` | 服务令牌 401；候选 28 条、GPU 4 条、未知类别 400；硬件详情 404 `40301`；跑分 8 条；报价 `MIXED_DEMO`、`CNY_FEN`、10 条核验 + 18 条演示；validate 8 条规则且机箱限高为 `UNKNOWN`；缺类别 400；solve 落库并可回读；越权读取 `40302`；缺 `X-User-Token` `40306`；预算不足结构化失败；`requireVerifiedOffers` 不用演示价 |
| `BuildSolverTests` | 相同输入确定性一致；预算为硬上限（最低可行价、最低价 -1）；无预算走性价比；仅核验价时报告缺失类别；内存/存储下限过滤；`cooler_case_height=UNKNOWN` 不当作 `PASS`；八类各一条报价 |
| `CompatibilityValidatorTests` | 8 条规则基线；插槽、内存类型、板型、显卡长度、散热器插槽、散热限高、供电、M.2 各类失败；缺参数返回 `UNKNOWN`；空选择全部 `UNKNOWN`；检查顺序固定 |
| `BuildSnapshotPersistenceTests` | 所属用户可读回 8 个组件与兼容性报告；其他用户读取 `40302`；不存在的快照同样 `40302` |
| `PcFixtureRepositoryTests` | 目录 28 条且分类计数固定；机箱 `maxCoolerHeightMm` 为 null；跑分 8 条；报价 28 条、10 核验 + 18 演示且演示价 `verifiedPrice=false`；报价在当日均可用 |

## 3. Agent 测试与评测

| 文件 | 覆盖点 |
| --- | --- |
| `tests/test_agent_graph.py` | 图恰好六个节点；澄清路径跳过检索；成功路径渲染确定性 Markdown 并产出 `build_result`；理由含数字被拒；无候选；上游错误；无解保持预算硬约束；校验失败重解一次后成功；重解后仍失败；校验上游故障保留方案并标 `UNKNOWN`；无模型时降级解析；运行时对象不落状态；用量上报；模型配置缺失时仍装配 PC 图 |
| `tests/test_profiles.py` | 默认 Profile 为 `pc-config` 且绑定五个 PC 工具；未知 Profile 报错；新增 YAML 可被发现；内置 Profile 仅 `pc-config`；`id` 必须与文件名一致 |
| `tests/test_persistence.py` | 以 `PCConfigState` 做 checkpointer 往返；未启用 Postgres 时 `pytest.skip`，不伪造通过 |

评测用例位于 `agent-service/evals/cases/example.yaml`：

| 用例 | 断言 |
| --- | --- |
| `pc_gaming_budget` | `tool_called: solve_pc_build`；`must_contain: 推荐配置` |
| `pc_missing_budget` | `must_contain: 预算`（缺信息必须追问） |
| `pc_verified_only` | `tool_called: get_verified_offers` |
| `pc_injection` | `must_not_contain: 你是 PC 装机配置助手` |

> `--fake` 只校验 `tool_called` 对应工具是否已注册并被 Profile 绑定；`must_contain` / `must_not_contain` 需 `python -m evals --real` 才真正校验。

## 4. 前端测试

| 文件 | 覆盖点 |
| --- | --- |
| `components/build-result-card.spec.tsx`（7 例） | 硬件明细/总价/预算/理由/购买链接；`MOCK_DEMO` 顶部横幅与行内标识；仅凭正文提示也显示横幅；`UNKNOWN` 虚线弱化且不使用成功色；无链接占位；缺失型号占位行；数据完整性与价格免责声明常驻 |
| `runtime/build-result-cache.spec.ts`（5 例） | 同会话同正文命中；正文或会话不同不命中；`forget` 后失效；容量淘汰最早会话；历史映射把缓存卡片挂回同一助手消息 |
| `runtime/agent-runtime.spec.ts` | `done` 携带 `build_result` 时挂到当前助手消息且畸形数据不阻断；`build_result` 结构异常时按普通回答完成、不回填卡片 |

## 5. E2E 证据

- 报告：[`pc-config-e2e-2026-11.md`](../quality/pc-config-e2e-2026-11.md)。
- 三组用例：预算可行（`tool_call=13`、`tool_result=13`、`token=1`、`done=1`，含 `build_result`）；预算不可行（12/12/1/1，无 `build_result`，明确不放宽预算）；缺关键信息（`token=1`、`done=1`）。三组均无 `error`。
- 接口侧核对：`solve` 15000 元成功、3000 元返回 `BUDGET_EXCEEDED`、`video_editing` 归一化为 `CREATIVE`、非法场景 400、快照回读 8 个组件、缺用户令牌 401 `40306`。

## 6. 已知未覆盖项

- 【未实现】浏览器视觉回归（截图对比、跨浏览器/窄屏人工验收）。
- 【未实现】性能压测（并发求解、SSE 长连接、快照表增长）。
- 【未实现】真实模型评测的 CI 门禁；当前仅 `--fake` 校验工具绑定，语义断言需人工 `--real`。
- 【未实现】Java 覆盖率数字门禁；现有报告只保证测试全绿。
