# 前端架构

| 项 | 内容 |
| --- | --- |
| 状态 | Current（2026-11-01 按代码全量核对） |
| 最后核验 | 2026-11-01 |
| 主要证据 | `frontend/package.json`、`frontend/src/**`、`frontend/src/routes/router.tsx`、`frontend/src/core/http/**`、`frontend/src/shared/lib/env.ts`、`frontend/src/app/layouts/lib/sidebar.ts` |

## 权威文档导航

| 文档 | 内容 |
| --- | --- |
| [docs/README.md](../../README.md) | 文档地图与状态标签（总入口） |
| [docs/architecture-overview.md](../../architecture-overview.md) | 三端职责、拓扑、信任边界：系统架构唯一权威 |
| [docs/api-contract.md](../../api-contract.md) | 对外 HTTP / SSE / 内部接口契约：契约唯一权威 |
| [docs/services/frontend/development-guide.md](./development-guide.md) | 命令、目录与命名、新增页面/接口、SSE 扩展、提交门禁 |
| [docs/services/frontend/ui-design-system.md](./ui-design-system.md) | UI Token、控件尺寸、组件状态（视觉 SSOT） |
| [.trae/rules-on-demand/10-frontend.md](../../../.trae/rules-on-demand/10-frontend.md) | 编码硬约束（与本文件冲突时，以能通过 CI 的代码与配置为准） |

本文件只描述 `frontend/` 的**实现事实**，不重复契约与视觉规范；契约变更见 `docs/api-contract.md`，视觉变更见 `ui-design-system.md`。

## 1. 适用范围

本文件只描述 `frontend/` 目录内**真实存在**的 React 实现：目录结构、路由、状态、请求层与流式消费方式。

不负责定义后端契约。前端代码里出现的路径与字段只能说明「前端这样调用」，后端是否支持、字段是否可空，必须以各端独立文档与公共契约为准。

## 2. 技术栈与运行方式

版本为 `frontend/package.json` 的声明区间（`^` / `~` 前缀已省略）；`pnpm-lock.yaml` 的实际解析版本未逐项核对。

| 维度 | 事实 | 证据 |
| --- | --- | --- |
| 框架 | React 19.3.1 + React DOM 19.3.1，只写函数组件 | `frontend/package.json` |
| 构建 | Vite 8.2.2 + `@vitejs/plugin-react` 6.1.2；`build` 并行跑 `type-check` 与 `build-only` | `frontend/package.json`、`frontend/vite.config.ts` |
| 语言 | TypeScript ~6.0，`tsc -b`；`strict`、`noUncheckedIndexedAccess`、`jsx: react-jsx`、`@/*` 别名 | `frontend/tsconfig.app.json` |
| 服务端状态 | TanStack Query 5.105（`QueryClient` 单例 + 领域 `queryOptions`） | `frontend/src/app/query-client.ts`、`frontend/src/features/{auth,models,sessions,settings,usage}/api/queries.ts` |
| 客户端状态 | Zustand 5.0.16（认证会话、界面偏好、设置草稿）；流式状态在 React 之外的运行时类 | `frontend/src/app/stores`、`frontend/src/features/auth/model`、`frontend/src/features/chat/runtime` |
| 路由 | TanStack Router 1.170.46，代码式路由树（无文件式路由生成） | `frontend/src/routes/router.tsx` |
| 表单与校验 | react-hook-form 7.91 + `@hookform/resolvers` 7.0 + zod 4.6.7 | `frontend/package.json`、`frontend/src/features/auth/model/login-schema.ts` |
| 国际化 | i18next 26.5 + react-i18next 17.1 | `frontend/src/i18n/index.ts`、`frontend/src/locales` |
| 样式 | Tailwind CSS 4.3.3（`@tailwindcss/vite`）+ `radix-ui` 1.8.1 + cva / clsx / tailwind-merge | `frontend/package.json`、`frontend/src/styles`、`frontend/src/shared/ui` |
| Markdown | react-markdown 10.1 + remark-gfm 4.0 | `frontend/src/features/chat/components/markdown-content.tsx` |
| 可视化与动效 | echarts 6.1、gsap 3.15、three 0.186 | `frontend/package.json` |
| 请求 | Java 用 axios 1.20；Agent 用原生 `fetch` + `ReadableStream` | `frontend/src/core/http/httpJson.ts`、`frontend/src/features/sessions/api/request.ts` |
| 测试 | Vitest 5.0.5 + happy-dom 21.0 + Testing Library；E2E 用 Playwright 1.64.1 | `frontend/vitest.config.ts`、`frontend/playwright.config.ts` |
| 静态检查 | oxlint 1.82 + eslint 10.10 + prettier 3.9.6 | `frontend/package.json`、`frontend/eslint.config.ts` |
| 运行时 | Node `^22.18.0` 或 `>=24.12.0`，pnpm `10.18.0`（corepack） | `frontend/package.json` |

