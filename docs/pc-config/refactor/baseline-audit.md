# Stage 0 基线审计（2026-11-16）

| 项 | 内容 |
| --- | --- |
| 目的 | 冻结重构前的代码与数据基线，区分「已核对事实」与「仍依赖交接文档的说法」 |
| 方法 | 只读代码核对 + 对 `pc-config/*.json` 执行可复现统计；未启动服务、未复测求解耗时 |
| 关联 | [重构方案 §22](../planning/pc-config-agent-refactor-plan-v1.md)、[ADR 0028](../../adr/0028-llm-led-build-selection.md) |

## 1. 已核对事实

### 1.1 Agent 服务

| 事实 | 证据 |
| --- | --- |
| `candidate_retriever` 只把类别计数、缺失类别、跑分与报价统计写入 state，不写 `hardware_id` | `agent-service/app/agent/pc/nodes.py`（candidate_retriever） |
| 查询类工具单轮配额 12、`solve_pc_build`/`validate_pc_build` 配额 3；超时分别 10s 与 60s | `agent-service/app/agent/tools.py`、`pc/tools.py` |
| 模型调用只有纯文本与自由文本 JSON 抽取（`extract_json_object`），无 `with_structured_output` / `response_format` | `agent-service/app/agent/pc/llm.py` |
| 节点内模型失败返回 `None`，由确定性兜底接管 | 同上 |
| RAG 只有契约与注册机制（`Retriever` 协议、`NoopRetriever`、模块发现），无检索器实现、无入库、无语料 | `agent-service/app/rag/{base,registry,prompt}.py` |
| `preferences` 是聊天偏好（语言、风格、instructions），`Preference` 枚举只有 `PERFORMANCE` / `VALUE` | `agent-service/app/agent/preferences.py`、`pc/schemas.py` |

### 1.2 Java 服务

| 事实 | 证据 |
| --- | --- |
| 内网接口目前为 `/internal/v1/pc/builds/solve`、`/validate`、`GET /{buildId}` | `pcbuild/web/PcBuildInternalController.java` |
| `/validate` 的 DTO 八类字段全部 `@NotBlank`，缺一类返回 400 / `BUILD_INCOMPLETE` | `pcbuild/web/dto/ValidateRequest.java` |
| `BuildSolveService.validate` 遍历 `REQUIRED_CATEGORIES`，缺类别直接抛错，**不支持部分校验** | `pcbuild/application/BuildSolveService.java` |
| 兼容性规则为 **9 条**，全部 `BLOCKING`，含 `storage_motherboard_m2` | `pcbuild/domain/CompatibilityRule.java` |
| `/solve` 要求 `X-User-Token`，`/validate` 不要求 | `PcBuildInternalController.java` |

### 1.3 数据（可复现统计）

| 指标 | 数值 |
| --- | --- |
| 目录硬件总数 | 402（CPU 71 / GPU 66 / MEMORY 60 / MOTHERBOARD 60 / STORAGE 53 / PSU 40 / CASE 26 / COOLER 26） |
| `platform_pairs` | 0 |
| 重复型号 | 13 组，多出 15 行；RTX 5080 共 4 行、5090 共 2 行、5060 8GB 共 4 行 |
| `lifecycle_status` 缺失或 `UNKNOWN` | 77 / 402 |
| `data_quality_status` | `VERIFIED_STRUCTURED` 333 / `PARTIAL` 68 / `BLOCKED` 1 |
| 报价总数 | 402，全部 `PLATFORM_OBSERVED`；`mock_offer_count=0`；`verified_offer_count=0`（修正计数口径后） |
| 报价库存字段 | 无 `availability_status` |
| 跑分 | 169 条（CPUMARK 71 / G3D_MARK 66 / DISKMARK 32），21 条 unmatched；STORAGE 53 条中约 21 条无跑分 |

## 2. 仍依赖交接文档、尚未复核

1. 求解器实测耗时（约 29s，p95 约 45s）与组合搜索规模 —— 未重跑基准测试。
2. 九节点图的路由与 SSE 事件映射 —— 未逐行核对 `graph.py` / `turn.py` / `chat.py`。
3. 前端类型与 `done.build_result` 消费字段 —— 未读 TypeScript 定义。
4. LiteLLM 部署的模型是否支持 JSON Schema 约束解码 —— 未在运行环境验证。
5. 候选/跑分/报价的 Controller 实现（`pc_client.py` 有客户端映射，未逐个核对 Controller）。

## 3. 缺口与风险

| 编号 | 风险 | 级别 | 影响 |
| --- | --- | --- | --- |
| R1 | 无任何 `OWNER_VERIFIED` 报价 | 高 | 「真实可购买报价」验收项不可达，按 ADR 0028/方案 D7 走双轨标注 |
| R2 | 无部分兼容性校验能力 | 高 | 逐步组装与针对性修正无法闭环 |
| R3 | 无结构化输出调用层 | 中 | BuildProposal 无法可靠解析，只能用自由文本抽取（方案已禁止） |
| R4 | RAG 为空壳且无语料 | 中（需求项则高） | Stage 3 全新建，语料周期最长 |
| R5 | 数据缺口（lifecycle 19%、存储无跑分、21 条未匹配） | 中 | `UNKNOWN` 高频触发修正循环 |
| R6 | 重复型号 13 组 15 行 | 低-中 | 候选池被同型号占位 |
| R7 | 求解耗时未复测 | 中 | Stage 1 的 p95 判据缺基线 |
| R8 | 前端无结构化软偏好输入 | 中 | 静音/体积/升级只能靠自然语言抽取 |
| R9 | `/validate` 无用户上下文 | 中 | 新主路径的鉴权口径不一致 |
| R10 | 文档漂移（「8 条规则」） | 低 | 已修交接文档与求解器文档；历史报告保留原样 |
| R11 | 工作区未提交改动（约 80 个文件，含 Agent、Java、前端） | 高 | 基线未真正冻结，回滚点不明确；Stage 0 必须先确定提交/分支策略 |

## 4. 本轮已执行

1. `scripts/data-cleaning/build_offers_from_shortlist.py` 计数改为按 `price_source` 统计，并重新生成 `offers.json`：`verified=0 / mock=0 / observed=402`。
2. 交接说明 §6.3/§6.4 与 `solver-and-compatibility.md` 的规则数改为九条，并补 `storage_motherboard_m2`。
3. 新增 [ADR 0028](../../adr/0028-llm-led-build-selection.md)，改写术语表「求解器」并新增四个概念。
4. 重构方案新增 §22（勘误、决策、退出判据、Stage 0 必做项）。

## 5. 待决策

1. 重复型号保留策略（按数据质量、报价时效还是销量）。
2. `lifecycle_status` 缺失 77 条：补标还是显式 `UNKNOWN` 并允许召回。
3. 存储类无跑分的展示与选型策略。
4. 单次成本上限 ¥0.3 是否确认（当前为评审默认值）。
