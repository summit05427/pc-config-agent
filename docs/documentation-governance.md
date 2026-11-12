# 项目文档管理规范

| 项 | 内容 |
| --- | --- |
| 状态 | Current |
| 最后核验 | 2026-11-11 |
| 权威性 | Authoritative（文档体系的分类、命名、状态、SSOT、变更与门禁规则） |

本文定义本仓库文档的分类、目录、命名、状态、变更与校验规则，是新增、修改、整理、审查文档的统一依据。本文只立规则，不描述具体实现；实现细节属于各服务文档。文档地图与阅读路径见 [README.md](README.md)。

适用范围：根 `docs/`、三个服务的 `README.md`、`.trae/rules/`、仓库根 `README.md`、`GLOSSARY.md`。不适用于 `.trae/skills/`（工具资产）与 `agent-service/app/agent/prompts/*.md`（运行时提示词，属于代码资产而非文档）。

## 1. 冲突优先级（唯一规则）

**代码 > `.env.example` 等可执行配置 > 本仓库权威文档 > 历史归档。**

不再保留「docs 优先 / rules 优先」两套说法。`.trae/rules/` 是编码硬约束，与 `docs/` 冲突时以能通过 CI 的可执行配置为准，并同时修正规则或文档。

发现冲突的处理方式：登记到对应文档的「已知问题 / 待确认事项」，不自行选定一端作为答案，也不在不告知的情况下改代码。

## 2. 分类与职责边界

| 类别 | 存放位置 | 负责内容 | 禁止放入 |
| --- | --- | --- | --- |
| 项目级 | `README.md`、`docs/architecture-overview.md`、`docs/README.md` | 项目定位、三端职责、部署拓扑、技术选型、文档地图 | 单端实现细节、接口字段表 |
| 公共契约 | `docs/api-contract.md`、`docs/development-rules.md` | 跨端路径、鉴权、响应信封、SSE、错误码、内部接口、变更影响矩阵 | 某端内部类名、私有实现 |
| 服务级 | `docs/services/{frontend,application-service,agent-service}/` + 各服务 `README.md` | 该服务的内部分层、模块、数据访问、配置、开发指南 | 其他服务的职责、跨端契约正文 |
| 架构决策（ADR） | `docs/adr/NNNN-<kebab-title>.md` | 重要决策的背景、备选方案、结论、影响 | 普通实现细节、临时讨论 |
| 规划与质量 | `docs/planning/`、`docs/quality/` | 当前未完成事项、验收结论、缺陷台账、联调证据 | 长期契约、稳定规范 |
| 开发与运维 | `docs/deployment/`、`docs/development-rules.md` | 环境搭建、变量、部署、密钥、测试、排障 | 业务规则、接口定义 |
| 历史归档 | `docs/archive/` | 废弃但仍具参考价值的文档 | 作为当前有效规范使用 |

边界判定：一条事实如果同时服务两个以上端，只能写在公共契约或项目级文档；服务文档只允许引用，不允许复制第二份。

## 3. 目录结构

```text
README.md                                   # 项目入口：定位、启动、文档入口
GLOSSARY.md                                 # 术语表（项目级）
docs/
├── README.md                               # 文档总入口：清单、状态标签、阅读路径、SSOT
├── architecture-overview.md                # 项目级：各端职责、拓扑、信任边界、未实现清单
├── api-contract.md                         # 公共契约：对外 HTTP/SSE + 内部接口摘要
├── development-rules.md                    # 跨端变更矩阵、验证命令、评审清单
├── documentation-governance.md             # 本文件
├── model-runtime-architecture.md           # 模型接入与调度设计 + 落地记录
├── adr/                                    # 架构决策记录
├── deployment/
│   ├── deployment-guide.md                 # 部署与上线操作手册
│   ├── environment-variables.md            # 环境变量唯一权威
│   └── env-quick-reference.md              # 环境变量速查（派生）
├── planning/
│   ├── roadmap.md                          # 阶段目标、决策与遗留问题唯一权威
│   └── pc-config-implementation-plan.md    # Stage 1–6 历史方案（状态以 roadmap 为准）
├── quality/                                # 验收证据（PC 配置联调、硬件治理、基线）
├── services/{frontend,admin,application-service,agent-service}/
└── archive/                                # 历史归档（按需创建，当前为空）
frontend/README.md
admin/README.md
application-service/README.md
agent-service/README.md
```

- 每个服务的入口固定为 `<service>/README.md`，必须能一跳到达 `docs/services/<service>/`，且不得重复粘贴契约内容。
- `frontend/docs/`、`application-service/docs/` 已被 `.gitignore` 排除；`agent-service/docs/` 不存在。三者都不是权威来源，需要长期保存的内容必须写入根 `docs/`。
- `docs/archive/` 与 `docs/adr/` 按需创建，禁止预建空目录。

## 4. 命名规范

