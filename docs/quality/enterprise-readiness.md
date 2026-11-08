# 企业级达标清单（模板定位）

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-06 |
| 权威性 | Authoritative（本文件是「企业级达标」的唯一评分表与整改 backlog） |
| 适用定位 | 可复用模板：对外提供可检查的门禁、参考实现与达标基线，不承诺真实生产 SLO 与合规审计结论 |

本文件只回答一个问题：**这个模板距离「企业级」还差什么，以及每一条怎么被第三方验证。**

不靠主观感受判定的原因是：企业级 = 可被审计。任何一条能力如果没有「自动化门禁、演练记录、可导出证据」三者之一，一律记为未达标，即使代码能跑。

## 1. 判定规则

### 1.1 评分口径

| 分 | 含义 |
| --- | --- |
| 0 | 完全没有 |
| 1 | 只有文档或口头约定，无实现 |
| 2 | 有实现，无自动化验证 |
| 3 | 有自动化门禁，失败可阻断合并 |
| 4 | 门禁 + 运行期验证（指标/告警/演练记录） |
| 5 | 可长期维持（有负责人、有复核节奏、有历史证据） |

模板基线的目标是**每域 ≥ 3.5，P0 项 ≥ 3**。低于 3 的能力不得在 README 或对外介绍中描述为「已具备」。

### 1.2 三条硬判定线

1. **门禁化**：能自动检查的，不允许只写在文档里。
2. **证据化**：每次发布应能导出测试报告、覆盖率、扫描结果、SBOM、迁移清单。
3. **演练化**：备份恢复、告警触发、回滚必须真跑过一次并留时间戳。

### 1.3 事实标签

沿用 [documentation-governance.md](../documentation-governance.md) §5.2：「（已验证，`路径`）」「【已确认决策】」「【未实现】」「【待确认】」。

## 2. 总览

| 域 | 当前分 | 目标 | 一句话结论 |
| --- | --- | --- | --- |
| A 工程质量与交付门禁 | 2.6 | 4.0 | 四端门禁齐全，缺供应链安全与契约自动化 |
| B 可靠性与容量 | 1.8 | 3.5 | 健康检查做得好，缺限流、熔断、压测、演练 |
| C 可观测性 | 2.2 | 3.5 | 指标与日志可用，缺 tracing、告警、SLO |
| D 安全 | 2.8 | 4.0 | 认证授权扎实，缺 CSP/HSTS、扫描、轮换演练 |
| E 数据与隐私 | 1.7 | 3.5 | 删除链路有基础，保留策略与导出未实现 |
| F 架构治理 | 2.3 | 3.5 | ADR 与 SSOT 到位，缺依赖方向检测与发布版本管理 |
| **综合** | **2.2 / 5** | **≥ 3.7** | 可内部交付，不可对外宣称「企业级已达标」 |

## 3. 逐项清单

### A. 工程质量与交付门禁

| 编号 | 标准（可验证） | 分 | 证据 | 验收方式 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| A1 | CI 按路径分流，四端独立门禁 | 3 | （已验证，`.github/workflows/ci.yml` L28–L75） | 只改 `frontend/**` 时仅前端 job 运行 | — |
| A2 | lint / type-check / 格式检查在 CI 强制 | 3 | 四端 job 均含对应步骤（`ci.yml` L121–L144、L183–L197、L316–L320） | 故意引入一个 lint 错误，PR 变红 | — |
| A3 | 覆盖率阈值可阻断构建 | 2 | 前端 `frontend/vitest.config.ts` L40–L42（lines 80）；Agent `agent-service/pyproject.toml` L78（90）；**admin 无 thresholds**（`admin/vite.config.ts` L55–L63）；**Java 明确未设**（`application-service/pom.xml` L145–L148） | 删掉一个测试后构建失败 | P1 |
| A4 | 依赖版本锁定且 CI 严格安装 | 4 | `frontend/pnpm-lock.yaml`、`admin/pnpm-lock.yaml`、`agent-service/uv.lock`、`application-service/pom.xml` L35–L45；CI 使用 `--frozen-lockfile` / `--frozen` | 手改 lock 文件后 CI 失败 | — |
| A5 | 依赖漏洞扫描 | 0 | 【未实现】仓库内无 Dependabot / Renovate / pip-audit / OWASP dependency-check 配置 | PR 引入已知高危版本时被阻断 | **P0** |
| A6 | 静态应用安全测试（SAST） | 0 | 【未实现】无 CodeQL / Semgrep / Sonar 配置 | 注入类漏洞能被扫描出并阻断 | **P0** |
| A7 | SBOM 与镜像扫描 | 0 | 【未实现】CI 只验证 Docker 构建成功（`ci.yml` L366–L410），无 SBOM 产物、无 Trivy/Grype | 每次构建产出 SBOM；Critical 阻断 | **P0** |
| A8 | 数据库迁移门禁 | 3 | （已验证，`scripts/check-migrations.ps1`，CI `ci.yml` L227–L231） | 新增跳号迁移时 CI 失败 | — |
| A9 | 提交规范与评审模板 | 0 | 【未实现】根 `package.json` 仅含 `packageManager`；无 commitlint / husky / PR 模板 / CODEOWNERS | 非规范提交信息被拒 | P1 |
| A10 | 契约自动校验（生成 + 破坏性变更检测） | 1 | 有 `docs/api-contract.md` 与 springdoc 依赖，但无 OpenAPI 生成比对门禁 | 删除一个响应字段时 CI 报警 | P1 |
| A11 | 文档门禁（链接 + 环境变量键一致） | 3 | （已验证，`scripts/check-doc-links.ps1`、`scripts/check-env-docs.ps1`，CI L343–L361） | 写坏一个相对链接后 CI 失败 | — |

