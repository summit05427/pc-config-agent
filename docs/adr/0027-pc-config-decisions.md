# PC 配置模块决策合并记录

| 项 | 内容 |
| --- | --- |
| 状态 | Accepted |
| 决策日期 | 2026-11-11（承接 2026-11-08 至 2026-11-09 的 PC 相关决策） |
| 承接范围 | 原 ADR 0009–0026 中与 PC 配置相关的全部有效决策 |
| 替代说明 | 原 PC 相关 ADR 文件已合并进本文件并由 Git 保留历史；模板类 ADR 0001、0004–0008 不受影响 |
| 相关 | [roadmap](../planning/roadmap.md)、[pc-config 文档集](../pc-config/README.md)、[API 契约](../api-contract.md) §5.7 |

> 本文件是 PC 配置模块架构决策的唯一权威。各节标题后标注原 ADR 编号，便于从历史提交追溯。

## 1. 工作流与输出（原 ADR 0009、0010）

### 1.1 用单一 PC 工作流替换通用聊天（0009）

1. 删除通用 ReAct 图（`model` / `tools` 节点、`ToolNode`、`tools_condition`），`build_agent` 保持函数名与签名，内部装配 PC 图。
2. 唯一工作流是确定性流水线：`requirement_parser → requirement_validator → [clarification_gate] → candidate_retriever → build_solver → build_validator → [compatibility_gate] → response_generator`。LLM 只出现在解析与生成两个节点。
3. 节点直接调用治理后的工具，不交给 LLM 自主选择；节点返回 `tool_events`，由 `turn.py` 映射为既有 `tool_call` / `tool_result` 事件。
4. 解析节点的模型调用打 `TAG_NOSTREAM`，避免结构化 JSON 以 `token` 事件漏进正文流。
5. 保留聊天基础设施（`chat.py`、`sse.py`、`turn.py`、会话存储、模型运行时、鉴权）与 Profile 加载机制，但仓库只保留 `pc-config.yaml`；未知 `agent_id` 继续 404。
6. 删除通用图测试与示例评测用例，同步补齐 PC 图测试；不得以减少断言换取通过率。

### 1.2 配置结果由后端确定性渲染（0010）

1. Java 返回的结构化 `BuildResult` 是配置结果的唯一事实来源。
2. `response_generator` 用代码模板渲染 Markdown，经 `token` 事件输出，作为兜底与导出形式。
3. `done` 事件保留 `thread_id`，追加可选 `build_result`；旧客户端忽略即可，不构成破坏性变更。
4. 前端 `BuildResultCard` 读取 `build_result`；字段缺失时回退 `MarkdownContent`，保证历史会话可回放。
5. LLM 只生成推荐摘要与理由，不接触型号、价格、链接、SKU 与总价。

## 2. 报价与商品映射（原 ADR 0011、0018、0019、0020、0021）

### 2.1 报价以文件承载，不建新表（0018）

1. 报价继续由 `application-service/src/main/resources/pc-config/offers.json` 承载，由 `JsonOfferRepository` 启动期读取；发布方式为「内存校验通过后整份重写」。
2. 不新建 Offer、Product Mapping、Import Batch 表，不新增 Flyway 迁移；沿用 `catalog_version`，用 `observed_at` 与发布清单批次区分同版本内的多次发布。
3. 商品映射是离线产物，不是运行时实体。
4. 数据库化留待报价规模达到数千条或需要并发写入时重开本决策。

### 2.2 价格来源三值分离（0019）

1. `price_source` 取值：`OWNER_VERIFIED`、`PLATFORM_OBSERVED`、`MOCK_DEMO`。
2. 生产求解只接受 `OWNER_VERIFIED`；`PLATFORM_OBSERVED` 可进入 `offers.json` 与证据展示，但不得参与求解。
3. 三类来源分别计数：`verified_offer_count`、`mock_offer_count`、`observed_offer_count`。
4. 必须修复降级路径：重试时不得静默退到未核验价；`candidate_retriever` 的 `verified_only` 是显式配置项。

> 2026-11-11 实测偏差：`requireVerifiedOffers` 默认 `false`，3,809 条 `PLATFORM_OBSERVED` 默认参与求解，与第 2 条冲突。见 [roadmap §5.4](../planning/roadmap.md) S9-05，修复前不得宣称「生产只用核验价」。

### 2.3 非商业研究定位（0020）

1. 项目定位为本地化、封闭式、非商业学术研究；`chengkit-taobao` 不标记 BLOCKED，不做代码隔离。
2. 允许将其解析的商品数据导入报价产物；不复制其源代码；数据必须标注来源、价格出处与采集时间。
3. 出现对外交付、商业收益、公开发布数据或更换使用主体时，立即暂停对应数据链路并重新评估。
4. 风险由项目负责人书面兜底，定位与失效条件维护在 [market-offer-management.md](../pc-config/market-offer-management.md)。

### 2.4 报价核验改为确定性规则（0021）

