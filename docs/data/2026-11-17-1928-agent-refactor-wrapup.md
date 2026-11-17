# Handoff: agent-refactor-wrapup

2026-11-17 19:28 +08:00 · agent-project-template / feature/pc-config-data-governance · Agent: TraeCode

## Unfinished Tasks

1. [done] DeepSeek 结构化输出预置跳过 — `llm.py` 按 provider 预置 `deepseek` 不支持 `json_schema`，并保留「400 后学习」兜底；跳过时不再虚记失败用量。
2. [done] RAG 引用质量收尾 — 新增 `RAG__MIN_RELEVANCE_SCORE`（默认 0.2），低分向量命中不展示、精确型号命中豁免；引用 `score` 改为余弦相似度而非 RRF 名次分；`rag-demo` 4/4 命中、`rag-baseline` recall 0.9 / MRR 0.75 达标。
3. [done] citations / reasoning 持久化 — 引用与 `had_reasoning` 写入 `session_messages.metadata`（JSONB），历史接口回放引用并提示「思考仅本回合可见」；思考正文仍不落库。
4. [done] 阶段文案动态化 — 新增 SSE `stage` 事件（`turn.py` 按节点完成推进）；前端 `ChatStage` 映射与文案，reasoning 与阶段指示器并存。
5. [done] 实时正文流式 — `response_generator` 校验通过后按块下发，块间让出事件循环，避免同一帧整段出现（校验前仍不流式）。
6. [done] OpenUI Form 硬约束 — `FormDisabledContext` 在存在待澄清中断时隐藏生成式 Form，避免与 HITL 双入口。
7. [done] 历史会话模型失效回退 — `model_resolver` 在「会话模型不可用且本次未显式选模型」时回退 Auto，请求级显式模型仍原样 403；不复用原幂等键。
8. [done] Critic 受限修正 — `REVISE` + HIGH/MEDIUM 才回 `build_architect`；入口占住剩余修正配额（重提案 + 最多 1 次内部修正），标记消费后清空，最坏路径仍为 9 次调用；LOW 只披露。补齐路由、问题映射与评审矩阵单测。
9. [done] 第二条多 Agent 单例真实验收 — `ma_render_itx` 通过：33.7s、7 次调用、硬约束 100%、质量评审 100%、修正成功率 100%；同时修复评测入口 Windows Proactor 导致 `search_knowledge` 超时的问题。
10. [done] 全量门禁 — Agent `ruff/mypy/pytest`、前端 `type-check/lint/test`、`evals --fake`、`evals.e2e --mode local`（3/3）、`mvnw verify`（426 tests）全部通过。
11. [done] 文档同步 — V27、compose 契约、修正上限、多 Agent 默认值、Critic 修正与阶段事件均已补进交接、阶段、ADR 与接口文档。
12. [deferred] token 用量统计 — 用户决定暂时忽略，后续再实现；当前只有收尾调用能拿到 usage（608/572）。
13. [deferred] 报价核验闭环、真实模型评测门禁 — 演示后迭代。
14. [removed] 多方案对比 / 交互式换件 — 用户决定移出计划，不实现。

## Goal

完成 Agent 重构收尾：把真实主链路暴露的问题修到“合理需求可稳定出单”，并明确剩余任务的优先级与边界，供服务器部署演示。

## Done