### B. 可靠性与容量

| 编号 | 标准（可验证） | 分 | 证据 | 验收方式 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| B1 | liveness 与 readiness 分离 | 4 | （已验证，`agent-service/app/api/v1/health.py` L35–L80） | 断开依赖后 readiness 返回 503、liveness 仍 200 | — |
| B2 | 关键依赖纳入 readiness | 3 | 同上；Java 使用 `/actuator/health`（`docker-compose.yml` L181–L189） | 停 Redis 后 Agent 不就绪 | — |
| B3 | 优雅停机（等待进行中的 SSE / 后台任务） | 2 | 容器 `init: true` 与 `restart` 策略（`docker-compose.yml` L105–L115、L196–L204）；【待确认】Spring `server.shutdown` 与 Agent lifespan 的超时配置 | 部署时无截断流与丢任务 | P1 |
| B4 | 分层超时 | 3 | Nginx `/api/` 60s、`/agent/` 3600s（`frontend/deploy/nginx/default.conf.template` L66–L137）；Agent→Java 5s（`docker-compose.yml` L255–L260） | 上游挂起时请求在预期时间内失败 | — |
| B5 | 重试含退避与抖动 | 2 | LLM SDK `max_retries=2`（`agent-service/app/services/llm.py` L35、L139）；outbox 有退避；【待确认】无统一抖动策略 | 上游 429 时不同实例不同步重试 | P1 |
| B6 | HTTP 层限流 | 1 | 仅登录失败限流（`InMemoryLoginAttemptLimiter.java`），业务 API 无限流 | 压测下出现 429 而非全量打穿 | **P0** |
| B7 | LLM 维度限流（RPM/TPM） | 2 | 只有每日请求额度（`V10__create_model_request_quotas.sql`），无 token 速率限制 | 单用户无法在短时间内耗尽配额 | **P0** |
| B8 | 熔断 / 失败切换 | 1 | 控制面不可达降级默认模型（`agent-service/app/services/model_runtime.py` L81–L83）；无上游失败切换与熔断 | 某个 provider 故障时自动切备用 | P1 |
| B9 | 压测基线与回归 | 0 | 【未实现】无 k6 / JMeter / Locust 脚本与基线数据 | 每次发布对比首 token P95 与吞吐 | P1 |
| B10 | 灰度 / Feature Flag / 回滚演练 | 1 | 部署文档有回滚命令（`docs/deployment/deployment-guide.md`）；【未实现】灰度与开关 | 新模型可对小流量灰度并一键回滚 | P2 |
| B11 | 备份与恢复演练 | 1 | 只有手工 `pg_dump` 命令（`docs/deployment/deployment-guide.md` L346–L352）；无定时任务、无恢复演练记录 | 从备份恢复到可用环境并记录 RTO/RPO | **P0** |
| B12 | 故障注入 / 混沌 | 0 | 【未实现】 | 注入上游超时后系统降级不雪崩 | P2 |