仓库内已无任何 Vue 依赖（源码、`package.json`、配置均为零命中）。

## 3. 目录职责

2026-11-01 已清理 Vue 期的空目录与未被引用的文件；`src` 顶层只剩下列目录与 `main.tsx`。

```text
src/
├── main.tsx        # createRoot 挂载，首次渲染前初始化 i18n
├── app/            # app.tsx、query-client.ts、components/（route-error.tsx）、lib/（report-error.ts）
│                   # layouts/（DefaultLayout.tsx、BlankLayout.tsx、components/、hooks/、lib/）、providers/、stores/
├── routes/         # router.tsx、paths.ts、guards.ts、pages/（8 个页面组件）、design-system-page.tsx
├── features/       # auth、chat、models、sessions、settings、usage，按业务域内聚
├── core/http/      # index.ts、auth.ts、httpJson.ts、sseStream.ts、api-error.ts
├── shared/         # lib/（app-storage、env、format、query-keys、utils）、ui/（Radix 封装）、types/
├── constants/      # http.ts（状态码）、storage.ts（本地存储键）
├── i18n/           # index.ts（i18next 装配）
├── locales/        # zh-CN.ts、en-US.ts
├── styles/         # main.css（`@theme inline` 映射）、cds-theme.css（`--cds-*` Token）
└── test/           # setup.ts（Vitest 环境准备）
```

`features/<domain>/` 实际存在的子目录：

| 域 | 子目录 | 说明 |
| --- | --- | --- |
| `auth` | `api/`、`components/`、`model/` | 登录/刷新/当前用户/资料/密码/设备会话接口、登录表单、登录态 store |
| `chat` | `components/`、`hooks/`、`runtime/` | 对话界面与 Agent Runtime；HTTP/SSE 实现属于 `sessions` 域 |
| `sessions` | `api/`、`components/` | 会话列表、历史消息、`streamChat`、会话级模型 |
| `models` | `api/` | 模型目录与 BYOK 连接 |
| `settings` | `api/`、`components/`（含 `components/sections/`）、`model/` | 偏好/资料/设备查询，设置分区组件，BYOK 连接生命周期模块与共享 zod schema |
| `usage` | `api/` | 本人模型用量 |

约定：`routes/pages` 只做数据编排与组合；服务端数据只进 Query；跨页面偏好与认证会话进 Zustand；所有请求经 `core/http` 或领域 `api/`；跨目录引用用 `@/` 别名。

### 3.1 入口收口现状（待收敛项）

**当前没有任何域级 `index.ts`**（`features/auth/index.ts`、`features/chat/index.ts` 等均不存在）。实际存在的 barrel 只有：

- 各域 `api/index.ts`：`auth`、`models`、`sessions`、`settings`、`usage`；
- `features/chat/runtime/index.ts`。

`.trae/rules-on-demand/10-frontend.md` 要求「跨域协作只经 `index.ts` 公开入口」，与当前代码存在差距。该差距登记为**待收敛项**（C-15），本次只记录现状，既不改代码补入口，也不声称已完成。跨域引用目前直接写到具体模块路径。

### 3.2 Vue 基线

