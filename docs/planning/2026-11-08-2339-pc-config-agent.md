# Handoff: pc-config-agent

2026-11-08 23:39 +08:00 · agent-project-template-main / `feature/pc-config-agent` · Agent: Trae (DeepSeek-V4.1-Flash)

## Unfinished Tasks

1. [pending] 提交改动到 git — 工作区共 90 项变更（56 修改 / 8 删除 / 26 新增）全部未提交，需按「一次提交只做一件事」拆分：数据与脚本、Java `pcbuild`、Agent 单图重构、前端卡片、根文档与 `docs/pc-config`。
2. [pending] P0-01 用真实核验价替换 18 条 `MOCK_DEMO` 报价 — 京东采集限流中断，`offers.json` 中 18 条为虚拟价。
3. [pending] P0-02 机箱目录补 `max_cooler_height_mm` — 缺失导致 `cooler_case_height` 恒为 `UNKNOWN`。
4. [pending] P1-01 入门/高端候选扩充 — 当前 28 款在 3000 元以下与高端区间无解。
5. [pending] P1-02 快照保留策略 — 本期只增不删，`pc_build_snapshots` 无清理机制。
6. [pending] P1-03 浏览器视觉验收 — Playwright `e2e:critical` 本次未运行。
7. [pending] P2-01/P2-02 真实模型评测 CI 门禁、性能压测。

## Goal

基于 Monorepo Agent 模板二次开发「基于 LLM 的 PC 配置智能推荐 Agent」：把模板原有的通用聊天工作流**整体替换**为 PC 专用确定性单图流水线（不允许两套并行），由 Java 承担硬件目录、跑分、报价、求解、兼容性与快照的权威计算。

## Done

- **Stage 1 数据**：`application-service/src/main/resources/pc-config/{catalog.json,benchmarks.json,offers.json}`——28 款硬件（CPU/GPU/主板/内存各 4、存储/散热/机箱/电源各 3）、28 条报价（10 `OWNER_VERIFIED` + 18 `MOCK_DEMO`，`dataStatus=MIXED_DEMO`）、8 条聚合跑分；采集脚本 `scripts/pc-config/ingest_offers.py`；录入模板 `docs/pc-config/offers.template.json`。
- **Stage 2 Java**：`application-service/src/main/java/com/example/agent/pcbuild/**`——7 个 `/internal/v1/pc/**` 接口、`BuildSolver`（整数分计算、预算硬上限）、8 条兼容规则、快照落库（`V24__create_pc_build_snapshots.sql`）；`mvnw verify` 50 个 surefire 报告 0 失败。
- **Stage 3 Agent**：`agent-service/app/agent/pc/**` + `app/agent/graph.py` 单图六节点（`requirement_parser → requirement_validator → candidate_retriever → build_solver → build_validator → response_generator`）；`app/agents/pc-config.yaml` 绑定 5 个 PC 工具；3 份提示词；`app/services/turn.py` 把节点 `tool_events` 映射为 SSE；pytest 504 用例 / 92.23%。
- **Stage 4 前端**：`frontend/src/features/chat/components/build-result-card.tsx`、`runtime/build-result-cache.ts`、`features/sessions/api/build-result.ts`；74 个测试文件 / 483 用例 / 行覆盖 92.64%。
- **Stage 5 端到端**：报告 `docs/quality/pc-config-e2e-2026-11.md`——15000 元 GAMING 成功（total 1,464,200 分、13 次工具调用）、3000 元无解不放宽、缺信息只追问；Java 7 接口与错误码 40301–40306 全部核对通过。
- **Stage 6 文档**：`docs/pc-config/` 14 份文档；根文档同步（`docs/README.md`、`docs/INDEX.md`、`docs/architecture-overview.md`、两份 service api-reference、`docs/services/agent-service/agent-workflows.md`、`docs/deployment/environment-variables.md`）；新建 [closure-plan.md](closure-plan.md) 修复 R7 断链；`scripts/check-env-docs.ps1` 改为手写目录遍历，避开 `node_modules` 断裂 junction。
- **门禁**：`check-doc-links.ps1` → 142 份 markdown 无断链；`check-env-docs.ps1` → 60 份文档 / 154 个变量全部在 `*.env.example` 中声明。

## In Progress / Next

下一步二选一，建议先确认提交策略再动数据：

- 若要落盘当前成果：按上文 5 个粒度拆分 commit（参考 `.trae/rules/00-monorepo-common.md` §4 提交格式）。
- 若要继续功能：先做 P0-01（真实报价替换），因为 P0-02 与 P1-01 都会改动 `catalog.json`，一起做可减少重复联调。