### C. 可观测性

| 编号 | 标准（可验证） | 分 | 证据 | 验收方式 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| C1 | 业务与运行时指标 | 4 | （已验证，2026-11-07）Agent 13 个指标族（`agent-service/app/core/metrics.py` L34–L101）、Java `/actuator/prometheus`（Micrometer）、LiteLLM `/metrics/`；三端由 `deploy/prometheus/prometheus.yml` 统一抓取 | 面板能看到首 token 延迟与 outbox 死信 | — |
| C2 | 指标标签基数受控 | 4 | 明确禁止 `user_id` / `thread_id` 作标签，路由用模板（`metrics.py` L12–L14、L110–L133） | 压测后序列数不随用户数线性增长 | — |
| C3 | 结构化日志 + 请求关联 | 4 | JSON 日志与 `request_id` 绑定（`agent-service/app/core/logging.py` L31–L68、`app/core/middleware.py` L20–L60） | 用 request_id 串起一次请求全部日志 | — |
| C4 | 日志脱敏 | 2 | 规则要求存在（`.trae/rules/00-monorepo-common.md` §5），【待确认】无统一脱敏器与自动化测试 | 日志中检索不到 Token / 手机号 | P1 |
| C5 | 分布式 tracing | 0 | 【未实现】无 OpenTelemetry / `traceparent` 传播 | 一次对话可从 Nginx 追到 LLM 调用 | P1 |
| C6 | 告警规则 | 0 | 【未实现】无 Prometheus rules / Alertmanager | 首 token 变慢时真实触发一次告警 | **P0** |
| C7 | SLO / SLI / 错误预算 | 0 | 【未实现】 | 有明确阈值与季度达标记录 | **P0** |
| C8 | 告警处置 Runbook | 0 | 部署文档有排障章节，【未实现】告警到处置的映射 | 值班人按文档 10 分钟内定位 | **P0** |
| C9 | 前端错误与性能采集 | 0 | 【未实现】无 Sentry / RUM | 线上前端异常可归因 | P2 |

### D. 安全

| 编号 | 标准（可验证） | 分 | 证据 | 验收方式 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| D1 | JWT 非对称签名与密钥校验 | 4 | （已验证，`JwtTokenIssuer.java` L37–L53，RS256） | 伪造签名被拒 | — |
| D2 | 令牌用途隔离 | 4 | `TokenUseFilter.java` L37–L69；Agent 侧 `core/security.py` L98–L145 | 服务令牌调用户接口返回 401/403 | — |
| D3 | 刷新令牌轮换与重放检测 | 4 | 仅存 SHA-256 摘要，闲置 7 天 / 绝对 30 天（`RefreshSessionService.java`） | 旧 refresh token 重放失败 | — |
| D4 | 口令哈希 | 3 | BCrypt（`SecurityConfig.java` L133–L134）；【待确认】strength 参数未显式声明 | 口令泄露不可逆 | P1 |
| D5 | 登录爆破防护 | 3 | `InMemoryLoginAttemptLimiter.java`；【待确认】多实例下不共享状态 | 多副本部署时仍然生效 | P1 |
| D6 | 角色与管理端隔离 | 3 | `/api/v1/admin/**` 要求 ADMIN（`SecurityConfig.java` L78–L105） | 普通用户访问管理接口 403 | — |
| D7 | 资源归属校验 | 3 | 任务、会话、用量均按用户过滤（如 `ModelRuntimeService.java` L202–L208） | 访问他人资源返回 404 而非 403 | — |
| D8 | SQL 参数化 | 3 | MyBatis Mapper 全部使用参数绑定 | 静态扫描无字符串拼接 SQL | — |
| D9 | 输入校验以服务端为准 | 3 | Bean Validation + Pydantic Schema | 越界/非法枚举被拒 | — |
| D10 | CORS 白名单 | 3 | `app/main.py` L169–L174 使用配置化 origin，未开 `*` | 非白名单 Origin 预检失败 | — |
| D11 | 安全响应头 | 2 | 仅 3 个头（`frontend/deploy/nginx/default.conf.template` L35–L38）；【未实现】CSP、HSTS | 安全扫描无「缺失安全头」高危项 | P1 |
| D12 | SSRF 防护（BYOK 地址） | 3 | `OutboundHostGuard.java`、`BaseUrlPolicy.java` | 内网地址与重绑定域名被拒 | — |
| D13 | 凭证加密与密钥版本 | 4 | AES-256-GCM + `key_version`（`ProviderCredentialCipher.java` L15–L24） | 密文不含明文，旧版本可读 | — |
| D14 | 密钥轮换流程与演练 | 1 | 文档有说明（`docs/deployment/environment-variables.md`），【未实现】轮换脚本与演练记录 | 轮换后旧数据可读、新数据用新版本 | **P0** |
| D15 | 审计日志覆盖 | 3 | `AuthAuditRecorder.java` L42–L72 覆盖登录/刷新/角色变更/BYOK 操作；【待确认】不可篡改与保留期 | 管理操作可追溯 | P1 |
| D16 | LLM 提示注入与工具越权防护 | 1 | 有工具注册表、超时、每回合调用上限（`agent-service/app/agent/registry.py`）；【未实现】注入检测与工具权限分级 | 恶意提示无法越权调用工具 | **P0** |
| D17 | 模型输出不可信处理 | 2 | 生成式 UI 有渲染边界说明（`docs/services/frontend/generative-ui.md`）；【待确认】是否全量净化 | 模型输出无法注入脚本 | P1 |

