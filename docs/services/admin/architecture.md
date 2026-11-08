# 管理端（admin）架构

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-02 |
| 权威性 | 服务事实说明（管理端内部结构、认证与数据流） |
| 主要证据 | `admin/package.json`、`admin/vite.config.ts`、`admin/src/core/http/client.ts`、`admin/src/routes/_authenticated/route.tsx`、`admin/src/features/models/`、`admin/src/features/usage/`、`admin/src/features/model-connections/`、`admin/Dockerfile`、`admin/deploy/nginx/default.conf` |

适用范围：`admin/**`。跨端路径、字段与错误码以 [api-contract.md](../../api-contract.md) 为准，本文不重复定义；用户端说明见 [services/frontend/architecture.md](../frontend/architecture.md)。

## 1. 定位与边界

管理端是面向 `ADMIN` 角色的运营后台，独立于用户端 `frontend/`，基于 [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin) v2.2.1 模板改造（已验证，`admin/README.md`、`admin/package.json`）。

| 项 | 事实 |
| --- | --- |
| 技术栈 | React 19 + TypeScript 6 + Vite 8 + TanStack Router（文件式路由 + 自动代码分割）+ TanStack Query + Zustand + Tailwind v4 + shadcn/ui |
| 职责 | 管理员登录、用户管理（状态 / 角色）、审计日志查询、模型目录与定价维护 |
| 明确不做 | 不调用 Agent、不连接数据库、不持有模型密钥、不实现用户端功能 |
| 后端依赖 | 仅 Java `/api/v1/auth/**` 与 `/api/v1/admin/**`（`SecurityConfig` 对 `/api/v1/admin/**` 要求 `ADMIN`） |
| 当前端口 | 本地开发 `5274`（`admin/vite.config.ts`）；容器内 `80`，经 frontend Nginx 的 `/admin/` 暴露 |
| 生产入口 | 与用户端同源：浏览器访问 `/admin/`，frontend Nginx 剥掉前缀后转发到 `admin:80`，接口仍走 `/api/` |

**部署状态**：已接入 frontend Nginx `/admin/` 与 Compose `admin` 服务（2026-11-01，D-09）：`admin/Dockerfile` 构建静态产物，`admin/deploy/nginx/default.conf` 负责静态托管与 SPA 回退，frontend 模板用 `proxy_pass ${ADMIN_UPSTREAM}/` 剥掉 `/admin` 前缀。构建期 `VITE_BASE_PATH=/admin/` 同时驱动 Vite `base` 与 TanStack Router `basepath`，三者必须一致。详见 [deployment/deployment-guide.md](../../deployment/deployment-guide.md) §3 / §4。

## 2. 目录结构

| 目录 | 职责 |
| --- | --- |
| `src/core/http/` | HTTP 门面：`httpClient`（axios 实例）、信封解包、错误归一、401 单飞刷新、`httpJson` |
| `src/features/auth/` | 登录接口（zod 校验）、登录页与表单 |
| `src/features/admin-users/` | 用户列表、状态与角色变更、角色编辑弹窗 |
| `src/features/audit-logs/` | 审计日志列表与事件过滤 |
| `src/features/models/` | 模型目录（启停）、Provider 启停、定价版本历史与新增定价弹窗 |
| `src/features/usage/` | 跨用户用量与成本：KPI 汇总、成本状态分布、Provider / 模型 Top 5、明细分页与多条件过滤 |
| `src/features/model-connections/` | 用户 BYOK 连接只读视图：连接状态、最近验证时间、凭证掩码与状态 |
| `src/features/errors/` | 401 / 403 / 404 / 500 / 503 静态错误页 |
| `src/components/` | `layout/` 壳层（侧边栏、头部、命令面板）、`ui/`（shadcn 封装）与通用组件 |
| `src/routes/` | TanStack Router 文件式路由；`routeTree.gen.ts` 由插件生成 |
| `src/stores/` | Zustand：仅认证会话 |
| `src/lib/` | 环境变量（`env.ts`）、Query key、格式化与重定向校验等纯函数 |