Vue 实现已于 2026-11-01 从工作目录移除，由 Git Tag `vue-frontend-baseline-2026-10-31` 与只读 Worktree `agent-project-template-vue` 保全，仅用于回滚与功能对等比对。新增代码不得重建 `views/`、`stores/`、`router/`、`api/`、`utils/` 等旧目录。

已知遗留：`frontend/deploy/nginx/default.conf.template` 第 56 行注释仍写「Vue Router 使用 createWebHistory」。属配置注释残留，本次文档治理不修代码，仅登记（遗留项 U-05）。

## 4. 路由

| 路径 | 路由名/来源 | 页面文件 | 需要登录 | 布局 |
| --- | --- | --- | --- | --- |
| `/` | `ROUTE_PATHS.welcome`（路由 id `/`） | `src/routes/pages/welcome-page.tsx` | 否 | `BlankLayout` |
| `/welcome` | `ROUTE_PATHS.welcomeAlias` | 重定向到 `/` | 否 | `BlankLayout` |
| `/login` | `ROUTE_PATHS.login` | `src/routes/pages/login-page.tsx` | 否（已登录回 `/chat/new`） | `BlankLayout` |
| `/chat/new` | `ROUTE_PATHS.chatNew` | `src/routes/pages/chat-page.tsx`（`ChatNewPage`） | 是 | `DefaultLayout` |
| `/chat/$sessionId` | `ROUTE_PATHS.chatSession` | `src/routes/pages/chat-page.tsx`（`ChatSessionPage`） | 是 | `DefaultLayout` |
| `/settings` | `ROUTE_PATHS.settings` | 重定向到 `/settings/general` | 是 | `DefaultLayout` |
| `/settings/$section` | `ROUTE_PATHS.settingsSection` | `src/routes/pages/settings-page.tsx` | 是 | `DefaultLayout` |
| `/design-system` | `ROUTE_PATHS.designSystem` | `src/routes/design-system-page.tsx` | 否 | `BlankLayout` |
| `/403` | `ROUTE_PATHS.forbidden` | `src/routes/pages/protected-placeholder-page.tsx` | 是 | `DefaultLayout` |
| 其余路径 | `notFoundComponent` | `src/routes/pages/not-found-page.tsx` | 否 | `BlankLayout` |

`src/routes/pages/` 共 6 个页面组件（另含 2 个同名 `.spec.tsx` 测试）。

实现细节：

- 路由树在 `routes/router.tsx` 用 `createRootRouteWithContext` + `createRoute` 组装；所有路径常量集中在 `routes/paths.ts`（含 `/chat/$sessionId`），守卫、导航与重定向共用。
- 页面统一 `lazyRouteComponent` 动态 `import()`；`NotFoundPage` 直接导入，作为根路由的 `notFoundComponent`。
- `/chat/new` 注册在 `/chat/$sessionId` 之前，避免静态段被当成会话 ID。
- 设置分区只认合法值：`/settings` 与非法 `section` 都在 `beforeLoad` 重定向到 `/settings/general`，保证地址可刷新、可分享。
- 受保护路由挂在无路径布局路由 `_authenticated` 上，`beforeLoad` 统一执行 `requireAuthenticated`：先 `ensureAuthSession()`，再 `ensureQueryData(currentUserQueryOptions)` 预热用户；未登录重定向 `/login?redirect=<原地址>`。页面内不重复判权。
- `/login` 的 `beforeLoad` 执行 `redirectAuthenticatedUser`，已登录用户直接回 `/chat/new`。
- 请求层刷新失败时由 `main.tsx` 装配的 `onUnauthorized` 调 `handleUnauthorizedNavigation`：清会话并跳 `/login?redirect=当前地址`；`core/http` 不直接依赖 router。
- 侧边栏不再有主导航：`app/layouts/lib/nav.ts` 只保留 `SidebarMode = 'default' | 'settings'`。默认模式依次显示品牌位、新建对话、「最近」会话列表与用户菜单；设置从用户菜单进入，设置模式下侧栏整体替换为设置目录，移动抽屉复用同一份信息结构。
- `/home` 与 `/history` 页面已删除，`ROUTE_PATHS`、路由树、守卫与文案同步清理；登录默认落地、品牌链接、404 / 错误页与设置页返回入口统一指向 `/chat/new`。

