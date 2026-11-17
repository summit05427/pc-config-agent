# 文档治理规范

| 项 | 内容 |
| --- | --- |
| 适用范围 | 根 `docs/` 的分类、状态、SSOT、变更与门禁 |
| 状态 | Authoritative |
| 最后更新 | 2026-11-17 |
| 读者 | 所有提交文档的开发者与评审人 |

## 1. 结论先行

- 根 `docs/` 是唯一权威目录；各服务的 `docs/` 不提交、不构成权威。
- 同一事实只允许一处详述（SSOT），其他位置只写结论并链接。
- 删除文档必须同时满足：内容已被权威文档完整承接、全仓无引用、无独立证据价值。
- ADR 不可修改；历史决策由 Git 保留，不靠文档副本。

## 2. 读前必做

1. 先查 [INDEX.md](INDEX.md) 的任务路由，只读命中的 1–3 份。
2. 长文档先用 Grep 定位标题，再按 `offset` / `limit` 读取命中段。
3. 禁止整目录遍历或一次性读取全部规则。
4. 发现冲突：记录「代码位置、文档位置、差异」，按 §6 优先级处理，不自行选定版本后静默改写。

## 3. 目录与文件

```text
docs/
├── INDEX.md                         任务路由
├── README.md                        文档地图、术语、SSOT
├── api-contract.md                  HTTP / SSE / 内部接口契约（唯一事实源）
├── api-contract-quick-reference.md  派生速查
├── architecture-overview.md         系统架构与边界
├── development-rules.md             跨端变更与验证规范
├── documentation-governance.md      本文
├── model-runtime-architecture.md    模型运行时设计
├── adr/                             架构决策记录（不可变）
├── deployment/                      部署、Solo、环境变量
├── services/
│   ├── frontend/                    前端架构、开发、UI、生成式 UI
│   ├── application-service/         Java 架构、接口、安全、开发
│   ├── agent-service/               Agent 架构、工作流、接口
│   └── admin/                       管理端架构、开发
├── pc-config/                       PC 配置模块：架构、规则、数据、报价、评测、术语
├── planning/                        路线图、重构方案
└── quality/                         数据治理报告与基线
```

PC 配置模块的 Agent 图与节点行为统一在 `services/agent-service/agent-workflows.md`，`pc-config/` 不保留副本。

## 4. 文档类型与状态

| 类型 | 要求 | 示例 |
| --- | --- | --- |
| 契约（Authoritative） | 字段、错误码、事件必须与代码一致；变更需跨端同步 | `api-contract.md` |
| 事实（Current） | 描述当前实现，必须给证据位置 | `services/*/architecture.md` |
| 规范（Authoritative） | 强制约束，可被 CI 或评审引用 | `development-rules.md`、本文 |
| 规划（Current） | 明确标注已完成 / 规划中 / 未实现 | `planning/roadmap.md` |
| 证据（Current） | 带时间、批次、统计口径，可复算 | `quality/*.md` |
| 派生速查 | 只做压缩视图，冲突时以源文件为准 | `*-quick-reference.md` |
| 历史归档 | 解释背景，不作为契约；原则上不新增 | — |

每篇文档开头必须有「适用范围 / 状态 / 最后更新」；契约、规范、事实类文档还应给「权威性 / 主要证据」。

## 5. SSOT

| 主题 | 唯一权威 |
| --- | --- |
| 系统架构、服务边界、数据归属、通信链路 | `architecture-overview.md` |
| 对外 HTTP / SSE / 内部接口契约 | `api-contract.md` |
| PC 兼容规则 | `pc-config/compatibility-rules.md` |
| Agent 图与节点行为 | `services/agent-service/agent-workflows.md` |
| PC 数据、报价与快照 | `pc-config/data.md`、`pc-config/market-offer-management.md` |
| 环境变量与生产 fail-fast | `deployment/environment-variables.md` |
| 部署、CI、回滚 | `deployment/deployment-guide.md` |
| 技术决策 | `adr/**` |
| 阶段状态与遗留问题 | `planning/roadmap.md` |
| 编码硬约束 | `.trae/rules/**` |

派生文档允许重复结论，但不得扩展事实；源文件变更时必须同步。

## 6. 冲突优先级

```text
代码 > .env.example / Compose / Dockerfile / 迁移脚本 > 权威文档 > 派生速查 > 历史归档
```

- 文档与可执行配置冲突时，以可执行配置为准，并立即修正文档。
- 文档与代码冲突时，先确认代码是否为预期实现；不确定则记录待确认，不擅自选边。
- ADR 只记录当时的决策；与现状冲突时，新增 ADR 或在路线图中说明，不回改旧 ADR。

## 7. 变更规则

1. 契约变更（路径、字段、错误码、SSE 事件、状态枚举）必须同时更新 `api-contract.md`、受影响服务文档与代码。
2. 新增公共 API、配置项、环境变量时同步 `.env.example` 与 `deployment/environment-variables.md`。
3. 新增依赖、模型、数据源时说明用途、体积/成本与失败降级。
4. 阶段完成后更新 `planning/roadmap.md`，不在多份报告里保留互相矛盾的状态。
5. 复杂流程（状态机、流式协议、HITL）写设计说明，不只留代码。
6. 不写没有证据的「已完成」「已支持」「已优化」；未实现能力必须标注【规划中】或【未实现】。

## 8. 删除与合并

删除前逐项确认：

| 条件 | 说明 |
| --- | --- |
| 内容已承接 | 有效内容已迁入 SSOT 文档，且新位置可检索 |
| 无引用 | 全仓 Markdown、代码注释与 `.trae/` 中无链接 |
| 无独立证据 | 不是唯一的质量/评测/审计证据；如保留需说明 |
| 不违反 ADR | `adr/**` 不可修改；旧 ADR 中的历史链接失效需在路线图记录 |

合并时先写新位置，再删旧文件，最后全仓搜索旧文件名与旧术语。

## 9. 命名与链接

- 文件名 kebab-case，主题名而非阶段编号；`roadmap.md`、`compatibility-rules.md`。
- 链接使用相对路径，必须指向真实存在的文件与章节。
- 不链接已删除文件；不链接回收站、临时目录与本地绝对路径。
- 章节标题保持稳定；重命名章节时同步全仓引用。

## 10. 门禁与评审

| 检查 | 方式 |
| --- | --- |
| 链接有效 | `Glob docs/**/*.md` + 抽查链接 |
| 术语一致 | 全仓 Grep 旧求解器端点、旧节点名与旧文档名 |
| 契约一致 | 对照 `api-contract.md` 与控制器 / Schema |
| 数据一致 | 对照夹具计数与 `quality/` 报告 |
| ADR 未改 | `git diff -- docs/adr` 必须为空 |

评审重点：是否有第二事实源、是否把规划写成现状、是否给出可复算的数据口径。

## 11. 维护

- 单份规范不超过 150 行；超出时拆分为主题文档。
- 每季度抽查一次链接、计数与状态标签。
- 文档与 CI、Dockerfile、Compose 不一致时，以可执行配置为准并修正文档。