- 结构化输出：`agent-service/app/agent/pc/llm.py` 用 `_JSON_SCHEMA_UNSUPPORTED_PROVIDERS={"deepseek"}` 预置跳过，BYOK 占位模型名改由运行时 provider 判断；跳过路径不再记虚假失败用量。
- RAG：`RagSettings.min_relevance_score=0.2`；`fusion.py` 保留向量/关键词原始分，`retriever.py` 用向量阈值过滤、精确词豁免，`Citation.score` 改为余弦相似度（关键词单通道命中时为 null）；`.env.example`、环境变量文档同步。
- 引用持久化：`session_messages.metadata` JSONB 保存 `citations` 与 `had_reasoning`；`turn.py` 收集本轮引用并落库；历史接口回放 `citations` / `had_reasoning`；前端历史映射用 `toCitations` 解析，渲染引用面板并提示「思考过程仅在本回合可见」。
- 文档同步：`docs/api-contract.md`、`docs/deployment/environment-variables.md`（多 Agent 默认值、partial checks 上限）、`docs/services/agent-service/agent-workflows.md`、`docs/planning/pc-config-stage-status.md`。
- 阶段与正文：`turn.py` 新增 `stage` 事件（节点 → 前端枚举），`nodes.py` 正文校验通过后分块下发并让出事件循环；前端 `ChatStage`、阶段文案、reasoning 与指示器并存。
- OpenUI：`FormDisabledContext` 在 HITL 待澄清时隐藏表单；`OpenUiBlock` 新增 `disableForms`，`MessageContent` 透传。
- 模型回退：`model_resolver` 对「会话模型被目录停用且本次未显式选模型」回退 Auto，显式选择仍 403；`docs/model-runtime-architecture.md` §10.3 同步。
- 评测环境：`evals/__main__.py` 在 Windows 切 SelectorEventLoop（Proactor 会让 `search_knowledge` 超时）；`evals/e2e/contract.py` 允许 `stage` 事件。
- 多 Agent 验收：`ma_render_itx` 33.7s / 7 次调用 / 硬约束 100% / 质量 100% / 修正 100%；`mvnw verify` 426 tests 通过。
- Critic 修正：`specialists.py` 输出 `critic_revision_requested`；`graph.py` 路由回 Architect 一次；`nodes.py` 把 HIGH/MEDIUM 问题注入修正提示并占住配额；ADR 0030 与阶段文档同步。
- 验证：Agent `ruff` + `mypy` + 786 passed / 1 skipped；前端 `type-check`、`lint:ci`、80 个测试文件 547 条用例；RAG 冻结题集 4/4、基线 recall 0.9 / MRR 0.75。
- 模型：新增 `application-service/src/main/resources/db/migration/V27__disable_deepseek_v4_pro.sql` 停用 v4-pro，并给 flash 补 `reasoning` / `reasoning_visible`；`deploy/litellm/config.yaml` 只保留 `deepseek:deepseek-flash`；本地 `.env` 设 `MODEL_MANAGED_ENABLED=false`。实测 `/api/v2/models` 只剩 `deepseek:deepseek-flash`，LiteLLM 请求头为 `deepseek/deepseek-flash`。
- 事实链路：`BuildSolveService.composeAndSnapshot` 透传 `budgetMaxFen` + `workloadProfile` 并写入快照；Agent `compose_pc_build` 同步传 `workload_profile`；`docs/api-contract.md` 已同步。
- SSE 去重：`turn.py` 的 messages 流跳过完整 `AIMessage`，修复正文 3 重复。
- 修正策略：`nodes.py` 增加规则级修正提示与预算提示；`ARCHITECT_MAX_REPAIRS` 2→3；`architect_max_partial_checks` 3→4。
- UI：执行轨迹改用业务阶段文案（原始名保留 `title`）；OpenUI 表格图片加载失败回落 `—`；OpenUI 提示词禁止用 Form 收集澄清字段并已重新生成。
- token usage：`_extract_token_usage` 增加 `response_metadata.token_usage` 兜底（上游缺失仍为 None）。
- 多 Agent：`AgentSettings.multi_agent_enabled` 默认改为 `true`，`agent-service/.env.example` 同步。
- 回归：用户原话“预算 8000 / 2K 3A / 偏好 AMD”31.5s 出单，¥7,422、`WITHIN_BUDGET`、`GAMING`、兼容 PASS；浏览器实测 1 张表 8 行、显示 ¥8,000、无“未设置预算”。
- 验证：Agent `ruff/mypy` + 768 passed；Java 相关 5 个测试类；前端 `type-check` + 组件测试 + ESLint。

## In Progress / Next

下一步从“Unfinished Tasks”第 8 项开始：确认 Critic 是否接入受限修正；随后做第 9 项多 Agent 真实验收与第 10 项全量门禁（`mvnw verify`、`evals.e2e --mode local` 尚未跑）。

## Key Files & Paths

