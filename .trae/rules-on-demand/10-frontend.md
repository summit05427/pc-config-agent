---
alwaysApply: true
---

# 前端规则（frontend/**）

适用范围：仅 `frontend/**`。其他目录忽略本文件；公共约束见 `00-monorepo-common.md`。

技术栈：React 19 + TypeScript 6 + Vite 8 + TanStack Router + TanStack Query + Zustand + i18next + Tailwind v4 + Radix UI + Vitest/happy-dom + Playwright。

## 目录职责

- `src/app`：入口与 Provider（`app.tsx`）、`query-client.ts`、`layouts/`、全局 `stores/`。
- `src/features/<domain>`：按业务域聚合 `api/` `model/` `components/` `runtime/` `hooks/`；跨域协作只经对方 `api/index.ts` 公开入口。
- `src/routes`：`router.tsx` 路由树、`paths.ts` 路径常量、`guards.ts` 守卫、`pages/` 页面。
- `src/shared`：`ui/`（Radix 封装）、`lib/`（纯函数与 `query-keys.ts`）、`types/`；`src/core/http` 为 HTTP 门面；`src/constants`、`src/i18n`、`src/locales`、`src/styles` 存放常量、文案与设计 Token。
- 依赖方向：`core` / `shared` 不依赖 `features`；`features` 之间只经对方的 `api/index.ts` 引用（`chat` 域尚未提供域级 `index.ts`，属待收敛项，见 `docs/planning/closure-plan.md` C-15）；跨目录一律用 `@/` 别名。
- Vue 遗留目录与 `src/types/common.ts` 已于 2026-11-01 清理；若本地仍有空目录请勿提交，新增代码统一放入 `app/`、`routes/`、`features/`、`shared/`、`core/`。
- 阅读顺序：[docs/README.md](../../docs/README.md) → `docs/services/frontend/architecture.md` → `development-guide.md` → `ui-design-system.md`；跨端改动先读 `docs/api-contract.md`。

## 命名

- 文件与目录 kebab-case；组件文件 kebab-case、导出 PascalCase（`chat-composer.tsx` → `ChatComposer`），一个文件只导出一个组件；`src/app/layouts/*Layout.tsx` 沿用既有 PascalCase 文件名，不改名。
- hooks 文件 `use-xxx.ts` 且导出同名 hook；测试与被测文件同名（`chat-composer.spec.tsx`）。
- `src/shared/ui/**` 为 Radix 封装，保留 kebab-case 文件名与 PascalCase 导出，不按业务改名。
- 路由页面位于 `src/routes/pages` 且组件名带 `Page` 后缀；统一出口只允许 `index.ts`，不建目录级入口组件。

## 组件与 hooks

- 只写函数组件，禁止 class 组件与 `React.Component`；props 用显式 `interface`，children 标 `ReactNode`。
- 组件内不直接发请求：只用 `features/<domain>/api` 导出的 `queryOptions` / mutation 与 `useQuery` / `useMutation`。
- 请求由事件或 Query 触发，禁止在 `useEffect` 里发起请求（StrictMode 会双调用）；effect 只做同步副作用。
- 自定义 hook 命名 `useXxx` 并显式声明返回类型；组合逻辑抽 hook，不复制粘贴；React 外状态源用 `useSyncExternalStore` 订阅。
- 单组件超过 200 行或承担两种以上职责必须拆分；JSX 嵌套不超过 3 层。
- 列表 `key` 用稳定唯一 ID（消息用服务端消息 ID），禁止用数组下标；不直接操作 DOM，用 `ref`。
- 布局用 `src/app/layouts/DefaultLayout.tsx`、`BlankLayout.tsx`；私有子组件放同域 `components/`。

## 状态管理

- 四层归属：服务端数据只进 TanStack Query；跨页偏好与认证会话进 Zustand；组件内部用 `useState`；Agent Runtime 用独立类。
- Query key 统一登记在 `src/shared/lib/query-keys.ts`：按域分组、每组含 `all` 前缀 key；禁止组件内手写数组字面量，同一份数据只允许一个 key。
- Zustand 不镜像服务端数据（`app/stores/app-store.ts`、`features/auth/model/auth-session.ts`）；派生值用 selector，不在 store 重复存。
- Agent Runtime 固定在 `features/chat/runtime`，是 React 外的普通类：禁止放进 Zustand / Query Cache / 组件 effect，组件只经 `useAgentRuntime` 订阅。
- `done` 后交接顺序固定：`invalidate` → 服务端确认 → 历史重新同步 → Runtime 临时状态清理；禁止两边同时追加同一份流式 Token。
- 持久化两键固定：`app-state`（localStorage 平铺 `{theme, locale, isSidebarCollapsed, sidebarWidth}`，禁止 Zustand `persist` 的 `{state, version}` 包装）、`agent-thread`（sessionStorage 兼容镜像）。
- 浏览器存储统一经 `shared/lib/browser-store.ts`：禁止业务代码直接访问 `window.localStorage` / `sessionStorage`，也禁止再写一份 `try/catch` 与 JSON 编解码；各域只保留键构造、结构校验与淘汰规则，键名、前缀与存储结构不得随重构改动。
- URL 中 `$sessionId` 是会话唯一权威，兼容镜像只能单向写入补充，不得反向覆盖；凭证不落持久化层。