## 5. 数据流

### 5.1 Java 业务接口

`src/core/http/httpJson.ts` 创建 axios 实例：

- `baseURL` 取 `env.apiBaseUrl`（构建期注入，默认 `/api/v1`），`timeout` 取 `env.apiTimeout`。
- 请求拦截器注入 `Authorization: Bearer <token>`，token 来自 `src/core/http/auth.ts` 的**内存变量**（不落 `localStorage` / `sessionStorage`）；调用方显式传 `idempotencyKey` 时注入 `Idempotency-Key`。
- 响应拦截器按信封 `{ code, message, data, requestId }` 判断：`code === 0` 交给调用方返回 `data`；否则抛 `ApiError`，非 `silent` 时统一 toast。
- 401 的决策全部交给 `auth.ts` 的 `handleUnauthorized()`：单飞刷新 → 成功则 `replay`（`isAuthRetried` 防循环）→ 失败则 `redirect`（清令牌并触发一次全局跳转）。axios 与 fetch 两个适配器只按返回值重放，不再各自维护 URL 规则表。
- 认证端点用**声明式策略**而非 URL 匹配：`login` / `refresh` 传 `authPolicy: 'no-redirect'`（不刷新、不跳转，登录页内联提示），`logout` / `logout-all` 传 `authPolicy: 'no-refresh'`（不刷新但仍清理并跳转）。
- 刷新实现与全局跳转在 `src/main.tsx` 通过 `configureAuth({ refresh, onUnauthorized })` 显式装配，`core/http` 不反向依赖认证模块与路由。
- 403 表示已认证但无权限，不刷新、不退出；主动取消（`axios.isCancel`）不提示错误。
- `ApiError` 与 `normalizeError` 是唯一错误类型；Query 重试只对无状态码、408/429 与 5xx 生效，最多 2 次，`staleTime` 30s、`gcTime` 5min，mutation 不自动重试。

当前实际调用（路径只写服务内相对段，`/api/v1` 前缀由 `VITE_API_BASE_URL` 提供）：

| 文件 | 端点 |
| --- | --- |
| `features/auth/api/auth.ts` | `POST /auth/login`、`POST /auth/refresh`、`POST /auth/logout`、`POST /auth/logout-all`、`GET /auth/me` |
| `features/auth/api/user.ts` | `GET` / `PUT /users/me/profile`、`PUT /users/me/password`、`GET /users/me/sessions`、`DELETE /users/me/sessions/{familyId}` |
| `features/settings/api/preferences.ts` | `GET` / `PUT /users/me/preferences` |
| `features/models/api/models.ts` | `GET /models`、`GET` / `POST /model-connections`、`PUT` / `DELETE /model-connections/{id}`、`POST /model-connections/{id}/verify` |
| `features/usage/api/model-usage.ts` | `GET /users/me/model-usage` |

服务端数据统一由 `shared/lib/query-keys.ts` 登记的 key 与领域 `queryOptions` 承载，禁止在组件里手写 key。

BYOK 连接生命周期集中在 `features/settings/model/use-model-connections.ts`：创建、验证、轮换、删除成功后统一失效 `queryKeys.models.connections`，创建与删除额外失效 `queryKeys.models.catalog`；成功提示与「未启用 / 加载失败」归类也在模块内完成，三个视图只负责三态切换与渲染。

### 5.2 Agent 流式接口

Agent 返回裸 JSON 与 SSE，**不复用** `httpJson.ts`：