- `agent-service/app/agent/pc/nodes.py` — 修正循环、部分校验、修正提示、compose 参数。
- `agent-service/app/agent/pc/llm.py` — 结构化输出 unsupported 集合与 token usage 兜底。
- `agent-service/app/rag/knowledge/{fusion,retriever}.py` — 引用相关性阈值与余弦分。
- `agent-service/app/services/session_store/{postgres,memory,mapping}.py` — 消息元数据（引用 / 思考可见性）。
- `frontend/src/features/chat/runtime/history-messages.ts` — 历史引用与思考可见性回放。
- `agent-service/app/services/turn.py` — SSE 出口与正文去重、`stage` 事件、引用落库。
- `agent-service/app/services/model_resolver.py` — 会话模型失效回退 Auto。
- `frontend/src/features/generative-ui/library/components/form.tsx` — HITL 期间隐藏生成式 Form。
- `agent-service/app/core/config.py` — 多 Agent 默认值、`architect_max_partial_checks`。
- `application-service/src/main/java/com/example/agent/pcbuild/application/BuildSolveService.java` — compose 落快照。
- `application-service/src/main/java/com/example/agent/pcbuild/web/dto/ComposeRequest.java` — 新增 `workloadProfile`。
- `application-service/src/main/resources/db/migration/V27__disable_deepseek_v4_pro.sql` — 模型目录收敛。
- `deploy/litellm/config.yaml` — DeepSeek 仅保留 flash。
- `frontend/src/features/chat/components/execution-trace.tsx` — 轨迹文案映射。
- `frontend/src/features/generative-ui/library/components/table.tsx` — 图片失败回落。
- `docs/adr/0030-multi-agent-call-budget.md` — 复杂场景上限已改为 9。
- `docs/planning/pc-config-stage-status.md` — 未完成项与收尾决策。

## Decisions & Gotchas

- 用户决策：复杂场景允许 ≤9 次 LLM 调用；多 Agent 默认开启；token 统计延后；多方案对比/交互式换件移除；不单独维护演示环境，直接服务器部署。
- 9 次来源：解析 1 + Strategist 1 + Specialist 2 + Architect 首提案 1 + 修正 3 + 收尾 1；实测成功轮为 7 次。
- 演示环境依赖本地 `agent-service/.env`：`AGENT__REQUEST_TIMEOUT_SECONDS=300`（线程锁 TTL 同为 300）、`RAG__ENABLED=true`、`RAG__RETRIEVER_MODULE=app.rag.knowledge.retriever`、`OPENUI__ENABLED=true`、`VITE_OPENUI_ENABLED=true`、`VITE_SHOW_EXECUTION_TRACE=true`；部署时需逐项确认。
- 平台托管密钥探测约 5s 超时会导致首请求 `503 control_plane_unavailable`；本地已用 `MODEL_MANAGED_ENABLED=false` 规避，服务器部署若用托管密钥需调大探测/控制面超时。
- DeepSeek 经 LiteLLM 不支持 `response_format=json_schema`，走文本兜底；Specialist 提示词必须写死 `role` 与英文类别枚举。
- 旧会话保存 `deepseek-v4-pro` 时由 `model_resolver` 回退 Auto；只有请求级显式选择该模型才会 403，演示前无需批量清理历史会话。
- 3D 机箱 WebGL 会让浏览器自动化 `Input.*` CDP 超时；UI 验收优先用新标签页 + `evaluate` 只读检查，或人工点击。

**Skills.** 调试运行时问题用 `TRAE-debugger`；契约变更先读 `docs/api-contract.md`；前端实测用 `TRAE-browseruse`。

## How to Verify

```powershell
# Agent 静态门禁 + 单测
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q tests

# 零费用链路
uv --directory agent-service run python -m evals --fake
uv --directory agent-service run python -m evals.e2e --mode local

# Java / 前端全量门禁
cd application-service; .\mvnw.cmd -q verify
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test

# 真实单例（一次一条，先登录取 token，避免额度耗尽）
$resp = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v1/auth/login' -Method Post -ContentType 'application/json' -Body (@{ username = 'admin'; password = '123456' } | ConvertTo-Json)
$env:EVALS__USER_TOKEN = $resp.data.accessToken
uv --directory agent-service run python -m evals --real --cases evals/acceptance --case-id ma_render_itx
```
