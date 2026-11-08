# 前端开发指南

| 项 | 内容 |
| --- | --- |
| 状态 | Current（2026-11-01 按代码核对） |
| 基线 | 不绑定分支与 commit；以 `frontend/package.json` 的 scripts 与 `frontend/src/**` 为准 |
| 最后核验 | 2026-11-01 |
| 主要证据 | `frontend/package.json`、`frontend/vitest.config.ts`、`frontend/playwright.config.ts`、`.github/workflows/ci.yml`、`frontend/src/**` |

## 权威文档导航

| 文档 | 内容 |
| --- | --- |
| [docs/README.md](../../README.md) | 文档地图与状态标签（总入口） |
| [docs/architecture-overview.md](../../architecture-overview.md) | 三端职责、拓扑、信任边界 |
| [docs/api-contract.md](../../api-contract.md) | 对外 HTTP / SSE / 内部接口契约 |
| [docs/services/frontend/architecture.md](./architecture.md) | 前端目录、路由、数据流、状态、环境变量（实现事实） |
| [docs/services/frontend/ui-design-system.md](./ui-design-system.md) | UI Token、控件尺寸、组件状态（视觉 SSOT） |
| [.trae/rules-on-demand/10-frontend.md](../../../.trae/rules-on-demand/10-frontend.md) | 前端编码硬约束 |

本文件只写「怎么做」，实现事实与已知偏差见 `architecture.md`；两者冲突时以代码为准。

## 1. 适用范围

`frontend/` 的开发约定：命令、目录与命名、新增页面/接口的落地步骤、SSE 扩展规则、提交前门禁。架构与路由事实见 [architecture.md](./architecture.md)。

## 2. 命令（在 `frontend/` 下执行，或在仓库根用 `corepack pnpm --dir frontend <script>`）

| 命令 | 作用 | 会改文件 |
| --- | --- | --- |
| `corepack pnpm dev` | 开发服务器（Vite，热更新，端口 5273） | 否 |
| `corepack pnpm build` | 并行跑 `type-check` 与 `build-only` | 产出 `dist/` |
| `corepack pnpm build-only` | 仅生产构建，不做类型检查 | 产出 `dist/` |
| `corepack pnpm preview` | 预览生产产物 | 否 |
| `corepack pnpm type-check` | `tsc -b` | 否 |
| `corepack pnpm lint` | `oxlint --fix` + `eslint --fix --cache` | **是（自动修复）** |
| `corepack pnpm lint:ci` | `oxlint . && eslint . --cache`（去掉 `--fix`），CI 用这条 | 否 |
| `corepack pnpm test` | `vitest run`（happy-dom） | 否 |
| `corepack pnpm test:watch` | Vitest watch | 否 |
| `corepack pnpm test:coverage` | 覆盖率报告，阈值 `lines ≥ 80%` | 产出 `coverage/` |
| `corepack pnpm e2e` | Playwright 全量 E2E（chromium） | 产出测试产物 |
| `corepack pnpm e2e:smoke` | 只跑 `e2e/smoke.spec.ts` | 否 |
| `corepack pnpm e2e:critical` | 只跑 `@critical` 标记用例 | 否 |
| `corepack pnpm verify` | `lint:ci` + `type-check` + `test` + `build-only` | 产出 `dist/` |
| `corepack pnpm check:env --mode production` | 校验生产构建环境变量 | 否 |
| `corepack pnpm openui:prompt` | 从 `OPENUI_LIBRARY` 生成 `agent-service/app/agent/prompts/openui.md` | 是（写入 agent-service） |
| `corepack pnpm openui:prompt:check` | 比对生成产物与组件库，发现漂移即失败 | 否 |
| `corepack pnpm format` | `prettier --write --experimental-cli src/` | 是 |

注意：

- 使用 `corepack pnpm` 而不是机器上的全局 `pnpm`，保证与 `package.json` 固定的 pnpm `10.18.0` 一致；Node 需满足 `^22.18.0` 或 `>=24.12.0`。
- `corepack pnpm lint` 会静默改写源码。只想检查时用 `lint:ci`。
- E2E 的 `baseURL` 是 `http://localhost:5273`，`webServer` 为 `corepack pnpm dev` 且 `reuseExistingServer: true`：本地已启动开发服务器时直接复用。

## 3. 目录与命名