1. `features/sessions/api/request.ts` 用 `fetch` 请求 `env.agentBaseUrl`（默认 `/agent/api/v1`，生产经 Nginx 去前缀转发），自动带 `Authorization`；401 在流尚未消费时先单飞刷新再重放一次。
2. `src/core/http/sseStream.ts` 按 SSE 规范解析 `id` / `event` / `data`，兼容 CRLF 与心跳注释，事件名白名单为 `token`、`reasoning`、`tool_call`、`tool_result`、`citations`、`done`、`error`（`SSE_EVENT_TYPES`）。
3. `features/sessions/api/stream-chat.ts` 把服务端事件转换为判别联合 `ChatStreamEvent`（`done.thread_id` → `threadId`）；未识别事件或损坏的 JSON 单帧返回 `null` 并继续读流。
4. `features/chat/runtime/agent-runtime.ts` 消费事件：`token` / `reasoning` 先进入帧级缓冲，由 `requestAnimationFrame` 合并成每帧最多一次 `publish`；`tool_call`、`tool_result`、`done`、`error`、停止与切换会话前强制 flush，保证内容不丢且事件顺序不变。`tool_call` 建步骤、`tool_result` 回填步骤、`done` 进入交接、`error` 置错误状态。

**流式渲染约束**：SSE 每秒可能推送数百个 token，渲染链路按三层收敛成本：运行时帧级合并状态更新；`MessageItem` 与 `MarkdownContent` 用 `memo` 固定渲染边界，流式期间只有最后一条消息重渲染；Markdown 在流式期间按「代码围栏外的空行」分块增量解析（`components/markdown-blocks.ts`），已完成块跳过解析，流结束后恢复整段一次解析。`ChatConversation` 仅在用户贴底时于绘制前滚动，避免每帧读取 `scrollHeight` 造成布局抖动。滚动容器固定声明 `scrollbar-gutter: stable both-edges`（`chat-conversation.tsx`）：内容撑出滚动条时可用宽度不再骤减，消息不会横向位移或重新换行；移除该声明会直接复现布局跳动。

**逐字淡入**：流式尾块通过 `components/stream-reveal.ts` 这个 rehype 插件，把文本节点中的非空白字符包成 `span.stream-char`（代码块内不包裹），由 CSS 播放一次 320ms 的透明度 + 去模糊动画。React 按索引复用同级节点，已出现的字符保持动画进度，只有新追加的字符触发动画；单块超过 1200 字符时自动降级为普通 Markdown 渲染，控制单帧 DOM 规模。插件只作用于尾块，流结束后整段重新解析，最终 DOM 不保留逐字 span。

会话管理接口同在 `features/sessions/api/`：`GET /sessions`（分页）、`GET /sessions/{thread_id}/messages`（`page` / `size` / `order`）、`PATCH /sessions/{thread_id}`（重命名）、`DELETE /sessions/{thread_id}`（204，走 `requestAgentVoid`）、`PUT /sessions/{thread_id}/model`（会话级模型）。Query 默认取最新一页（`order=desc`，100 条），页面按同一 key 预热与重同步。

**偏好下发**：`ChatRequest`（`features/sessions/api/types.ts`）含 `preferences` 字段（`instructions`、`reply_language`、`response_style`、`use_history`），命名与 Agent 的 snake_case 一致。`AgentRuntime.runTurn()` 每轮先 `deps.getPreferences()` 取当前偏好，取不到就不携带，与 `message` / `thread_id` / `model` 一起提交（Agent 只从请求体读偏好，不查库）；设置页通过 `features/settings/api/preferences.ts` 以 Query 为唯一事实来源读写。

**401 与流式边界**：`sendAgentRequest` 只在响应头到达、流未消费时处理 401 并重放，重放沿用同一 `Idempotency-Key`；一旦进入 `readSseStream`，后续错误只能走流内 `error` 事件。404 不弹全局提示，由调用方判断：草稿会话不发起历史查询，已落库会话的 404 表示会话不存在，由页面渲染错误态。

### 5.3 鉴权现状

**四态状态机**（`features/auth/model/auth-session.ts`）：`unknown` →（启动恢复）→ `authenticated` / `unauthenticated`；刷新过程中为 `refreshing`。