### E. 数据与隐私

| 编号 | 标准（可验证） | 分 | 证据 | 验收方式 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| E1 | 数据归属与隔离 | 3 | 业务表按 `user_public_id` 隔离；Agent 用命名空间线程键 | 跨用户查询查不到 | — |
| E2 | 会话删除级联 | 3 | 删除墓碑 + 重试 + 保留期（`agent-service/app/services/session_deletion/`） | 删除后 checkpointer 无残留 | — |
| E3 | 保留策略落地 | 1 | 【未实现】前端明示「保留策略与自动清理尚未实现」（`frontend/src/locales/zh-CN.ts` L320–L325） | 超过保留期的数据被自动清理 | **P0** |
| E4 | PII 字段清单 | 0 | 【未实现】 | 每个 PII 字段有分类、存储位置、保留期 | P1 |
| E5 | 数据导出（数据主体权利） | 0 | 【未实现】 | 用户可导出自己的全部数据 | P1 |
| E6 | 审计与用量数据保留期 | 1 | 只有 outbox 7 天清理（`agent-service/app/services/usage_outbox.py` L61） | 保留期到期自动清理并可证明 | P1 |
| E7 | 备份加密与异地存放 | 0 | 【未实现】 | 备份文件加密且可异地恢复 | **P0** |
| E8 | 敏感信息不落日志 | 3 | 规则与实现部分覆盖（见 C4） | 抽样日志审计无敏感字段 | P1 |
| E9 | AI 数据使用声明 | 0 | 【未实现】 | 用户可读的模型数据使用说明 | P2 |

### F. 架构治理

| 编号 | 标准（可验证） | 分 | 证据 | 验收方式 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| F1 | 架构决策记录 | 3 | `docs/adr/` 现有 5 条 | 新决策有 ADR 且被引用 | — |
| F2 | 单一事实源与文档门禁 | 4 | `docs/documentation-governance.md` §6 + CI 文档 job | 同类事实不在两处重复维护 | — |
| F3 | 模块边界 | 3 | Spring Modulith BOM（`application-service/pom.xml` L35–L45），模块化分层 | 跨模块直接引用被阻止 | P1 |
| F4 | 依赖方向自动检测 | 1 | 靠 `.trae/rules/00-monorepo-common.md` §1 人工约束；【未实现】ArchUnit / import-linter | 反向依赖让构建失败 | P1 |
| F5 | API 版本化与弃用策略 | 2 | 统一 `/api/v1`；【未实现】弃用公告与并行版本流程 | 破坏性变更提前一个版本告知 | P1 |
| F6 | 变更管理与发布记录 | 1 | 有 CI 与部署文档；【未实现】发布单 / 变更日志 | 每次上线可追溯到提交与审批 | P2 |
| F7 | 版本号与 CHANGELOG | 1 | 【未实现】根 `package.json` 无 version，无 CHANGELOG | 每次发布有可引用的版本号 | P2 |
| F8 | 环境分层 | 2 | dev / production 有区分；【未实现】staging | 预发环境可复现生产配置 | P1 |
| F9 | 技术债登记 | 3 | `docs/planning/closure-plan.md` | 技术债有负责人与验收标准 | — |