## API 层

- 所有请求经 `src/core/http`（`httpJson` / `sseStream` 门面），禁止组件或 feature 直接使用 `axios` / `fetch`。
- 按域放 `src/features/<domain>/api/`，查询用 `queryOptions` 组织；命名 `getXxx`、`createXxx`、`updateXxx`、`deleteXxx`。
- 接口必须有请求参数与响应类型，禁止裸对象与 `any`；用户输入用 Zod Schema 校验，结构化 Agent 输出先校验再收窄。
- 错误经 `normalizeError` / `getHttpErrorMessage` 处理，禁止静默 catch；401 由请求层单飞刷新，feature 不重复实现。
- 环境变量只从 `src/shared/lib/env.ts` 读取，禁止业务代码直接访问 `import.meta.env`。
- 路径契约：Java `/api/v1`；Agent 经 Nginx `/agent/api/v1`，不得写死在组件里。

## 路由

- 路由树集中在 `src/routes/router.tsx`，路径字符串只从 `paths.ts` 取。
- 页面用 `lazyRouteComponent` 懒加载；动态段使用前校验存在性（如 `sessionId`）。
- 守卫只做权限判断、重定向与 `ensureQueryData` 预热，不在 loader 重复实现 HTTP / 缓存 / 错误处理。
- 搜索参数用 `validateSearch` 显式收窄；登录态判断集中在 `guards.ts`，页面内不重复判断。

## 类型

- 禁止 `any`，未知值用 `unknown` 并收窄；类型名 PascalCase。
- 公共类型放 `src/shared/types`，feature 私有类型就近放 `model/` 或 `types.ts`；禁止用 `as` 绕过校验，接口与 Agent 响应先运行时校验再断言。

## 样式

- 设计依据是 `docs/services/frontend/ui-design-system.md`；Token 定义在 `src/styles/cds-theme.css`，`src/styles/main.css` 只做 `@theme inline` 映射。
- 颜色、间距、圆角、字号用 CSS 变量或 Tailwind 语义类；禁止硬编码 hex 与任意值。
- 控件高度只取 23 / 26 / 32 / 40px，圆角只取 6 / 8px（按钮）或对应 Token；布局优先 `flex` / `grid`。
- 类名 kebab-case；禁止行内 `style`（运行时计算值除外）与 `!important`（覆盖第三方需注明原因）。

## 构建与环境

- 命令统一 `corepack pnpm ...`（cwd `frontend`）；生产构建必须通过 `check:env --mode production`，失败禁止绕过。
- `VITE_*` 在构建期写入静态文件，变更后必须重建镜像，不能只重启容器。
- 本地 `.env.*` 不提交；Docker 通过 build args 注入，`.dockerignore` 已排除 env 文件。
- 不写死 `localhost`、容器名或生产域名；代理路径以 Nginx 模板为准。

## 性能

- 路由与大型组件按需加载；长列表用 Query 分页或虚拟滚动。
- 图片指定宽高并懒加载；输入、滚动、`resize` 等高频事件防抖或节流。
- 依赖数组完整；卸载时清理订阅、定时器与 `AbortController`；避免无依据堆叠 `useMemo` / `useCallback`。
- 优化前先测量（React Profiler、构建体积、`test:coverage`），用数据说明瓶颈。

## 安全

- 模型与用户 Markdown 经 `react-markdown` 白名单渲染，默认关闭原始 HTML；禁止用 `dangerouslySetInnerHTML` 渲染未净化内容。
- 禁止在代码、注释、提交信息中写密钥、Token、内网地址。
- 外链加 `rel="noopener noreferrer"`；用户输入提交前做格式与长度校验。
- 敏感信息不进 URL 查询参数；Token 只存内存、刷新令牌仅 HttpOnly Cookie；前端权限判断不作为安全边界。

## 质量门禁

- 提交前必须通过 `corepack pnpm lint:ci`、`type-check`、`test`；合并前 `e2e:critical`（`--grep @critical`）必须全绿。
- `test:coverage` 门槛 lines ≥ 80%（覆盖 `core/http`、业务 api、`chat/runtime`、`routes`），禁止用低价值代码堆总体覆盖率。
- 单文件不超过 300 行，函数不超过 50 行；不提交 `console.log`、`debugger` 与无理由的 `eslint-disable`。
- 不引入未经确认的第三方依赖；`verify` 为本机全量自检（lint:ci + type-check + test + build-only）。
- 单测不得依赖开发者本机 `.env.local`：涉及地址、开关的用例必须 `vi.mock('@/shared/lib/env')` 固定契约默认值，禁止改断言迁就本机配置。
- 断言优先用语义元素（`role`、`link`、`label`）与路由 `pathname`，不绑易变文案；E2E mock 先按 `URL.pathname` 归一化代理前缀，通配使用 `**/api/v*/**`。
- 重构后必须跑全量 vitest，不得只跑改动文件的 spec：环境与配置类失败只在全量执行时暴露。