- Access Token 只存内存，页面刷新即丢失；**不写 `localStorage` / `sessionStorage` / Zustand 持久化**。
- 首次导航时若状态为 `unknown`，`ensureAuthSession()` 触发 `restoreSession()`：先 `POST /auth/refresh`（凭 `HttpOnly` Cookie，JS 读不到），成功再 `GET /auth/me` 补全用户信息；失败则保持未登录并放行到登录页。
- `restoreSession` 调用 `refreshOnce()` 共享单飞 Promise，避免并发重复请求；`refreshSessionToken` 内的 `sessionEpoch` 保证退出或重新登录后，迟到的刷新结果按世代号丢弃。
- `logout()` 先调用 `POST /auth/logout` 撤销服务端会话，再清本地状态；接口失败也照常清理。
- 403 走统一错误提示，`/403` 页面存在但当前无跳转入口。
- `agent-thread` 仍落 `sessionStorage`，只作为旧实现的兼容镜像，URL 才是会话唯一权威。
- `agent-draft-thread` 记录本地生成、服务端首轮结束前尚未落库的会话 ID 列表；落库确认后由 `deps.confirmPersisted` 清除当前 ID，用于门控历史查询。

## 6. 状态管理

| 状态容器 | 职责 | 持久化 |
| --- | --- | --- |
| TanStack Query | 服务端数据唯一缓存：当前用户、会话列表与历史、偏好、资料、设备会话、模型目录/BYOK、用量 | 内存（刷新重取） |
| `useAuthSessionStore` | 四态登录、内存 Access Token、当前用户、登录/退出/刷新/恢复 | 无（凭证不落存储，靠刷新 Cookie 恢复） |
| `useAppStore` | 主题（light/dark/system）、语言、侧栏宽度与折叠、账户菜单图标开关；窄屏抽屉开合为纯内存态 | `localStorage['app-state']`，平铺 `{theme, locale, isSidebarCollapsed, sidebarWidth, showAccountMenuIcon}` |
| `useSettingsDraftStore` | 设置页未提交的本地偏好草稿（chats / general / appearance）；资料、密码、设备与 Agent 偏好以服务端为准 | 无 |
| `AgentRuntime` | 当前会话尚未落库的流式消息、工具步骤、错误与 `canRetry` | 无；`agent-thread` 为兼容镜像，`agent-draft-thread` 为草稿标记 |

状态归属（ADR-0002 D-09 / D-14）：

- 服务端数据只进 Query，不进 Zustand；同一份数据只允许一个 key。
- `AgentRuntime`（`features/chat/runtime/agent-runtime.ts`）是 React 之外的普通类，组件通过 `useAgentRuntime`（`features/chat/hooks/use-agent-runtime.ts`）的 `useSyncExternalStore` 订阅快照；禁止把流式 token 塞进 Zustand 或 Query Cache。
- `done` 之后由 `turn-handoff.ts` 按固定顺序交接：「确认落库（读取最新 1 条消息）→ 失效当前会话历史 key → 重新同步历史 → 清理临时状态」；每步校验运行序号，失败保留已生成内容并标记可重试，不提前失效缓存。
- URL 是会话唯一权威：`features/chat/hooks/use-chat-session.ts` 按「URL → `agent-thread` 镜像 → 新 ID」解析，并立即用 `navigate(..., replace)` 转成规范地址；`done` 带回真实 ID 时先确认运行时已绑定当前会话再改写，避免残留快照造成两个会话互相跳转。该模块还是会话列表（固定一页 20 条）的唯一查询方，统一产出历史合并、`isPersisted`、标题与 `sessionModelKey`；`use-chat-model` 只负责模型切换与持久化。会话身份分两阶段：本地生成、服务端首轮结束前未落库的 ID 记为草稿（`agent-draft-thread`），**不发起历史查询**，因此不会用 404 表达正常状态；`confirmPersisted` 成功后清除标记，历史查询恢复。切换会话会中止在途流并清空临时消息。
- 浏览器存储统一经 `shared/lib/browser-store.ts` 的 `createBrowserStore`（`readJson` / `writeJson` / `remove` / `keys` / `namespace`）：异常捕获、JSON 编解码、配额与隐私模式降级集中在一处，`Storage` 可注入。`app-storage`（`app-state`，localStorage）与 `agent-thread`、OpenUI 表单状态（sessionStorage）只保留键构造、结构校验与淘汰规则；键名、前缀与平铺结构不得改动，`index.html` 首屏脚本直接读取 `app-state`。

