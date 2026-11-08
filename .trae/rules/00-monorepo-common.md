---
alwaysApply: true
---

# Monorepo 公共规则

适用范围：整个仓库。四份服务规则只覆盖各自目录；冲突时以服务规则为准，未覆盖部分沿用本文件。

**规则加载策略（控制上下文成本）**：本文件常驻；服务规则在 `.trae/rules-on-demand/`，改动对应目录前必须先读命中项，未读视为未遵守。禁止一次性读取全部规则或整目录文档。

| 改动范围 | 动手前必读 |
| --- | --- |
| `frontend/**` | `.trae/rules-on-demand/10-frontend.md` |
| `application-service/**` | `.trae/rules-on-demand/20-backend-java.md` |
| `agent-service/**` | `.trae/rules-on-demand/30-agent-python.md` |
| `admin/**` | `.trae/rules-on-demand/40-admin.md` |
| 契约 / 跨端 | 命中规则 + `docs/api-contract.md` 对应章节 |

## 1. 结构与边界

- `frontend/`：React 19 + TypeScript + Vite + TanStack Router/Query + Zustand，负责界面、路由与 SSE 消费。
- `admin/`：React 19 + TypeScript + Vite + TanStack Router/Query（shadcn-admin），负责管理员登录、用户管理、审计日志、模型目录与定价维护。
- `application-service/`：Java 21 + Spring Boot，负责用户、权限、业务数据与 JWT 签发。
- `agent-service/`：Python 3.12 + FastAPI + LangGraph，负责对话编排、工具调用与会话持久化。
- `deploy/`：本地基础设施编排；根 `docker-compose.yml`：四端与中间件总编排。
- `.github/workflows/ci.yml`：按路径分流的 CI；根 `docs/`：契约与操作文档；`.trae/`：规则与技能。

依赖方向固定：浏览器 → `frontend` Nginx（唯一公网入口）→ `application-service` / `agent-service`；`admin` 由同一个 Nginx 以 `/admin/` 托管，接口仍经 `/api/` 到 `application-service`。禁止跨服务源码引用或共享业务表，只通过 HTTP 契约交互。
唯一例外是 **Agent → application-service 的内网内部接口**（`/internal/v1/**`，服务令牌 `token_use=service`，用户维度额外带 `X-User-Token`），方向不可反转：Java 不得调用 Agent。

职责边界：

- Java 是 Token 的唯一签发方；Agent 只校验，不建用户表、不签发生产 Token。
- Java 使用 `agent` 库；Agent 使用 `agent_service` 库，互不查询对方业务表。
- 前端不保存模型密钥，不自行拼接鉴权逻辑。
- 管理端只调用 Java `/api/v1/admin/**` 与 `/api/v1/auth/**`，不调用 Agent、不查询数据库。

契约变更（路径、字段、错误码、SSE 事件类型）必须同步前端类型、管理端类型、Java DTO、Agent Schema 与根 `docs/`。

## 2. 常用命令（从仓库根执行）

```powershell
corepack pnpm --dir frontend lint:ci
corepack pnpm --dir frontend type-check
corepack pnpm --dir frontend test:coverage
corepack pnpm --dir frontend e2e:critical

corepack pnpm --dir admin lint:ci
corepack pnpm --dir admin type-check
corepack pnpm --dir admin test
corepack pnpm --dir admin build

cd application-service; .\mvnw.cmd -q verify   # Windows
# cd application-service && ./mvnw -q verify   # Linux/macOS

uv --directory agent-service sync --frozen
uv --directory agent-service run ruff check app tests evals run.py
uv --directory agent-service run mypy
uv --directory agent-service run pytest -q --cov=app --cov-report=term-missing
uv --directory agent-service run python -m evals --fake

docker compose --env-file .env config -q
```

### 2.1 开发阶段启动方式（强制）

开发阶段四端（`frontend`、`admin`、`application-service`、`agent-service`）一律在宿主机启动，容器只跑中间件 `postgres`、`pgvector`、`redis`。中间件复用根 `docker-compose.yml` 的定义，保持现有数据卷不变：

```powershell
docker compose --env-file .env up -d postgres pgvector redis   # 只起中间件
docker compose stop frontend admin application-service agent-service   # 停四端容器
```

- 本地启动：`corepack pnpm --dir frontend dev`（5173）、`corepack pnpm --dir admin dev`（5174）、`cd application-service; .\mvnw.cmd spring-boot:run`（8080）、`uv --directory agent-service run python run.py`（8000）；Java 需先注入 JWT、DB 与管理员口令等必填变量。
- 四端容器只用于发布前验收或验证 Nginx / 代理链路，届时执行 `docker compose --profile full up -d --build`；只跑 Agent 的 Solo 模式见 `docs/deployment/deployment-guide.md` §3.3。
- `deploy/docker-compose.infra.yml` 使用独立的 `infra_*` 数据卷，与根 Compose 的中间件数据不互认，日常开发不使用。

只改运行时环境变量（数据库、JWT、LLM）不需要重建镜像；改 `VITE_*`、源码或 Dockerfile 必须重建对应服务。

## 3. 命名与代码风格