依赖方向：`routes → features → core/http`；`core`、`lib`、`stores` 不依赖 `features`。跨目录统一用 `@/` 别名。

## 3. 认证与会话（已验证）

登录与刷新契约见 [api-contract.md](../../api-contract.md) §5，服务端实现见 [application-service/security.md](../application-service/security.md)。

```text
登录：POST /api/v1/auth/login
      → 返回 { accessToken, tokenType, expiresIn, user }
      → accessToken 只写内存（Zustand），刷新令牌由服务端写入 HttpOnly Cookie

启动 / 守卫：ensureSession()
      → 内存无令牌时 POST /auth/refresh（Cookie 自动携带）
      → GET /auth/me 拉取 { publicId, username, roles }
      → 任一步失败：auth.reset()，视为未登录

401：src/core/http/client.ts 单飞刷新 → 成功后重放原请求一次
      → 刷新失败：reset() + unauthorizedHandler()（跳登录页）
      → /auth/login、/auth/logout、/auth/refresh 不参与重试
```

关键约束：

- 访问令牌不落 `localStorage` / `sessionStorage` / 普通 Cookie（`src/stores/auth-store.test.ts` 有断言）。
- 刷新令牌前端不可读；页面刷新后依靠 HttpOnly Cookie 恢复会话。
- 登出先 `POST /auth/logout` 撤销服务端会话并清 Cookie；失败不阻塞本地清理与跳转（`src/components/sign-out-dialog.tsx`）。
- Vite 代理必须 `changeOrigin: false`：Java `RequestOriginValidator` 对 refresh / logout 校验来源，改写 `Host` 会被判为跨域。

## 4. 路由与守卫

| 路径 | 文件 | 行为 |
| --- | --- | --- |
| `/sign-in` | `src/routes/(auth)/sign-in.tsx` | 登录页；已登录且为 `ADMIN` 时跳 `/users` |
| `/`（`_authenticated`） | `src/routes/_authenticated/route.tsx` | 统一守卫：未登录跳 `/sign-in`（带 `redirect`）；非 `ADMIN` 跳 `/403` |
| `/` | `src/routes/_authenticated/index.tsx` | 重定向到 `/users`，保留完整 search 参数 |
| `/users` | `src/routes/_authenticated/users/index.tsx` | 用户管理；search：`page` / `size` / `keyword` / `status` |
| `/audit-logs` | `src/routes/_authenticated/audit-logs/index.tsx` | 审计日志；search：`page` / `size` / `event` / `username` |
| `/models` | `src/routes/_authenticated/models/index.tsx` | 模型与定价；search：`page` / `size` / `keyword` / `provider` / `enabled` |
| `/usage` | `src/routes/_authenticated/usage/index.tsx` | 用量与成本；search：`page` / `size` / `userId` / `provider` / `modelKey` / `credentialSource` / `costStatus` / `status` / `from` / `to` / `order` |
| `/model-connections` | `src/routes/_authenticated/model-connections/index.tsx` | 模型连接只读；search：`page` / `size` / `userId` / `provider` / `status` |
| `/401`、`/403`、`/404`、`/500`、`/503` | `src/routes/(errors)/*` | 静态错误页 |

- `validateSearch` 用 zod 校验，并对非法值做 `.catch()` 兜底，避免手改 URL 导致页面崩溃。
- 守卫只做「恢复会话 + 角色判断 + 重定向」，不在 loader 重复实现 HTTP 与错误处理。
- 侧边栏与命令面板共用 `src/components/layout/data/sidebar-data.ts`；新增页面必须同步两处。

## 5. 数据获取与页面能力