## Key Files & Paths

- `docs/planning/pc-config-implementation-plan.md` — 六阶段任务、验收指标与业务口径（SSOT）。
- `docs/planning/closure-plan.md` — 放行条件 G-01–G-05、剩余 P0/P1/P2 清单、R1–R7 关闭依据。
- `docs/quality/pc-config-e2e-2026-11.md` — Stage 5 联调证据与指标实测值。
- `docs/pc-config/` — 模块文档集；入口 `README.md`，术语 `glossary.md`，契约索引 `api-contract.md`。
- `docs/api-contract.md` §5.7、§7 — PC 内部接口与 `done.build_result` 的最终契约。
- `agent-service/app/agent/pc/{nodes.py,schemas.py,renderer.py,state.py}` — 六节点实现、状态模型与前端载荷投影。
- `agent-service/app/services/turn.py` — `tool_events` → `tool_call` / `tool_result` → `done` 的唯一映射点。
- `agent-service/app/services/pc_client.py` — Agent 调用 Java 内部接口的客户端（服务令牌 + `X-User-Token`）。
- `application-service/src/main/java/com/example/agent/pcbuild/` — solver / validator / snapshot 与 7 个 Controller。
- `frontend/src/features/sessions/api/build-result.ts` — `build_result` 解析器（容忍 snake_case 与 camelCase）。
- `scripts/dev/start-local.ps1`、`scripts/dev/stop-local.ps1` — 本地三端启动/停止。
- `docs/adr/0009`–`0012` — 单图替换、确定性 Markdown、人工核验报价、快照持久化四项决策。

## Decisions & Gotchas

- **单图替换，不是并行**：模板原有的 `memory.py`、`state.py`、`tools.py`、`prompts/default.md`、`prompts/writer.md`、`agents/default.yaml`、`agents/examples/writer.yaml`、`tests/test_memory.py` 已删除，**不要恢复**。
- **Profile 只有两层**：`request.agent_id` > `AGENT__DEFAULT_PROFILE`（默认 `pc-config`）；未知 `agent_id` 直接 404，无第三层 `default` 兜底。
- **职责边界**：Java 是候选、跑分、报价、求解、兼容性、快照的唯一权威；金额一律 `long` 分（`CNY_FEN`）；Agent 只编排与渲染。
- **数据诚信红线**：`MOCK_DEMO` 报价不得表述为已核验；兼容性 `UNKNOWN` 不得展示为 `PASS`；无解时不得自行放宽预算。
- **重解策略**：兼容性失败最多重解 1 次（`AGENT__MAX_SOLVE_RETRIES`，默认 1），且只放宽 `requireVerifiedOffers`，不动预算。
- **本地端口不是默认值**：Java 18080、Agent 18000、前端 5273（由 `scripts/dev/start-local.ps1` 指定），不是 8080/8000/5173。
- **后台进程存活**：用 `start` 方式启动的进程在本会话命令结束后会被回收；需用后台常驻方式逐个启动，日志在临时目录。
- **PowerShell 5.1 编码**：含中文的 `.ps1` 必须存为 UTF-8 **带 BOM**，否则按 ANSI 解析报 `} in expression`。
- **演示账号**：本地 `.env` 的 `AUTH_DEMO_PASSWORD` 为空时 `demo` 账号不会创建（日志 `引导账号未配置口令，跳过创建`），联调改用 `AUTH_ADMIN_USERNAME/AUTH_ADMIN_PASSWORD`。
- **采集限流**：京东连续约 15 次搜索后触发限流，未绕过；剩余 16 条直接写入虚拟价，已在文档中标注。
- **改 `VITE_*`、源码或 Dockerfile 必须重建镜像**；只改运行时环境变量不需要。

**Skills.** 继续做数据替换时可参考 `TRAE-browseruse`（浏览器采集）；提交前如需审查可用 `TRAE-code-review`。

## How to Verify

```powershell
# 文档门禁（Stage 6 交付物，必须为 0）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-doc-links.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-env-docs.ps1

# Agent
uv --directory agent-service sync --frozen
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake

# Java
cd application-service; .\mvnw.cmd -q verify

# 前端
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage
corepack pnpm --dir frontend e2e:critical   # 本次未运行
```

端到端人工复验：启动三端后，用管理员账号登录，输入「预算 15000 元，主要玩 3A 游戏」应返回 8 件配置与 `build_result` 卡片；输入「预算 3000 元」应明确告知无解且不放宽预算。
