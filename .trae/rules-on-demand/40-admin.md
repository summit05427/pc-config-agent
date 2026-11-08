# 管理端规则（admin/**）

适用范围：仅 `admin/**`。其他目录忽略本文件；公共约束见 `00-monorepo-common.md`。

技术栈：React 19 + TypeScript 6 + Vite 8 + TanStack Router（文件式路由 + 自动代码分割）+ TanStack Query + Zustand + Tailwind v4 + shadcn/ui（Radix UI）+ react-hook-form + zod + Vitest 4（browser mode）。

## 定位与边界

- `admin/` 是运营管理端，只面向 `ADMIN` 角色；不得复制用户端页面，也不在管理端实现用户端功能。
- 只调用 Java `/api/v1/admin/**` 与 `/api/v1/auth/**`；不调用 Agent、不连接任何数据库、不持有模型密钥。
- 已落地范围：登录、用户管理（状态/角色）、审计日志查询、模型目录与定价维护（模型 / Provider 启停、定价版本）、用量与成本查询（KPI 汇总 + 明细过滤）、模型连接只读视图；新增板块前先确认后端 admin 接口已落地。
- 生产入口为 frontend Nginx 的 `/admin/`（剥离前缀后转发到 `admin:80`），接口仍走同源 `/api/`；本地开发走 Vite `5174` 的 `/api` 代理。

## 目录职责

- `src/core/http`：HTTP 门面（信封解包、错误归一、401 单飞刷新）；业务代码禁止直接使用 `axios` / `fetch`。
- `src/features/<domain>`：按域聚合 `api/`（queryOptions 与 mutation）与 `components/`；跨域只经对方 `api/` 引用。
- `src/routes`：文件式路由，`(auth)` 与 `_authenticated` 分组；`routeTree.gen.ts` 由插件生成，禁止手改。
- `src/components`：`layout/`（壳层）、`ui/`（shadcn 封装）与通用组件；`src/stores` 只放认证会话；`src/lib` 放纯函数与环境变量。
- 依赖方向：`core` / `lib` / `stores` 不依赖 `features`；`features` 不依赖 `routes`；跨目录一律用 `@/` 别名。
- 阅读顺序：[docs/README.md](../../docs/README.md) → `docs/services/admin/architecture.md` → `development-guide.md`；改接口先读 `docs/api-contract.md` §5.1。

## 认证与会话

- 访问令牌只存内存（`src/stores/auth-store.ts`），禁止写入 `localStorage` / `sessionStorage` / 普通 Cookie；刷新令牌只由 Java 下发的 HttpOnly Cookie 承载，前端不得读取。
- 会话恢复统一走 `ensureSession()`：先 `refreshAccessToken()` 换令牌，再 `GET /auth/me`；任一步失败即清理会话。
- 401 由 `src/core/http/client.ts` 单飞刷新并重放一次；登录、登出、刷新三条路径不重试，避免刷新死循环。
- 角色判断只用于交互与路由跳转（`hasRole`），真实权限边界在 Java 服务端；禁止把前端判断当安全措施。
- 登出先调用 `/auth/logout` 撤销服务端会话，失败也继续本地清理并跳登录页。
- 开发代理必须 `changeOrigin: false`：Java 对 refresh / logout 校验 Origin 与 Host 同源，改写 Host 会直接 403。

## API 层

- 请求统一经 `httpJson`；按域放 `src/features/<domain>/api/`，查询用 `queryOptions`，变更用 mutation。
- 接口必须有显式请求与响应类型；响应体用 zod 校验后再收窄，禁止 `any` 与裸 `as` 断言。
- Query key 统一登记在 `src/lib/query-keys.ts`，按域保留 `all` 前缀；组件禁止手写数组字面量。
- 查询参数放路由 search（`validateSearch` + zod，带 `.catch()` 兜底），不要复制到组件局部 state。
- 分页参数遵守后端约定：`page` 默认 1、`size` 默认 20、上限 100；分页与过滤全部由后端完成。
- 错误经 `ApiError` / `getHttpErrorMessage` 处理；禁止静默 catch（登出的本地兜底除外，必须注释原因）。
- 环境变量只从 `src/lib/env.ts` 读取，禁止业务代码直接访问 `import.meta.env`。

## 路由与状态

- 新增页面必须在 `src/routes/` 建文件，并同步 `components/layout/data/sidebar-data.ts` 与命令面板。
- `_authenticated/route.tsx` 是唯一登录守卫；页面内不重复判断登录态或角色。
- 服务端数据只进 TanStack Query；认证会话进 Zustand；其余组件状态用 `useState`。
- 禁止在 `useEffect` 里发起请求；查询由事件或 Query 触发。跨路由保留的筛选条件只从 search 取。
- 列表 `key` 用稳定唯一 ID；禁止用数组下标，禁止前端拉全量再筛选。

## UI 与文案

- `src/components/ui/**` 为 shadcn 生成封装，保持原结构；业务定制写在业务组件内，不直接改生成文件语义。
- 文案统一简体中文；标题、按钮、空态、错误提示不得中英混排（协议字段名除外）。
- 颜色、间距、圆角用 Tailwind 语义类或 CSS 变量；禁止硬编码 hex、行内 `style` 与 `!important`。
- 破坏性操作必须有二次确认（`ConfirmDialog`），确认按钮写清动作（如「退出登录」「禁用账号」）。
- 表单用 react-hook-form + zod；提交时禁用按钮并展示 loading，失败用 toast 呈现可读消息。

## 命名

- 文件 kebab-case；组件导出 PascalCase，一个文件一个组件；测试与被测文件同名。
- 变量与函数 camelCase，类型 PascalCase，常量 SCREAMING_SNAKE_CASE；布尔值用 `is` / `has` / `can` 前缀。
- 业务枚举与后端字符串保持一致（如 `ACTIVE` / `DISABLED`），展示文案用本地映射表，不改协议值。

## 构建与环境

- 命令统一 `corepack pnpm --dir admin ...`（或 cwd `admin`）；`VITE_*` 在构建期写死，修改后必须重新构建。
- `VITE_API_BASE_URL` 默认 `/api/v1`；`VITE_BASE_PATH` 默认 `/`，生产镜像由 Compose 注入 `/admin/`，必须与 Nginx 代理前缀一致（同时驱动 Vite `base` 与 Router `basepath`）；`VITE_API_PROXY_TARGET` 只用于本地开发代理，不进入客户端产物。
- 不写死 `localhost`、容器名或生产域名；`index.html` 保持 `noindex,nofollow`。

## 质量门禁

- 提交前必须通过 `lint:ci`、`type-check`、`test`、`build`；禁止 `eslint-disable` 与降低断言换取通过。
- 测试用 Vitest browser mode；首次需 `playwright install chromium --with-deps`，UI 断言优先按可访问角色定位。
- 新增页面至少覆盖：成功、参数非法、未登录跳转、非 ADMIN 跳转；变更操作覆盖成功与失败提示。
- 不引入未经确认的第三方依赖；优先复用现有 shadcn 组件与 `src/lib` 工具函数。