| 页面 | 接口 | 交互 |
| --- | --- | --- |
| 用户管理 | `GET /api/v1/admin/users` | 关键字（回车触发）、状态过滤、每页条数、服务端分页 |
| 用户管理 | `PATCH /api/v1/admin/users/{publicId}/status` | 启用 / 禁用；成功后 `invalidateQueries` 刷新列表 |
| 用户管理 | `PATCH /api/v1/admin/users/{publicId}/roles` | 角色弹窗勾选 `USER` / `ADMIN`，提交后刷新列表 |
| 审计日志 | `GET /api/v1/admin/audit-logs` | 事件类型下拉（8 类白名单）、用户名精确过滤、服务端分页 |
| 模型与定价 | `GET /api/v1/admin/models` | 关键字（回车或失焦触发）、Provider 选择、启用状态、每页条数；行内展示能力、上下文、状态与最近定价 |
| 模型与定价 | `PATCH /api/v1/admin/models/{provider}/{modelKey}/status` | 启用直接提交；停用走 `ConfirmDialog` 二次确认；成功后刷新列表 |
| 模型与定价 | `GET /api/v1/admin/model-providers` | Provider 卡片展示启用状态与模型数量（含启用数） |
| 模型与定价 | `PATCH /api/v1/admin/model-providers/{code}/status` | 停用 Provider 需二次确认；停用后其下模型行显示「Provider 已停用」 |
| 模型与定价 | `GET /api/v1/admin/models/{provider}/{modelKey}/pricing` | 定价弹窗上半部分：版本历史，按生效时间倒序 |
| 模型与定价 | `POST /api/v1/admin/models/{provider}/{modelKey}/pricing` | 定价弹窗下半部分：react-hook-form + zod 新增版本；成功后 `reset()` 并刷新列表 |
| 用量与成本 | `GET /api/v1/admin/model-usage` | 明细表：用户 ID（回车/失焦）、Provider、模型标识、凭证来源、成本状态、调用结果、起止日期（UTC 自然日）、排序与每页条数；全部由服务端过滤与分页 |
| 用量与成本 | `GET /api/v1/admin/model-usage/summary` | 顶部 KPI 与分布；只按 Provider、模型、凭证来源与日期聚合，页面明示不受用户、成本状态与结果筛选影响 |
| 模型连接 | `GET /api/v1/admin/model-connections` | 只读表：用户、Provider、接入地址、连接状态、最近验证时间、当前凭证掩码与状态；无创建 / 验证 / 删除入口 |

- 响应体在 `features/*/api/*.ts` 内用 zod 校验后再交给页面，字段变更会显式失败而不是静默透传。
- Query key 统一登记在 `src/lib/query-keys.ts`：`admin-users`、`audit-logs`、`admin-models`、`model-providers`、`admin-usage`、`admin-connections` 六组，列表与聚合 key 附带完整查询参数。
- 用量页的汇总与明细是两条独立缓存：汇总只接受 Provider / 模型 / 凭证来源 / 日期，明细额外接受用户、成本状态与结果；不要用明细数据推导汇总，避免口径漂移。
- 多币种费用由后端置空，页面区分「多币种」与「暂无定价」，不对不同币种求和；无数据时卡片显示 0 或「待建设」，不造假。
- 连接页只渲染 `maskedHint` 与凭证状态，密文与明文在前端类型上就不存在。
- 空态、加载态与错误态均由页面组件显式渲染，不用假数据填充。
- 定价只提供「新增版本」，不提供编辑或删除：后端以 `(provider, modelKey, effectiveFrom)` 唯一且只追加，历史用量成本不会被重算；冲突时展示后端 409 `40221` 的可读消息。
- Provider 是受控的小基数目录，前端不做分页与前端过滤，直接消费后端全量列表。

## 6. 已知边界

- 构建期 `VITE_BASE_PATH` 必须与 Nginx `/admin/` 前缀一致；它只在构建期写入静态产物，改后必须重建镜像，重启容器无效。
- 已实现模型目录与定价维护（D-05，2026-11-01）：模型 / Provider 启停、定价版本历史与新增定价，接口见 [api-contract.md](../../api-contract.md) §5.1。
- 未实现用量与调用记录、Dashboard 聚合、模型连接只读视图（D-06 ~ D-08），后端对应 admin 接口尚未提供。
- 管理端暂无 E2E 用例；门禁为 `lint:ci`、`type-check`、Vitest browser mode 单测、`build`。
- 模板残留的空目录（`features/{apps,chats,dashboard,settings,tasks}`、`routes/clerk`）未纳入 Git，不影响构建。
