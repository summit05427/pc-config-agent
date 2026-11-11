# Handoff: pc-config-openui-e2e

2026-11-10 23:35 +08:00 · agent-project-template / 当前工作区分支 · Agent: DeepSeek-V4.1-Flash

## Unfinished Tasks

1. [in_progress] 真实链路端到端实测并记录耗时 — 用本地已启动的 Vite(5273) + Java(18080) + Agent(18000) 跑真实对话，不 mock；覆盖八件配置、预算内/超预算、无解回退、信息不足追问、HITL 中断与恢复；逐阶段记录耗时（需求解析、Java solve、响应生成、首个 SSE 事件、done 总耗时）。
2. [pending] 验证 OpenUI 详情按钮在真实链路可用 — 确认真实 SSE 产出「单表格 + 查看配置详情」两个 OpenUI 块，点击按钮能打开详情弹窗；现有证据仅为单测与 mock SSE 用例，尚未真实链路验证。
3. [pending] HITL 真实触发验证 — 构造缺关键槽位或兼容性待确认的需求，确认 `interrupt` 事件、表单渲染、提交后恢复、提交后旧表单清除；本地已是 `hitl=True + storage=postgres`。
4. [pending] 硬件主流度/代差/兼容性复核 — 核对最终配置是否为主流在售型号（例如 i5-14400、B760M-D4、RTX 4060 是否满足 2026 年预期），记录明显代差与兼容性结论；数据源见 `application-service/src/main/resources/pc-config/catalog.json`。
5. [pending] 汇总实测结论 — 把四项关注点（主流度、代差/兼容性、OpenUI 使用充分度、HITL 触发）与耗时写入 `docs/quality/pc-config-e2e-2026-11.md`。

## Goal

在真实本地链路上验证 PC 配置 Agent 的完整执行链路与 OpenUI 展示效果，重点确认：配置硬件是否主流、是否存在代差与兼容性问题、OpenUI 能力是否充分使用、HITL 是否正常触发，并记录所有任务执行时间。

## Done

- OpenUI 清单改为「八件硬件合并成一张三列表格」，不再一件硬件一个组件，也不再渲染购买按钮：`agent-service/app/agent/pc/openui_renderer.py`（`_list_program`，Table 三列 + 总价 StatGroup）。
- OpenUI 渲染接入生成节点：`agent-service/app/agent/pc/nodes.py:785` 调用 `render_build_openui`。
- 详情按钮链路已实现：DSL 动作 `@OpenBuildDetail()` → 前端动作注册 `frontend/src/features/generative-ui/library/actions/build-detail.ts` → 白名单与分发 `frontend/src/features/generative-ui/library/actions/index.ts` → 宿主回调 `frontend/src/features/chat/components/message-item.tsx:166` → 弹窗 `frontend/src/features/chat/components/build-detail-dialog.tsx`（`sm:max-w-5xl`，内部滚动 `max-h-[74vh]`）。
- 散热器限高策略改为数据缺失默认放行：`application-service/src/main/java/com/example/agent/pcbuild/application/CompatibilityValidator.java:232-237`；前端隐藏该条结论：`frontend/src/features/chat/components/build-compatibility-list.tsx:29-38,51`。
- 登录后永远「没有访问权限」的根因已定位并修复：Vite `/api` 代理原先 `changeOrigin: true` 会把 Host 改成后端主机名，Java 用 Origin 与 Host 判同源，不一致时 `/api` 全部 403；已改为 `changeOrigin: false`，见 `frontend/vite.config.ts:25-31`。
- 已实测当前 Agent 进程有效配置：`openui=True`、`hitl=True`、`storage=postgres`（HITL 开启必须 postgres，校验在 `agent-service/app/core/config.py:471-483`）。

## In Progress / Next

打开 `http://localhost:5273` 登录，新建会话发送一条真实需求（如「预算 10000 元，主打 2K 游戏」），用浏览器 DevTools Network 的 EventStream 记录每个 SSE 事件到达时间，逐项核对：