- 目录与文件名 kebab-case；组件文件 kebab-case、导出 PascalCase（`chat-composer.tsx` → `ChatComposer`）；`src/app/layouts/*Layout.tsx` 是既有 PascalCase 例外。
- 页面统一放 `src/routes/pages/<name>-page.tsx`，路由注册只改 `src/routes/router.tsx` 与 `src/routes/paths.ts`。
- 业务模块放 `src/features/<domain>/`，按需建 `api/`、`model/`、`components/`、`hooks/`、`runtime/`，不为空占位。
- TS 模块与 hooks kebab-case（`use-agent-runtime.ts`）；测试与被测文件同名（`agent-runtime.spec.ts`、`chat-composer.spec.tsx`）。
- `src/shared/ui/**` 为 shadcn 风格组件（Radix primitive 组合），保留既有结构，不改名。
- 跨目录引用一律 `@/`，禁止 `../../../`。
- 布尔值用 `is` / `has` / `can` 前缀；禁止无意义缩写与单字母变量（循环计数除外）。

## 4. 新增一个页面

1. 建 `src/routes/pages/<name>-page.tsx`，导出 PascalCase 组件（如 `export function FooPage()`）。
2. 在 `src/routes/paths.ts` 登记路径常量，避免字符串散落到导航与重定向。
3. 在 `src/routes/router.tsx` 用 `createRoute` + `lazyRouteComponent` 注册：
   - 需要登录的页面挂到 `_authenticated` 布局路由下（统一执行 `requireAuthenticated` 与用户预热）；
   - 公开页挂到根路由（`BlankLayout`）；
   - 静态段必须排在动态段之前（如 `/chat/new` 先于 `/chat/$sessionId`）。
4. 在 `src/locales/zh-CN.ts` 与 `en-US.ts` 补 `routes.<name>` 词条；需要菜单或面包屑时同步 `src/app/layouts/lib/nav.ts` 的前缀表。
5. 若页面需要请求：先在 `src/features/<domain>/api/` 加接口与 `queryOptions`，在 `src/shared/lib/query-keys.ts` 登记 key，再由页面订阅；角色权限只用于交互，不在页面内做安全判定。
6. 新增/调整路由后补 `src/routes/guards.spec.ts` 或 `src/routes/router.spec.tsx` 用例，并为页面补 `.spec.tsx`。

> 鉴权约定：受保护路由一律由 `_authenticated` 的守卫处理；首次导航遇到 `unknown` 会先 `ensureAuthSession()`（`/auth/refresh` + `/auth/me`），未登录跳 `/login?redirect=<原路径>`。Access Token 只存内存，禁止写 `localStorage` / `sessionStorage` / Cookie；持久登录只依赖 Java 下发的 `HttpOnly` 刷新 Cookie。

## 5. 新增一个接口

1. Java 接口：在 `src/features/<domain>/api/<domain>.ts` 用 `@/core/http` 的 `http` / `request` 调用，禁止组件内直接用 `axios` / `fetch`。
2. Agent 接口：复用 `src/features/sessions/api/request.ts` 的 `requestAgentJson` / `requestAgentVoid`，不要另建 fetch 封装。
3. 每个接口必须声明请求参数类型与响应类型，禁止裸对象与 `any`；不确定时用 `unknown` 并在使用处收窄。
4. 查询类接口在 `api/queries.ts` 用 `queryOptions` 收口，并在 `shared/lib/query-keys.ts` 登记唯一 key；写操作按需用 `useMutation` 并失效对应 key。
5. 命名 `getXxx` / `createXxx` / `updateXxx` / `deleteXxx`；URL 参数用 `params`，路径参数必须 `encodeURIComponent`。
6. 错误统一经 `normalizeError` 处理，禁止静默 `catch`；能力探测类请求（模型目录、用量、BYOK）用 `silent` 关闭全局 toast，由调用方降级。
7. 环境地址只从 `src/shared/lib/env.ts` 取，禁止硬编码域名。
8. 契约变更（路径、字段、错误码）同步根 `docs/api-contract.md`、Java DTO 与 Agent Schema。

## 6. SSE 事件扩展

当前有 7 种事件：`token`、`reasoning`、`tool_call`、`tool_result`、`citations`、`done`、`error`。扩展时按顺序改：

1. `agent-service` 的发送端（`app/api/v1/chat.py` 与 `sse.py`）。
2. `src/core/http/sseStream.ts` 的 `SSE_EVENT_TYPES` 与 `SseEventType`。
3. `src/features/sessions/api/types.ts` 的 `ChatStreamEvent` 联合类型与 `stream-chat.ts` 的 `toChatStreamEvent` 映射。
4. `src/features/chat/runtime/agent-runtime.ts` 的 `dispatch` 分支；若事件需要展示，同步 `RuntimeMessage` 字段与 `message-item.tsx` 的渲染。
5. `src/features/sessions/api/stream-chat.spec.ts` 与 `src/features/chat/runtime/*.spec.ts` 补用例。
6. 根 `docs/api-contract.md` 的 §7 SSE 契约。