- 目录与文件名统一英文 `kebab-case`（如 `agent-workflows.md`），禁止中文文件名与新增长拼音缩写。
- 文件名表达内容而非编号；ADR 例外，使用 `NNNN-` 前缀保证排序。
- 历史归档文件在原名后追加归档月份（如 `execution-plan-2026-10.md`），避免与新文档同名。
- 服务目录名固定为 `frontend`、`admin`、`application-service`、`agent-service`，与目录或 Compose 服务名一致（`admin` 由 frontend Nginx 的 `/admin/` 托管，见 `docs/deployment/deployment-guide.md`）。
- 一个文件只承担一类职责；出现两类职责时新建文件而不是改名堆叠。

## 5. 状态标注

### 5.1 文档级状态

写在标题下的元信息行，只能取：

`Draft`、`Current`、`Planned`、`In Progress`、`Blocked`、`Completed`、`Deprecated`、`Superseded`。

- `Deprecated` / `Superseded` 只用于 `docs/archive/`，必须写明归档日期、废弃原因与替代文档路径。
- `Deprecated` 表示「内容过期且已被承接」；`Superseded` 表示「已被新版本取代」。2026-11 新归档文件统一用 `Deprecated`，早期归档文件沿用 `Superseded`。
- 一次性报告（审计、治理、验收快照）用 `Completed` + 日期，不再更新内容，只允许追加勘误。

### 5.2 章节级事实标签

沿用 [README.md](README.md) §2 的六类标签：已验证事实 / 已确认决策 / 待确认事项 / 待验证假设 / 未实现能力 / 历史信息。

- 任何「未实现能力」不得写成现在时；任何「待确认事项」不得写成强制规范。
- 写作时使用「（已验证，`路径`）」「【已确认决策】」「【未实现】」这类显式标记。

## 6. 单一事实来源（SSOT）

同一事实只在一处详细维护，其他文档只链接。

| 事实 | 唯一权威 | 其他文档的做法 |
| --- | --- | --- |
| 跨端路径、字段、错误码、SSE 事件、内部接口 | `docs/api-contract.md` | 只链接，不复制表格 |
| 各端职责（含管理端）、拓扑、数据归属、通信链路、未实现清单 | `docs/architecture-overview.md` | 只链接 |
| 环境变量名、默认值、生产 fail-fast、密钥轮换 | 两份 `.env.example` + `docs/deployment/environment-variables.md` | 不另列表 |
| 部署 / CI / 发布与回滚步骤 | `docs/deployment/deployment-guide.md` | 只链接 |
| 认证与令牌细节 | `docs/services/application-service/security.md` | 前端/Agent 文档只描述自身消费方式 |
| 编码硬约束（缩进、命名、安全基线） | `.trae/rules/*.md` | `docs/development-rules.md` 只写流程与矩阵 |
| 端点签名细节（DTO 字段、校验、错误码） | 对应服务的 `docs/services/<service>/api-reference.md` | 跨端文档只保留摘要与链接 |
| 管理端结构、认证流程、页面能力 | `docs/services/admin/architecture.md` | 用户端与 Agent 文档只描述自身消费方式 |
| 功能实现状态（已实现 / 部分实现 / 规划中 / 未实现） | `docs/architecture-overview.md` §7（未实现能力清单）+ `docs/planning/roadmap.md` §8（遗留问题） | 其他文档只链接，不自行断言「已实现」 |
| 模型运行时设计决策与落地进度 | `docs/model-runtime-architecture.md` | 服务文档只描述自身职责 |
| 阶段状态、当前待办与优先级 | `docs/planning/roadmap.md` | 其他文档只链接 |
| 当前未完成 / 未验证事项与放行条件 | `docs/planning/roadmap.md` §8 | 不复制结论 |
| 文档体系规则 | 本文件 + `docs/README.md` | 不重复规则条文 |

## 7. 与代码保持一致

1. 只写有证据的内容：源码、配置、迁移脚本、测试或实际运行结果，并在文中给出路径。
2. 不把计划写成现状；未合并的接口、表结构标记为「未实现能力」。
3. 不同端实现不一致时，先记录差异与证据，不自行选定一端作为答案。
4. 无法确认的内容写「待确认事项」，不得推测补全。

## 8. 变更流程

修改接口、数据结构、认证机制、服务通信或核心流程时，按序执行：

1. 改代码与测试。
2. 更新 `docs/api-contract.md` 对应小节（影响矩阵见 [development-rules.md](development-rules.md) §1）。
3. 更新受影响服务的 `api-reference.md` 与事实文档。
4. 同步 `*.env.example` 与 `docs/deployment/environment-variables.md`（若涉及配置）。
5. 更新 `docs/architecture-overview.md` 的「未实现能力清单」或 `docs/planning/roadmap.md`（若状态变化）。
6. 执行校验（见 §11）。