`features/chat/runtime/` 现有文件：`agent-runtime.ts`（订阅、幂等守卫、单轮状态机、快照基线与交接编排）、`turn-handoff.ts`（交接顺序的纯函数）、`agent-thread.ts`、`deps.ts`、`message-model.ts`、`history-messages.ts`、`types.ts`、`index.ts`。

## 7. 环境变量

统一由 `src/shared/lib/env.ts` 读取并冻结，业务代码禁止直接访问 `import.meta.env`。

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `VITE_APP_ENV` | 是 | `development`（非法值回落） | 仅接受 `development` / `production` |
| `VITE_APP_TITLE` | 是 | `Agent` | 页面标题与品牌展示，`index.html` 用 `%VITE_APP_TITLE%` 注入 |
| `VITE_API_BASE_URL` | 是 | `/api/v1` | Java 接口前缀 |
| `VITE_AGENT_BASE_URL` | 否 | `/agent/api/v1` | Agent 接口前缀，生产走 Nginx `/agent/` 去前缀转发 |
| `VITE_API_TIMEOUT` | 否 | `10000` | 毫秒；非正数回落默认值 |
| `VITE_USE_MOCK` | 否 | `false` | 仅占位，当前无 Mock 实现 |
| `VITE_OPENUI_ENABLED` | 否 | `false` | 生成式 UI 开关；关闭时聊天仍按普通 Markdown 渲染，默认关闭 |

「必填」指生产构建必须提供：`frontend/scripts/check-env.mjs` 在生产构建前硬校验，必填项缺失、`VITE_APP_ENV` 非 `production`、`VITE_USE_MOCK=true`、`VITE_API_BASE_URL` / `VITE_AGENT_BASE_URL` 含 `http://` 或 `localhost` 等，均直接失败。

`VITE_*` 会被打进静态产物：禁止写入密钥、Token、内网地址；修改后必须重建镜像，重启容器无效。

## 8. 已知偏差与临时状态

| 项 | 现状 | 性质 |
| --- | --- | --- |
| 域级 `index.ts` 缺失 | 只有各域 `api/index.ts` 与 `features/chat/runtime/index.ts`，无 `features/<domain>/index.ts`；规则要求与代码存在差距 | 待收敛项（见 §3.1、审计 C-15） |
| Nginx 模板注释 | `frontend/deploy/nginx/default.conf.template:56` 仍写「Vue Router 使用 createWebHistory」 | 遗留注释，本次不修（审计 U-05） |
| `/403` 页面 | 路由存在且受保护，但当前无业务入口跳转 | 占位 |
| `VITE_USE_MOCK` | 只有配置位，无实现；生产构建禁止为 `true` | 占位 |
| 多标签页并发刷新 | 某标签页刷新失败会短暂清态，但刷新 Cookie 共享，下次导航 `restoreSession` 可恢复 | 已知行为，可接受 |
| 刷新 Cookie 依赖同域部署 | Cookie `Path=/api/v1/auth`、`SameSite=Strict`，要求前端与 Java 同站；分域部署需重新评估 | 限制条件，非缺陷 |

前几版登记的两项已随代码修正，不再成立：

- 「Vue 遗留目录仍存在」→ 2026-11-01 已清理，Vue 基线由 Git Tag `vue-frontend-baseline-2026-10-31` 与只读 Worktree `agent-project-template-vue` 保全（§3.2）。
- 「对话偏好未随请求下发」→ `AgentTurnRunner.start()` 已按轮次取偏好并随请求提交（§5.2）。

## 9. 明确不负责

- 不签发 Token（由 Java `agent-application-service` 签发，前端只保存与透传）。
- 不做权限安全边界：前端隐藏入口只用于交互，真实校验由后端保证。
- 不定义 Agent 的模型、工作流、工具与 State；这些属 `agent-service`。
- 不直接访问数据库、Redis 或任何模型密钥。
- 不定义对外契约：路径、字段、错误码、SSE 事件类型的唯一权威是 `docs/api-contract.md`。
