# 管理后台（admin）

Agent 平台的运营管理端，基于 [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin) v2.2.1 模板改造。

当前范围：管理员登录、用户管理（状态与角色）、审计日志查询、模型目录与定价维护（模型 / Provider 启停、定价版本新增）、用量与成本查询（KPI 汇总 + 明细过滤）、模型连接只读视图（掩码与验证时间）。

## 技术栈

- React 19 + TypeScript 6 + Vite 8
- TanStack Router（文件式路由 + 自动代码分割）
- TanStack Query（服务端数据与缓存）
- Tailwind CSS v4 + shadcn/ui（Radix UI）
- Zustand（仅存内存中的认证会话）
- react-hook-form + zod
- Vitest 4（browser mode，Playwright chromium）

## 环境要求

- Node.js 20+ 与 pnpm（仓库根通过 `corepack` 固定版本）
- 本机可访问 `application-service`（默认 `http://localhost:8080`）
- 首次运行测试前安装浏览器：`corepack pnpm --dir admin test:browser:install`

## 本地启动

```powershell
# 仓库根执行
corepack pnpm --dir admin install

# 复制环境变量模板（首次）
Copy-Item admin\.env.example admin\.env

corepack pnpm --dir admin dev
```

开发服务器端口 `5174`，`/api` 通过 Vite 代理转发到 `VITE_API_PROXY_TARGET`，
因此登录、刷新、退出与 Java 服务保持同源，HttpOnly 刷新 Cookie 可正常往返。

## 常用命令

```powershell
corepack pnpm --dir admin lint:ci
corepack pnpm --dir admin type-check
corepack pnpm --dir admin test
corepack pnpm --dir admin build
```

## 配置项

| 变量 | 说明 |
| --- | --- |
| `VITE_APP_TITLE` | 浏览器标题与侧边栏标题 |
| `VITE_API_BASE_URL` | 接口基地址，默认 `/api/v1` |
| `VITE_BASE_PATH` | 部署前缀，默认 `/`；生产镜像由 Compose 传 `/admin/` |
| `VITE_API_PROXY_TARGET` | 仅本地开发使用的代理目标，不进入客户端产物 |

`VITE_*` 在构建期写入静态文件，修改后必须重新构建，重启进程无效。

## 生产部署

管理端不单独对外，浏览器通过 frontend Nginx 的同源 `/admin/` 访问，接口仍走 `/api/`。

```bash
# 仓库根执行
docker compose --profile full --env-file .env up -d --build admin
docker compose restart frontend   # 重建 admin 后必须重启，Nginx 缓存了上游主机解析
curl -fsS http://localhost/admin/healthz
```

- 镜像由 `admin/Dockerfile` 构建（`node:24-alpine` → `nginx:stable-alpine`），容器内端口 `80`，不映射宿主机端口。
- 静态托管使用独立配置 [deploy/nginx/default.conf](deploy/nginx/default.conf)，只做静态文件、`/healthz` 与 SPA 回退。
- `VITE_BASE_PATH=/admin/` 由 Compose 作为构建参数注入，必须与 Nginx `/admin/` 前缀一致；本地开发保持 `/`。
- 路由、构建判定与回滚见 [部署指南](../docs/deployment/deployment-guide.md) §3 / §4 / §6。

## 认证与安全约定

- 访问令牌只存内存（Zustand），不写 Cookie/localStorage；页面刷新后用 HttpOnly 刷新 Cookie 换新令牌。
- 刷新令牌仅存在于 HttpOnly Cookie，前端代码不读取。
- 所有请求经 `src/core/http`，401 由请求层单飞刷新并重放一次；刷新失败跳登录页。
- 路由守卫集中在 `src/routes/_authenticated/route.tsx`，非 ADMIN 角色访问管理页面跳 `/403`。
- 前端角色判断只用于交互与跳转，真正的权限边界在 Java 服务端。

## 目录结构

```
src/
  core/http/          HTTP 门面：信封解包、401 单飞刷新、错误归一
  features/
    auth/             登录接口、登录页
    admin-users/      用户管理（服务端分页、状态与角色变更）
    audit-logs/       审计日志查询
    models/           模型目录与定价（启停、定价版本历史与新增）
    usage/            用量与成本（KPI 汇总、明细过滤与服务端分页）
    model-connections/ 用户模型连接只读视图（掩码、验证时间、凭证状态）
    errors/           400/403/404/500/503 静态错误页
  components/         布局、通用组件与 shadcn/ui 封装
  routes/             TanStack Router 文件式路由
  stores/             Zustand 状态（认证会话）
  lib/                环境变量、Query key、格式化等纯函数
```

## 接口依赖

与 `application-service` 的契约见根文档：

- [接口契约](../docs/api-contract.md)
- [Java 接口清单](../docs/services/application-service/api-reference.md)
- [管理端架构说明](../docs/services/admin/architecture.md)
- [管理端开发指南](../docs/services/admin/development-guide.md)

## 说明

模板原有演示模块（Dashboard / Tasks / Apps / Chats / Settings）、Clerk 集成与客户端表格已移除；
新增页面请遵循 [.trae/rules-on-demand/40-admin.md](../.trae/rules-on-demand/40-admin.md)。