1. 正文流是否出现「推荐配置清单」单表格，且无购买按钮。
2. 表格下方「查看配置详情」按钮是否可点击，弹窗是否展示兼容性、八件参数、CPU/GPU 跑分、参考价与购买链接。
3. 换一条缺预算或用途的需求，确认 `interrupt` 事件与 HITL 表单；提交后确认恢复且旧表单消失。
4. 记录首个事件、`done` 事件与各阶段耗时，判断慢点卡在哪一节点。

## Key Files & Paths

- `agent-service/app/agent/pc/openui_renderer.py`：OpenUI 表格与详情按钮的唯一投影入口。
- `agent-service/app/agent/pc/nodes.py`：生成节点与 `render_build_openui` 调用点（第 785 行附近）。
- `agent-service/app/agent/pc/renderer.py`：Markdown 兜底渲染，仍保留购买链接，需确认真实链路不走兜底。
- `agent-service/app/agent/pc/hitl.py`、`agent-service/app/api/v1/chat.py`：HITL 门控、中断与恢复校验。
- `agent-service/app/agent/pc/status.py`：阶段状态与前端进度标签。
- `frontend/src/features/generative-ui/library/actions/build-detail.ts`、`actions/index.ts`：详情动作注册与分发。
- `frontend/src/features/chat/components/message-item.tsx`：OpenUI 内容与详情弹窗的挂载点。
- `frontend/src/features/chat/components/build-detail-dialog.tsx`、`build-result-component-row.tsx`、`build-compatibility-list.tsx`：详情弹窗与共用展示组件。
- `frontend/vite.config.ts`：端口 5273 与 `/api`、`/agent` 代理配置。
- `frontend/e2e/build-visual.spec.ts`：现有视觉验收用例，使用 mock SSE，不等于真实链路。
- `docs/quality/pc-config-e2e-2026-11.md`：实测结论落盘位置。

## Decisions & Gotchas

- 用户已在本地启动三端，禁止停止或重启：Vite `5273`（仅监听 `::1`，用 `http://localhost:5273`）、Java `18080`、Agent `18000`；不要再执行 `docker compose up` 起四端容器。
- Vite `/api` 代理必须 `changeOrigin: false`；改回 `true` 会导致登录后所有 `/api` 请求 403（表现为「永远没有访问权限」）。
- 端口不是 5173：`frontend/vite.config.ts` 固定 `5273 + strictPort`，访问 5173 会连到别的项目。
- Agent 本地配置以 `agent-service/.env` 与进程环境为准，`PROJECT_ROOT` 解析到 `agent-service/`；不要依据根 `.env` 判断 OpenUI/HITL 开关。
- HITL 开启时 `storage=postgres` 是硬性前置；memory 后端开启会直接拒绝启动。
- HITL 表单提交后必须立即清除旧表单，避免重复提交报「中断不存在」。
- `@OpenBuildDetail()` 是纯前端动作，不请求后端、不追加消息、不产生新的模型调用与计费。
- 现有 e2e 用例大多 mock SSE，只能证明前端渲染；真实链路需手动浏览器验证或新增 real e2e。

**Skills.** 浏览器实测优先使用 `TRAE-browseruse`；若要采集控制台/网络与性能数据使用 `trae-remote-official:chrome-devtools`。

## How to Verify

```powershell
netstat -ano | Select-String "LISTENING" | Select-String ":5273|:18000|:18080"
uv --directory agent-service run python -c "from app.core.config import Settings; s=Settings(); print(s.openui.enabled, s.hitl.enabled, s.storage.backend)"
uv --directory agent-service run pytest -q tests/test_openui_renderer.py tests/test_hitl.py
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage
```

浏览器侧：打开 `http://localhost:5273`，登录后新建会话发送真实需求，在 DevTools Network 中查看 `/agent/api/v1/chat/stream` 的 EventStream，确认事件顺序为 `stage/reasoning/tool_call/tool_result/done`（HITL 场景额外出现 `interrupt`）。