- Java / TypeScript 的变量与函数用 camelCase；Python 用 snake_case；类与组件用 PascalCase。
- 常量用 SCREAMING_SNAKE_CASE；文件与目录用 kebab-case（Python 模块用 snake_case）。
- 布尔值用 `is` / `has` / `can` 前缀；禁止无意义缩写与单字母变量（循环计数除外）。
- 魔法数字与字符串提取为常量或枚举；名称必须表达用途。
- 缩进以各服务格式化配置为准（前端 Prettier 2 空格，Java 与 Python 4 空格），UTF-8、LF；单函数不超过 50 行，嵌套不超过 3 层。

## 4. Git 与评审

- `main` 受保护，禁止直接提交；分支用 `feature/`、`fix/`、`hotfix/`、`refactor/`、`docs/`，小写 kebab-case。
- 提交格式 `type(scope): 中文描述`，type 取 `feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `build` / `ci` / `chore`。
- 一次提交只做一件事，禁止混入格式化与无关重命名。
- 不提交 `node_modules/`、`target/`、`.venv/`、`dist/`、日志、`.env`、密钥与本地部署产物。
- PR 描述包含变更目的、影响范围、验证方式与回滚方案；CI 通过后再合并。
- PR 建议不超过 400 行；至少 1 名评审人；squash merge 并删除源分支。
- 评审重点：分层与事务边界、API 契约、SQL 参数化与索引、越权与敏感信息、错误码、测试覆盖、配置同步文档。

## 5. 安全基线

- 密钥、口令、Token、API Key 只能来自环境变量或密钥管理，禁止硬编码、禁止提交真实 `.env`。
- SQL 必须参数化；禁止字符串拼接 SQL，禁止 `${}` 拼接用户输入。
- 输入校验以服务端为准；DTO / Pydantic Schema 必须声明长度、格式、范围与枚举。
- 按 ID 访问资源必须校验归属；前端权限判断只用于交互，不作为安全边界。
- 日志禁止输出密码、Token、身份证号、手机号、银行卡号与完整对话内容。
- 页面禁止用 `dangerouslySetInnerHTML` 渲染未经净化的用户输入；外链加 `rel="noopener noreferrer"`。
- 文件上传校验类型白名单、大小上限与内容嗅探；文件名不信任用户输入。
- CORS 使用明确白名单；禁止 `*` 与 `allowCredentials` 同时开启。

## 6. 配置与环境

- `.env.example` 随仓库提交；真实 `.env`、`.env.local`、`.env.*.local` 一律忽略。
- 生产环境必须 fail-fast：缺关键变量、使用占位符、开启 debug 时直接拒绝启动。
- 配置项 kebab-case（YAML）或大写下划线（环境变量），同类配置集中管理。
- 禁止硬编码服务地址、端口与第三方域名；容器内用 Compose 服务名互访。
- 修改 `.env.example` 时必须同步根 `docs/` 的部署说明。

## 7. 文档

- 根 `docs/` 随仓库提交；三个服务内部的 `docs/` 已被 `.gitignore` 排除，仅本地保留。
- 日常改代码先查 [docs/INDEX.md](../../docs/INDEX.md) 的任务路由，只读命中的 1–3 份，禁止整目录遍历；需要全量清单时再读 [docs/README.md](../../docs/README.md)。同一事实只在一处详细维护（SSOT 表见 `docs/documentation-governance.md` §6）。
- 冲突优先级：代码 > `.env.example` 等可执行配置 > 权威文档 > 历史归档。发现冲突先记录，不自行选定版本。
- README 含项目定位、技术栈、环境要求、启动命令、配置说明与接口文档入口。
- 新增公共 API、配置项、环境变量时同步更新根 `docs/` 与 `.env.example`。
- 复杂流程（状态机、流式协议、异步补偿）写设计说明，不只留代码。
- 注释解释「为什么」，不复述「做了什么」；禁止在注释中写密钥、Token、内网地址。

## 8. 性能

- 数据库查询避免 N+1；批量操作用批量接口；常用过滤/排序列建索引，禁止 `SELECT *`。
- 列表必须分页；大数据量前端用分页或虚拟滚动。
- 循环体内不做 I/O、不重复创建客户端；连接池与超时必须显式配置。
- 前端路由与大型组件按需加载；高频事件防抖或节流。
- 耗时操作（LLM 推理、大文件）异步化或展示进度，不阻塞主流程。
- 优化前先测量（EXPLAIN、性能面板、Profile），用数据说明瓶颈。

## 9. 测试与门禁

- 前端：`corepack pnpm --dir frontend lint:ci`、`type-check`、`test:coverage` 全部通过；关键 E2E `e2e:critical` 全绿。
- 管理端：`corepack pnpm --dir admin lint:ci`、`type-check`、`test`、`build` 全部通过；测试为 Vitest browser mode。
- Java：`mvnw verify` 通过；核心 service 覆盖率 ≥ 70%（建议）。
- Agent：ruff、mypy、pytest 全部通过；覆盖率阈值 90%（`pyproject.toml`）。
- 禁止用 `@Disabled`、`skip`、`-DskipTests` 或降低断言换取通过。
- 每个业务分支至少覆盖：成功、参数非法、资源不存在、未认证/无权限。
- CI 按 `frontend/**`、`admin/**`、`application-service/**`、`agent-service/**` 路径分流，互不干扰。

## 10. 维护

- 单份规则不超过 150 行；新增规则先以「建议」试运行一个迭代，再升级为「强制」。
- 规则与 CI、Dockerfile、Compose 不一致时，以可执行配置为准，并立即修正规则。
