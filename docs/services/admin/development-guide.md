# 管理端开发指南

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-01 |
| 权威性 | 服务规范（管理端命令、环境变量、扩展步骤与门禁） |
| 主要证据 | `admin/package.json`、`admin/.env.example`、`admin/vite.config.ts` |

适用范围：`admin/**`。编码硬约束见 [.trae/rules-on-demand/40-admin.md](../../../.trae/rules-on-demand/40-admin.md)；结构与认证流程见 [architecture.md](architecture.md)。

## 1. 环境要求

- Node.js 20+；pnpm 由仓库根 `packageManager` 固定，统一用 `corepack pnpm`。
- 本机可访问 `application-service`（默认 `http://localhost:8080`）。
- 首次运行测试前安装浏览器：`corepack pnpm --dir admin test:browser:install`（Playwright chromium）。

## 2. 安装与启动

```powershell
# 仓库根执行
corepack pnpm --dir admin install

# 首次复制环境变量模板
Copy-Item admin\.env.example admin\.env

corepack pnpm --dir admin dev
```

开发服务器固定 `5274`；`/api` 由 Vite 代理到 `VITE_API_PROXY_TARGET`，且 `changeOrigin: false`，保留浏览器原始 `Host`，Java 的 refresh / logout 来源校验才能通过。

## 3. 命令与门禁

```powershell
corepack pnpm --dir admin lint:ci       # eslint --max-warnings 0
corepack pnpm --dir admin type-check    # tsc -b
corepack pnpm --dir admin test          # Vitest browser mode（headless）
corepack pnpm --dir admin build         # tsc -b && vite build
```

- 提交前四条全部通过；CI 的 `admin` job 与本地命令保持一致。
- `test:coverage` 可查看覆盖率，但未设硬阈值；新增代码以页面分支与错误路径覆盖为主，不堆低价值代码。
- 禁止用 `eslint-disable`、跳过用例或降低断言换取通过。

## 4. 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `VITE_APP_TITLE` | 否 | 浏览器标题与侧边栏标题，默认「Agent 管理后台」 |
| `VITE_API_BASE_URL` | 否 | 接口基地址，默认 `/api/v1` |
| `VITE_BASE_PATH` | 否 | 部署前缀，默认 `/`；生产镜像由 Compose 传 `/admin/`，同时作为 Vite `base` 与 Router `basepath` |
| `VITE_API_PROXY_TARGET` | 否 | 仅本地开发代理目标，默认 `http://localhost:8080`，不进入客户端产物 |

- 环境变量只从 `src/lib/env.ts` 读取，由 zod 校验；业务代码禁止直接访问 `import.meta.env`。
- `VITE_*` 在构建期写入静态文件，修改后必须重新构建，重启进程无效。
- 真实 `.env` 不提交；`.env.example` 变更时同步本表与 `admin/README.md`。

## 5. 新增一个页面

1. 确认后端接口已在 `docs/api-contract.md` §5.1 登记且已实现；未实现的接口不得在页面中调用。
2. 在 `src/features/<domain>/api/` 写请求函数与 `queryOptions`，响应体加 zod Schema。
3. 在 `src/lib/query-keys.ts` 登记域级 `all` key；列表 key 用 `[...all, 'list', params]`。
4. 在 `src/routes/_authenticated/<path>/index.tsx` 建路由文件，用 `validateSearch` + zod 收窄查询参数。
5. 页面组件放 `src/features/<domain>/components/`；空态、加载态、错误态与分页显式渲染。
6. 同步 `src/components/layout/data/sidebar-data.ts` 与命令面板导航项。
7. 补测试：成功、参数非法、未登录跳转、非 ADMIN 跳转；变更操作覆盖成功与失败提示。

## 6. 新增一个接口调用

- 请求必须经 `src/core/http` 的 `httpJson`，禁止在组件或 feature 中直接使用 `axios` / `fetch`。
- 请求与响应都要有显式类型；响应先 zod 校验再收窄，禁止 `any` 与裸断言。
- 查询用 `queryOptions`，变更用 mutation；成功后按域前缀 `invalidateQueries`。
- 错误统一经 `ApiError` / `getHttpErrorMessage`；禁止静默 catch（登出的本地兜底需注释原因）。
- 401 由请求层处理，feature 不重复实现刷新逻辑。

## 7. 样式与组件

- 复用 `src/components/ui/**` 的 shadcn 封装；新增基础组件优先通过 shadcn 生成，不在业务组件里重造。
- 文案统一简体中文；破坏性操作使用 `ConfirmDialog` 并写清动作。
- 颜色、间距、圆角用 Tailwind 语义类或 CSS 变量；禁止硬编码 hex、行内 `style` 与 `!important`。
- 表格与分页由 `src/components/pagination-bar.tsx` 与业务表格组件组合，分页与过滤在后端完成。

## 8. 认证相关改动

改动登录、刷新、登出、守卫时，按 [development-rules.md](../../development-rules.md) §1 检查：

- Java：`identity/**/security/**`、`RefreshSessionService`、`RefreshCookieFactory`、`RequestOriginValidator`。
- 管理端与用户端：两套 `core/http` 与认证 store 都要同步，行为保持一致。
- 契约文档：[api-contract.md](../../api-contract.md) §5；安全细节：[application-service/security.md](../application-service/security.md)。
- 验证：登录、刷新页面恢复会话、401 自动刷新、登出、非 ADMIN 访问 `/users` 跳 `/403`。

## 9. 部署

已接入 Compose（D-09，2026-11-01），浏览器同源访问 `http://<host>/admin/`，接口仍走 `/api/`。

```bash
# 仓库根执行；只改管理端时按需重建
docker compose --profile full --env-file .env up -d --build admin
docker compose restart frontend     # 重建 admin 后必须重启，Nginx 会缓存上游主机解析
curl -fsS http://localhost/admin/healthz
```

- 镜像：`admin/Dockerfile`（`node:24-alpine` 构建 → `nginx:stable-alpine` 运行），容器内端口 `80`，不映射宿主机端口。
- 构建参数 `VITE_BASE_PATH=/admin/` 由 Compose 注入，必须与 frontend 模板的 `/admin/` 前缀一致；本地开发保持 `/`，否则访问地址会变成 `http://localhost:5274/admin/`。
- admin 容器使用独立 Nginx 配置 `admin/deploy/nginx/default.conf`，只做静态托管、`/healthz` 与 SPA 回退，不反向代理。
- 完整路由、构建判定与回滚流程见 [deployment/deployment-guide.md](../../deployment/deployment-guide.md) §3 / §4 / §6；变量登记见 [environment-variables.md](../../deployment/environment-variables.md) §2.13。