未识别事件必须"忽略并继续"，不能抛错中断流；这是现有向前兼容约定，改动前先确认后端不再发送旧事件。

## 7. 样式与设计系统

- 视觉权威是 `docs/services/frontend/ui-design-system.md`（Token、尺寸、组件状态）。
- React 没有 `scoped` 样式：组件用 Tailwind 工具类 + CSS 变量组合，全局样式放 `src/styles/main.css`（由 `main.tsx` 引入）与 `src/styles/cds-theme.css`。
- 颜色、间距、圆角、字号用 CSS 变量或 Tailwind Token，禁止硬编码 hex；布局优先 `flex` / `grid`。
- 控件高度只取 23 / 26 / 32 / 40px 阶梯；圆角只取 6 / 8px 或对应 Token。
- 禁止 `!important`（覆盖第三方需在代码注释说明原因）。
- 暗色主题由 `document.documentElement` 的 `.dark` 类控制；`index.html` 首屏脚本读取 `app-state.theme` 提前应用，`ThemeProvider` 负责运行时同步，改动主题逻辑必须两边一起改。

## 8. 提交前门禁

```bash
corepack pnpm lint:ci
corepack pnpm type-check
corepack pnpm test
corepack pnpm test:coverage
corepack pnpm check:env --mode production
corepack pnpm build-only
```

也可先跑 `corepack pnpm verify`（lint:ci + type-check + test + build-only），再补覆盖率与生产环境校验。

CI（`.github/workflows/ci.yml`）对 `frontend/**` 或 `agent-service/app/agent/prompts/openui.md` 变更执行：`lint:ci` → `type-check` → `openui:prompt:check` → `test:coverage` → 安装 chromium → `e2e:critical` → `check:env --mode production` → `build`。任一步失败即阻断合并。

不提交：`node_modules/`、`dist/`、`coverage/`、Playwright 产物、日志、`.env.local`、任何密钥。

## 9. 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 生产构建报 `[check-env]` 失败 | 缺少 `VITE_APP_ENV` / `VITE_APP_TITLE` / `VITE_API_BASE_URL`，或地址含 `http://`、`localhost` | 在构建参数或 `.env.production` 补齐同源前缀（如 `/api/v1`） |
| 生产构建后接口 404 | `VITE_API_BASE_URL` 未在构建期注入；变量会被打进静态产物 | 重新构建镜像，不要只重启容器 |
| `corepack pnpm lint` 后出现大量未预期改动 | lint 带 `--fix` | 用 `lint:ci` 检查；提交前确认 diff |
| 登录后刷新页面变未登录 | Access Token 只在内存，刷新后靠 `HttpOnly` 刷新 Cookie 恢复 | 检查 `/auth/refresh` 是否携带 Cookie（`Path=/api/v1/auth`、`SameSite=Strict`） |
| 刷新页面一直跳登录页 | Cookie 没被携带（跨域、Path 不符、`Secure` 与本地 http 不匹配） | 看 Network 中 `/auth/refresh` 是否带 `Cookie`；本地确认 `AUTH_COOKIE_SECURE=false` |
| 401 反复刷新不停止 | 在已消费的 SSE 流或 `/auth/refresh` 自身触发刷新 | 请求层已排除三个 auth 路径；SSE 只在未交付内容时刷新，检查 `sendAgentRequest` 边界 |
| SSE 事件收不到 | 事件名不在白名单或 `Content-Type` 不是 `text/event-stream` | 对照 §6 五个事件名与 `src/core/http/sseStream.ts` |
| E2E 启动失败或连错端口 | 端口 5273 被占用，或复用了指向旧代码的 dev server | 关闭旧服务后重跑；配置见 `frontend/playwright.config.ts` |
| 单测在本机失败、CI 却通过（或相反） | 开发者 `.env.local` 覆盖了 `VITE_*`，vitest 同样会加载它 | 用例内 `vi.mock('@/shared/lib/env')` 固定契约默认值；不要改断言迁就本机配置 |
| E2E 全部停在登录页、mock 不生效 | mock 只匹配 `**/api/v1/**`，漏掉 `/api/v2/**` 等新版接口；或 Agent 配成绝对地址，与 `/agent` 代理前缀不一致 | 通配统一 `**/api/v*/**`；匹配前用 `new URL(input).pathname` 归一化并剥掉代理前缀 |
| 文案类断言隔一两轮就失效 | 断言绑定了欢迎页、按钮等易变文案 | 改用稳定的语义断言（`getByRole('link', { name })`、`router.state.location.pathname`） |
