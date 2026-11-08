# 前端（frontend）

Agent 对话工作台的前端：欢迎页、工作台、对话、历史、设置与登录，负责界面、路由与 SSE 流式消费。

技术栈：React 19 + TypeScript 6 + Vite 8 + TanStack Router/Query + Zustand + Tailwind/Radix。运行时 Node `^22.18.0` 或 `>=24.12.0`，包管理器 pnpm `10.18.0`（统一用 `corepack pnpm`）。

## 快速开始

```bash
corepack pnpm install
cp .env.example .env.local     # 按本地后端地址改 VITE_API_BASE_URL
corepack pnpm dev
```

本地联调：先以 `local` profile 启动 `application-service`（默认放开 `http://localhost:5173` 跨域），用其 `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD` 登录。

## 常用命令

```bash
corepack pnpm dev             # 开发服务器
corepack pnpm build           # 类型检查 + 生产构建
corepack pnpm type-check      # tsc -b
corepack pnpm lint:ci         # oxlint + eslint（只检查，不改文件）
corepack pnpm test            # vitest run
corepack pnpm test:coverage   # 覆盖率门禁（lines ≥ 80%）
corepack pnpm e2e             # Playwright；e2e:critical 只跑 @critical
corepack pnpm check:env       # 校验构建所需环境变量
```

`corepack pnpm lint` 带 `--fix`，会改写源码；只检查时用 `corepack pnpm lint:ci`。

## 文档入口导航

契约与开发约定的唯一权威在仓库根 `docs/`，本目录不再重复：

| 文档 | 内容 |
| --- | --- |
| [`README.md`](../README.md) | 项目定位、目录结构、启动命令与文档总入口 |
| [`docs/README.md`](../docs/README.md) | 文档地图与信息状态标签 |
| [`docs/architecture-overview.md`](../docs/architecture-overview.md) | 三端职责、拓扑与信任边界 |
| [`docs/services/frontend/architecture.md`](../docs/services/frontend/architecture.md) | 路由、目录职责、数据流、状态、环境变量、已知偏差 |
| [`docs/services/frontend/development-guide.md`](../docs/services/frontend/development-guide.md) | 命令、命名、新增页面/接口、SSE 扩展、提交门禁 |
| [`docs/api-contract.md`](../docs/api-contract.md) | 跨端 HTTP 与 SSE 契约（含 Agent 直连与 SSE 事件定义） |
| [`docs/services/frontend/ui-design-system.md`](../docs/services/frontend/ui-design-system.md) | UI Token 与组件规范 |
| [`.trae/rules-on-demand/10-frontend.md`](../.trae/rules-on-demand/10-frontend.md) | 前端编码硬约束 |

## 注意

- 登录态与角色由全局守卫统一处理（`src/routes/guards.ts`），页面内不重复判权。
- `VITE_*` 会在构建期写入静态产物：禁止写入密钥；修改后必须重新构建镜像。