1. 取消人工逐条核对，改为规则核验：通过则写 `price_source=OWNER_VERIFIED`、`verification_method=RULE`；否则保持 `PLATFORM_OBSERVED`。
2. 五条规则：身份一致（MPN 或完整型号 token）、关键规格逐项一致、价格为正整数分且与页面原文一致、必备字段完整、同一硬件只允许一条通过核验的报价。
3. 规则版本写入发布清单，规则必须有单元测试；规则变化等同于数据口径变化。
4. `verification_method=MANUAL` 保留给将来的人工复核，不作为本期路径。
5. 价格分布异常只告警不阻断；阈值调整必须走文档与测试变更。

> 原 ADR 0011 的人工核验条款由本节取代；人民币分、无报价不得进入成功方案两条继续有效。购买链接改为「来源展示字段」：可空、不校验店铺与可达性，仅保留非空时的 `http(s)` 安全校验（防止 `javascript:` 注入）。

### 2.5 价格观测入库，目录继续用文件（2026-11-11 重开 0018）

触发条件已满足（3,837 条报价、需要价格历史与来源追溯），结论调整如下：

1. `catalog.json` 继续作为发布产物随镜像发布，不建硬件主数据表。
2. 新增 `price_observation` 表承载价格观测，append-only（只插入，不更新、不删除）；`price_current` 视图按 `price_basis` 精度与 `observed_at` 取当前价。
3. 灰度期间 Java 仍读 `offers.json`，发布时由同一批数据导出，保证 Solo 模式离线可跑。
4. 入库目标是「可追溯、可查历史、可按 `valid_until` 过滤」，**不承诺提升价格准确度**；价格准确性由 `price_basis` 分层与来源锚点解决。
5. 读路径切换前不得删除 `offers.json`；切换后保留一个版本的导出用于回滚。

## 3. 硬件主数据治理（原 ADR 0013、0014、0015、0016、0017）

### 3.1 JSONL 为权威治理产物（0013）

1. 治理产物落在仓库内 `data/pc-config/`，JSONL 为权威格式，Parquet 仅派生。
2. 原始 PCPartPicker / PassMark 数据保持外部只读，不进入仓库。
3. 许可未核实前 `distribution_status=INTERNAL_ONLY`，全量 `master/`、`pools/`、`export/`、`staging/` 不进版本库；只提交 README、manifest、schema、samples、脚本与报告。
4. `manifest` 必须记录批次、输入 `sha256`、脚本摘要、八类计数与分发状态。

### 3.2 治理结论独立为 governance_status（0014）

1. `data_quality_status` 的取值、语义、Java 代码与夹具保持不变。
2. 新增独立字段 `governance_status`（`VALID` / `INCOMPLETE` / `INVALID` / `CONFLICT`），只在治理产物与候选池规则中使用。
3. 五个状态字段相互独立：`data_quality_status`、`governance_status`、`lifecycle_status`、`market_status`、`recommendation_status`。
4. 禁止旧值映射成新枚举，禁止新枚举出现在运行时 `catalog.json`。

### 3.3 生命周期 UNKNOWN 不等于 EXCLUDED（0015）

1. 生命周期分类按类别推进：CPU 按 Socket 代际、GPU 按 Chipset、主板按 Socket + Chipset、内存按 DDR、存储按接口；散热、机箱、电源默认 `UNKNOWN`。
2. 只使用结构化字段与参考表，禁止用 LLM 记忆或未核实推测补全。
3. `UNKNOWN` 不自动 `EXCLUDED`；`CURRENT` 不自动 `ELIGIBLE`；推荐资格由 §3.4 规则单独计算。
4. 允许人工覆盖（`reference/manual-overrides.json`），覆盖项必须在报告中计数。

### 3.4 推荐资格规则

| 类别组 | 规则 |
| --- | --- |
| CPU / GPU | `governance=VALID` 且 `lifecycle∈{CURRENT,MATURE}` → `ELIGIBLE`；`LEGACY` / `UNKNOWN` → `RESTRICTED`；`DISCONTINUED` → `EXCLUDED`；`INVALID/CONFLICT` → `EXCLUDED` |
| 主板 / 内存 / 存储 | 兼容性关键字段齐全且 `governance∈{VALID,INCOMPLETE}` → `ELIGIBLE`；缺关键字段 → `RESTRICTED` |
| 散热 / 机箱 / 电源 | 关键规格齐全 → `ELIGIBLE`（`lifecycle=UNKNOWN` 不阻断）；缺字段 → `RESTRICTED` |
| 任意类别 | 人工覆盖优先；`ARCHIVED` 不参与求解 |

### 3.5 Stage 8 只产出离线资产（0016）

1. Stage 8 不修改 `pcbuild` 模块、不新增 Java 只读接口、不替换 classpath `catalog.json`、不调整既有测试断言。
2. 验收口径是「标准化硬件资产可发布、可追溯、可重复生成」，不以推荐覆盖率作为验收项。
3. 第三方商品导入、`hardware_id` 关联与 `OfferRepository` 接入由 Stage 9 承担。
4. `hardware_id` 必须稳定，作为跨阶段唯一回关联键；现有 28 条基线 ID 不得变化。