## 4. 与业界基准的映射

| 基准 | 本清单覆盖项 | 当前结论 |
| --- | --- | --- |
| OWASP ASVS 4.0 | D1–D17 | 认证与凭证章节较好；通信安全（CSP/HSTS）、恶意输入、日志章节有缺口 |
| OWASP LLM Top 10 | D16–D17、B7、E9 | 工具治理有基础；提示注入、输出过滤、用量滥用防护不足 |
| Google SRE（SLI/SLO/错误预算） | C1–C8、B9 | 有指标无 SLO，有健康检查无告警闭环 |
| SLSA / SBOM | A5–A7 | 依赖锁定达标；扫描、SBOM、制品验证缺失 |
| DORA 四指标 | A1–A11、F6–F7 | 自动化基础好；变更失败率与恢复时长无度量 |
| ISO/IEC 25010 | A–F 全域 | 功能适配与可维护性较好；可靠性与安全性待补 |

## 5. 整改 backlog

按「先建立客观可信度，再补运行期能力」排序。每一步的完成定义 = 清单对应项分数提升 + 验收方式可复现。

### Phase 1（P0，模板基线必做）

| # | 事项 | 对应项 | 产出物 | 验收 |
| --- | --- | --- | --- | --- |
| 1 | 供应链安全门禁 | A5 / A6 / A7 | Dependabot 或 Renovate、CodeQL、pip-audit、Trivy、SBOM 上传 | 引入高危依赖的 PR 被阻断 |
| 2 | 告警与 SLO 闭环 | C6 / C7 / C8 | Prometheus rules、SLO 定义、Runbook | 现场触发一次告警并按 Runbook 处置 |
| 3 | 备份与恢复演练 | B11 / E7 | 定时备份脚本、恢复脚本、演练记录模板 | 从备份恢复并记录 RTO/RPO |
| 4 | 限流与熔断 | B6 / B7 / B8 | HTTP 限流中间件、TPM 限额、provider 级 fallback | 压测出现受控 429；上游故障不雪崩 |
| 5 | 数据保留与删除闭环 | E3 / E5 | 保留策略执行任务、导出接口、注销级联 | 超期数据被清理；导出完整；删除后全链路无残留 |
| 6 | 密钥轮换与 AI 输入防护 | D14 / D16 | 轮换脚本与演练记录、工具权限分级、提示注入检测 | 轮换无损；恶意提示无法越权 |

### Phase 2（P1，企业评审必问）

| # | 事项 | 对应项 |
| --- | --- | --- |
| 7 | 分布式 tracing | C5 |
| 8 | 契约自动生成与破坏性变更检测 | A10 |
| 9 | 覆盖率阈值补齐（Java / admin） | A3 |
| 10 | 提交规范与评审模板 | A9 |
| 11 | 压测基线与性能回归 | B9 |
| 12 | 安全响应头补齐 | D11 |
| 13 | 日志脱敏自动化与 PII 清单 | C4 / E4 |
| 14 | 依赖方向自动检测 | F4 |
| 15 | 预发环境与弃用流程 | F8 / F5 |

### Phase 3（P2，增强项）

| # | 事项 | 对应项 |
| --- | --- | --- |
| 16 | 灰度与 Feature Flag | B10 |
| 17 | 混沌工程 | B12 |
| 18 | 成本预算与告警 | B7 延伸 |
| 19 | 前端 RUM | C9 |
| 20 | 发布版本号与 CHANGELOG | F7 |
| 21 | AI 数据使用声明 | E9 |

## 6. 复核机制

1. 每完成一个 P0 项，更新对应行分数、证据路径与验收结果；不允许只改分数不改证据。
2. 新增任何「企业级能力」必须同时登记到本表，否则视为未完成。
3. 每季度用 [OWASP ASVS 4.0](https://owasp.org/www-project-application-security-verification-standard/) 清单做一次自评，差异写入本文件变更记录。
4. 冲突时以可执行配置为准（见 [documentation-governance.md](../documentation-governance.md) §1），并立即修正本表。

## 7. 变更记录

| 日期 | 变更 | 影响 |
| --- | --- | --- |
| 2026-11-06 | 首次建立评分表与 P0–P2 backlog | 无代码变更，仅新增基线 |