新增文档前先检查是否已有等价文档；能改现有文件时不新建。

## 9. Agent 使用规则

- 开始任务先读 `docs/README.md`，再按任务读 `docs/architecture-overview.md` 与相关服务文档；跨端任务必须读 `docs/api-contract.md`。
- 不加载与当前任务无关的历史文档；`docs/archive/` 只用于理解决策背景。
- 发现文档缺失、冲突或与代码不符时，先报告并给出证据位置，不自选版本、不擅自扩大范围。
- 不为完成当前任务修改无关文档。
- `.trae/rules/*.md` 只放「稳定约束 + 导航」，不复述 `docs/` 正文；单份规则不超过 150 行。

## 10. 废弃与归档

- 废弃文档移入 `docs/archive/`，保留原文并在标题下标注 `Deprecated`（或 `Superseded`）、归档日期、原因与替代文档。
- 仍具决策价值的内容不得删除；只有确认无价值（完全重复、无历史价值、无审计证据、无外部引用、已由权威文档完整承接）的文件才可删除，删除原因写入提交信息。
- 禁止直接覆盖被替代的架构决策，新建取代文件并用 `Superseded` 双链。
- 拆分大文档时先确保新文档完整承接，再归档原文件，不允许只留下半截内容。

## 11. 校验与门禁

| 校验 | 命令 | 覆盖 |
| --- | --- | --- |
| 相对链接 | `powershell -File scripts/check-doc-links.ps1` | 全部 Markdown 链接可达 |
| 配置键 | `powershell -File scripts/check-env-docs.ps1` | 文档中环境变量存在于某个 `*.env.example` |
| 迁移门禁 | `powershell -File scripts/check-migrations.ps1` | Flyway 迁移命名、版本唯一且连续、全部纳入版本控制 |
| 契约实现 | 三端测试（见 `docs/development-rules.md` §4） | 接口、SSE、错误码行为 |

文档脚本在 CI 的 `Docs (link / env keys)` Job 中执行，`docs/**`、README、`.trae/rules/**`、`scripts/**` 变更即触发；迁移门禁在 `Backend` Job 执行，`application-service/**` 或脚本本身变更即触发。

## 12. 评审检查清单

提交文档相关 PR 时逐条确认：

1. 新增事实是否给出源码或配置证据。
2. 是否重复了 `api-contract.md` 或服务文档的已有内容（是否违反 §6 SSOT）。
3. 文件名、目录是否符合 §3、§4。
4. 是否标注了文档级状态与章节级事实标签；未实现内容是否标注。
5. 受影响的服务文档、`.env.example`、`docs/README.md` 索引是否同步。
6. 三个校验脚本是否通过。

文档变更提交信息使用 `docs(<scope>): <中文描述>`，说明变更原因与影响范围。

## 13. 整改记录（历史）

以下为 2026-10-30 的一次性整改，保留作为背景；当前状态以上文与 `docs/README.md` 为准。表中提到的归档文件已于 2026-11-05 文档清理中删除，历史见 Git。

| 编号 | 偏差 | 处理结果（2026-10-30） |
| --- | --- | --- |
| D-01 | 两份认证文档被删除但有独有内容，且留下死链 | 归档为 `docs/archive/auth-strategy.md`、`docs/archive/authentication-certification.md`，标注 `Superseded` 并修正链接 |
| D-02 | 运维手册使用中文文件名 | 更名为 `docs/production-configuration-guide.md`，全仓引用同步（该文件已于 2026-11 拆分归档，见下） |
| D-03 | 规划手册游离在 `docs/function/` | 移至 `docs/planning/execution-plan.md`（已于 2026-11 归档） |
| D-04 | 缺少 ADR 目录，重要决策无固定载体 | 建立 `docs/adr/` 并新增 `0001`；后续决策按 `NNNN-<kebab-title>.md` 追加 |
| D-05 | `production-configuration-guide.md` 同时承载变量表与部署步骤，双份维护 | 拆分为 `docs/deployment/deployment-guide.md` 与 `docs/deployment/environment-variables.md`，原文件归档 |
| D-06 | 计划类文档散落 8 份且互相引用 | 2026-11-07 收敛为单份待办；2026-11-11 进一步合并为 `docs/planning/roadmap.md`，Stage 8–11 任务书与 closure-plan 已删除（历史见 Git） |
| D-07 | `agent-service/configuration.md` 与根运维手册重复 | 内容并入 `docs/deployment/environment-variables.md` 后删除原文件 |
| D-08 | PC 相关 ADR 与模块文档分散且部分过期 | 2026-11-11 将 PC 决策合并为 `docs/adr/0027-pc-config-decisions.md`，新增 `docs/adr/README.md` 索引；`docs/pc-config/` 由 14 份收敛为 8 份（`agent.md`、`data.md` 承接原工作流/状态/HITL 与数据模型/质量文档），历史见 Git |