### 3.6 ETL 单一入口（0017）

1. 原地演进 `scripts/pc-config/` 为唯一 ETL 入口，复用现有解析器与 `PC_DATA_DIR`，不新建第二套流水线。
2. 新脚本必须 import 现有解析器，不得复制解析逻辑。
3. CI 新增 `data` 过滤与任务：`scripts/pc-config/**`、`data/pc-config/{schema,samples,manifest}/**` 变化时运行 `pytest scripts/pc-config/tests` 与 Schema/样本校验。
4. 全量数据验证不进云端 CI，由 `scripts/pc-config/verify-release.ps1 -DataDir <路径>` 提供本地验收入口，非零退出即失败。

## 4. 快照、评分与兼容性（原 ADR 0012、0022、0023、0024、0025）

### 4.1 求解快照落库（0012）

1. 求解成功后在同一事务写入 `pc_build_snapshots`，失败不写库。
2. 快照保存需求、八类组件、总价与预算、兼容性报告、跑分与报价快照、`solver_version`、`compatibility_rule_version`、`catalog_version`。
3. 表为 append-only；读取必须同时匹配 `build_id` 与 `user_id`，不存在或越权统一返回 `40302`。
4. 历史快照不可变；规则升级与价格更新不得回填或改写。

### 4.2 评分配置版本写入快照 JSON（0024）

1. 评分配置与权重随结果写入 `snapshot` 的 JSON 字段，不新增数据库迁移。
2. 只保存复现所需的最小依据：用途画像、评分策略版本、各分项得分与关键参数。
3. 不为保存全部中间计算过程而扩大快照。

### 4.3 兼容性 UNKNOWN 必须分级（0023）

1. 每条规则声明 `risk_level`：`BLOCKING`（关键物理/电气约束）或 `ADVISORY`（辅助信息）。
2. `BLOCKING` 的 `UNKNOWN` 阻止方案被标记为「完全验证通过」，但不等于 `FAIL`，方案仍可生成并显示「待核验」。
3. `ADVISORY` 的 `UNKNOWN` 允许继续求解，只在结果中提示。
4. 所有规则必须有唯一 ID、版本、涉及类别、输入字段、判断条件、结果状态、失败原因、用户可读解释与数据依据。

### 4.4 九条兼容规则全部为 BLOCKING（0025）

1. CPU 插槽、内存类型、主板板型、显卡长度、散热器插槽、散热器限高、显卡供电与电源功率、存储接口、内存条数不超过主板插槽数，全部 `BLOCKING`。
2. `ADVISORY` 保留枚举但本期不启用。
3. 接受后果：机箱限高数据补齐前，每套方案都会显示「待核验」；不得靠改规则分级绕过。
4. `CompatibilityReport.RULE_VERSION = pc-compat-2.0.0`。

### 4.5 Stage 10 不扩展运行时目录（0022）

1. Stage 10 只在当时的运行时夹具上改造规则与评分；数据接入运行时作为独立阶段评审。
2. 验收报告必须逐项标注「算法层已通过 / 真实规模 E2E 未完成」。
3. 大规模候选测试只能使用隔离 fixture，不得修改 `offers.json` 或采集数据。

> 2026-11-11 实测（历史时点）：运行时目录已扩到 3,974 款、报价 3,837 条，但真实规模 E2E 仍受报价可信度缺口阻塞，见 [roadmap §5.4](../planning/roadmap.md)。
>
> 2026-11-12 更新：目录已收敛为 402 款国内可购候选，`offers.json` 由 `scripts/data-cleaning/build_offers_from_shortlist.py` 同源生成（402 条，`data_status=PLATFORM_OBSERVED_ONLY`）。本 ADR 中"3,974 / 3,837"仅代表旧 Stage-8 离线治理规模，不再是运行时事实。

## 5. MCP 只做客户端（原 ADR 0026）

1. `agent-service` 保持 MCP 客户端能力（默认关闭），不对外暴露 MCP Server。
2. 不新增第三方 MCP 工具依赖；工具仍经 `get_governed_tool` 注册与治理。
3. 需要外部能力时优先复用现有 HTTP 内部接口，避免引入第二套鉴权与审计边界。

## 6. 影响与维护

- 本文件取代原 PC 相关 ADR 的规范效力；历史讨论与替代方案见 Git 历史与 [roadmap](../planning/roadmap.md)。
- 新增 PC 决策优先以新 ADR 记录并回链本文件；不要在本文件内追加与既有条款冲突的段落。
- 涉及运行时契约的决策必须同步 [api-contract.md](../api-contract.md)、Agent Schema、前端类型与测试。
- 实测偏差应登记到 [roadmap §8](../planning/roadmap.md)，不得通过修改本文件的决策描述来掩盖。
