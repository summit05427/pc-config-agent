# agent-project-template

React 19 前端 + React 管理端 + Spring Boot 业务后端 + FastAPI Agent 服务的 Monorepo 模板。

## 目录结构

```text
agent-project-template/
├── frontend/              # React 19 + TypeScript + Vite（容器内 Nginx 静态托管与代理）
├── admin/                 # React 19 + TanStack Router 管理后台（经 Nginx /admin/ 托管）
├── application-service/   # Java 21 + Spring Boot 4 + PostgreSQL
├── agent-service/         # Python 3.12 + FastAPI + LangGraph
├── deploy/                # 本地基础设施 compose（可选）
├── docs/                  # 跨服务配置与部署文档
├── docker-compose.yml     # 四端 + 依赖中间件的一体化编排
└── .github/workflows/     # 按路径触发的 CI
```

## 快速开始

1. 复制环境变量模板并替换所有 `replace-with-*`：

    ```bash
    cp .env.example .env
    ```

2. 本地只启动数据库等基础设施：

    ```bash
    docker compose --env-file .env up -d postgres pgvector redis
    ```

3. 一键启动四端（脚本从根 `.env` 注入变量、校验数据库口令后并行拉起）：

    ```powershell
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-local.ps1
    ```

    管理端独立启动（默认启动范围不含管理端）：

    ```powershell
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/start-local.ps1 -Service admin -SkipMiddleware
    ```

    停止：

    ```powershell
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev/stop-local.ps1
    ```

    各端手工启动命令见 [部署指南](docs/deployment/deployment-guide.md) §2。

4. 一体化启动（构建四个镜像 + 三个中间件）：

    ```bash
    docker compose --profile full up -d --build
    ```

    启动后：用户端 `http://localhost/`、管理端 `http://localhost/admin/`，接口经同源 `/api/` 与 `/agent/`；端口由 `WEB_PORT` 控制。

    `application-service`、`admin`、`frontend` 与中间件都归属 profile（中间件为 `infra` / `full`，三端为 `full`）；`agent-service` 无 profile，因此不带 `--profile` 的 `docker compose up -d` 只会启动 Agent 一个容器。

5. Solo 模式（只跑 Agent，不装 Java / 中间件）：

    ```bash
    uv --directory agent-service run python ../scripts/generate_solo_env.py
    # 编辑 .env.solo，填入 LLM_API_KEY
    docker compose --env-file .env.solo up -d --build agent-service
    ```

    Agent 使用 memory 存储、关闭 Redis，并附带本地自签 RSA 公钥与私钥；`APP_ENV=dev` + `DEBUG=true` 时会开放 `/api/v1/auth/dev-token` 用于直接对话。切换回整栈时需先 `docker compose --env-file .env.solo stop agent-service`，否则端口 8000 会冲突。

## 文档

各端公共契约与各服务文档统一在 [docs/README.md](docs/README.md)（文档地图）。常用入口：

- [总体架构](docs/architecture-overview.md)：职责边界、部署拓扑、调用关系与未实现能力
- [API 与 SSE 契约](docs/api-contract.md)：路径前缀、鉴权、响应信封、错误码、跨端对照
- [跨端开发规则](docs/development-rules.md)：变更影响矩阵、验证命令与评审要求
- [文档管理规范](docs/documentation-governance.md)：文档分类、目录命名、状态标注与变更流程

## 安全提示

- `.env`、各服务的真实 env 文件、日志与构建产物均已被忽略，禁止提交。
- `VITE_` 前缀变量会被打包进浏览器产物，只能放公开配置。
- 生产环境必须配置真实 RSA 密钥对（`JWT_PRIVATE_KEY` 只给 Java，`JWT_PUBLIC_KEY` 与 Agent 共享）与数据库口令，否则服务会拒绝启动。
