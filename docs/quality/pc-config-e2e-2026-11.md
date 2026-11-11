# PC 配置 Agent 端到端联调报告（2026-11）

| 项 | 内容 |
| --- | --- |
| 状态 | Completed |
| 执行日期 | 2026-11-08 |
| 分支 | `feature/pc-config-agent` |
| 环境 | 本地宿主机：Java 18080、Agent 18000、前端 5273；中间件 `postgres` / `pgvector` / `redis` / `litellm` 容器 |
| 数据版本 | `catalogVersion=2026-11-08-demo-1`；`dataStatus=MIXED_DEMO`（10 条 `OWNER_VERIFIED` + 18 条 `MOCK_DEMO`） |
| 证据类型 | 接口请求与响应摘要、测试报告、运行日志（未做浏览器人工截图） |

## 1. 启动与预检

`scripts/dev/start-local.ps1` 配置预检 11 项通过、0 警告、0 失败；三端与中间件均就绪：

| 服务 | 地址 | 就绪探测 |
| --- | --- | --- |
| application-service | `http://127.0.0.1:18080` | `/actuator/health` → `status=UP` |
| agent-service | `http://127.0.0.1:18000` | `/api/v1/health/ready` → `checkpointer=up, redis=up` |
| frontend（Vite） | `http://localhost:5273` | 首页 200；`/api/v1` → 18080、`/agent/api/v1` → 18000 代理均通 |

Java 由 devtools 自动重启加载最新类；Agent 首次复用了改动前的旧进程，导致返回通用模型知识。已用 `scripts/dev/stop-local.ps1` 全量重启后才得到下述有效结果。**这是本次联调发现的唯一环境性问题，与业务代码无关。**

## 2. Java 内部接口

服务令牌 `POST /internal/v1/auth/service-token` 正常签发（300s）。

| 接口 | 结果 |
| --- | --- |
| `GET /internal/v1/pc/hardware/candidates` | 28 条，`catalogVersion=2026-11-08-demo-1` |
| `GET /internal/v1/pc/offers` | `dataStatus=MIXED_DEMO`、`priceUnit=CNY_FEN`、verified=10、demo=18、total=28 |
| `GET /internal/v1/pc/benchmarks` | 8 条（每类一条聚合跑分） |
| `POST /internal/v1/pc/builds/solve`（15000 元 / GAMING / 32G / 1T） | `solved=true`，总价 1,464,200 分，`WITHIN_BUDGET` |
| `POST /internal/v1/pc/builds/solve`（3000 元 / GAMING） | `solved=false`，`BUDGET_EXCEEDED`，最低可行 1,104,200 分，**不放宽预算** |
| `POST /internal/v1/pc/builds/solve`（`scenario=video_editing`） | `solved=true`，场景归一化为 `CREATIVE` |
| `POST /internal/v1/pc/builds/solve`（`scenario=MINING`） | 400 `10001`，字段级错误文案列出 8 个合法场景 |
| `GET /internal/v1/pc/builds/{buildId}` | 快照回读与求解结果一致，8 个组件 |
| `POST /internal/v1/pc/builds/validate` | `valid=true`，规则版本与求解一致 |
| 缺少 `X-User-Token` 读取快照 | 401 `40306` |

求解样例（GAMING，预算 15000 元）：

| 类别 | 型号 | 单价（分） | 价格来源 |
| --- | --- | --- | --- |
| CPU | Intel Core Ultra 7 265K | 186,900 | `OWNER_VERIFIED` |
| MOTHERBOARD | ASRock B860 Rock WiFi 7 | 119,900 | `MOCK_DEMO` |
| MEMORY | G.Skill Flare X5 64GB (2×32) DDR5-6000 CL30 | 359,900 | `MOCK_DEMO` |
| GPU | Radeon RX 9060 XT 16GB | 519,900 | `OWNER_VERIFIED` |
| PSU | MSI MAG A650GLS PCIE5 | 49,900 | `MOCK_DEMO` |
| CASE | Fractal Design Pop Air | 49,900 | `MOCK_DEMO` |
| COOLER | Thermalright Peerless Assassin 120 SE | 17,900 | `MOCK_DEMO` |
| STORAGE | Samsung 990 Pro 2TB | 159,900 | `MOCK_DEMO` |

## 3. Agent SSE 三组用例

请求：`POST /agent/api/v1/chat/stream`，`preferences={reply_language:zh-CN, response_style:balanced, use_history:true}`。

| 用例 | 输入 | 事件统计 | 耗时 | 结论 |
| --- | --- | --- | --- | --- |
| 预算可行 | 15000 元以内游戏主机，3A 大作，2K，32G 内存，2T 硬盘 | `tool_call=13`、`tool_result=13`、`token=1`、`done=1` | 18.4s | 生成 8 件配置单；`done.build_result` 存在；正文首行常驻演示价声明 |
| 预算不可行 | 预算 3000 元，想玩 3A 游戏 | `tool_call=12`、`tool_result=12`、`token=1`、`done=1` | 7.8s | 无 `build_result`；确定性 Markdown 兜底，明确「不放宽预算」并给出最低可行 11,042 元 |
| 缺关键信息 | 帮我配台电脑 | `token=1`、`done=1` | 8.1s | 无工具调用；只返回预算与用途追问 |

工具序列符合流水线设计：`search_hardware_candidates`（8 类）→ `get_benchmark_data` → `get_verified_offers` → `solve_pc_build` →（可行时）`validate_pc_build`。

`done.build_result` 抽样：

```json
{
  "total_price_fen": 1464200,
  "budget_max_fen": 1500000,
  "budget_status": "WITHIN_BUDGET",
  "overall_status": "UNKNOWN",
  "demo_offer_count": 6
}
```

## 4. 业务指标核对（对照计划 §8.2）

| 指标 | 结果 | 证据 |
| --- | --- | --- |
| 成功配置恰好八个类别 | 通过 | 求解与 `build_result` 均为 8 类且无重复 |
| 严格预算超支次数为 0 | 通过 | 1,464,200 ≤ 1,500,000；超预算请求被拒绝而非放宽 |
| 已知硬性兼容冲突进入成功方案 | 0 | `hasFailure=false`，8 条规则中 7 条 `PASS` |
| 虚构商品链接次数为 0 | 通过 | 19 条报价中 `purchase_url` 仅 10 条核验价为 `https://item.jd.com/{sku}.html` |
| 虚构价格次数为 0 | 通过 | 演示价单独标记 `MOCK_DEMO` 且 `purchase_url=null`，正文逐行标注「演示」「未核验」 |
| 无法验证的规格不得展示为已兼容 | 通过 | `cooler_case_height=UNKNOWN`（机箱未提供散热限高），总状态为 `UNKNOWN`，未被写成通过 |
| 工具错误不得伪装为正常推荐 | 通过 | 三组用例均无 `error` 事件；无解走确定性文案 |

## 5. 基础设施回归（对照计划 §8.3）

| 项 | 结果 |
| --- | --- |
| 登录 | 通过（管理员账号，返回 `roles=ADMIN`） |
| 刷新令牌 | 通过（`HttpOnly` Cookie 轮换，返回新 access token，`expiresIn=600`） |
| 会话列表 | 通过（中文标题正常，最近会话置前） |
| 历史消息 | 通过（`user` + `assistant` 两条，中文与 Markdown 完整） |
| SSE 事件 | 通过（`token` / `tool_call` / `tool_result` / `done`；PC 流水线内部 LLM 打 `TAG_NOSTREAM`，无泄漏的 `reasoning`） |
| 模型选择 | 通过（`GET /api/v1/models` 返回 2 个模型；会话建立后 `PUT /sessions/{id}/model` 可设置并可重置为 Auto） |
| 用户偏好 | 通过（`reply_language=zh-CN` 生效，`concise` 风格输出简短中文） |
| 未认证访问 | 通过（401） |

说明：会话首次创建前调用 `PUT /sessions/{id}/model` 返回 404 属既有契约（会话不存在），非回归。

## 6. 自动化测试结果

| 端 | 结果 |
| --- | --- |
| Java | 50 个 surefire 测试报告全部 `Failures: 0, Errors: 0`，`AgentApplicationServiceApplicationTests` 与各 `pcbuild` 测试均通过 |
| Agent | 历史记录：504 用例通过，覆盖率 92.23%（高于 90% 门禁）；本次联调未改动 Agent 测试 |
| 前端 | 历史记录：74 个测试文件、483 用例通过，行覆盖 92.64%；`lint:ci` / `type-check` 通过 |

## 7. 遗留问题与后续

1. **18 条 `MOCK_DEMO` 报价**待负责人在京东限流解除后用自营/官方旗舰店真实报价替换，再重跑 `scripts/pc-config/ingest_offers.py`。替换后 `dataStatus` 才会变为 `OWNER_VERIFIED`。
2. **机箱缺少散热限高字段**，导致 `cooler_case_height` 长期为 `UNKNOWN`；补齐 `case.max_cooler_height_mm` 后可转为确定性判断。
3. **最低可行总价 11,042 元**由当前 28 条候选决定，8000 元档位无解属于数据范围问题；扩充入门级候选后自然缓解，不应通过放宽求解规则解决。
4. 本地 `.env` 的 `AUTH_DEMO_PASSWORD` 为空，演示账号未创建（日志 `引导账号未配置口令，跳过创建 username=demo`）；联调使用管理员账号。若要恢复 demo 账号，需补口令后重启 Java。
5. 前端 UI 已做浏览器视觉验收（见 §8）：八硬件渲染、演示价提示、无解回退与 HITL 表单均由 `frontend/e2e/build-visual.spec.ts` 断言锁定，不再依赖人工在 `http://localhost:5273` 复现。
6. 联调产生的测试会话（`e2e-*`）保留在本地数据库中，未清理。

## 8. 前端视觉验收（P1-03，2026-11-10）

`frontend/e2e/build-visual.spec.ts` 用本地 SSE 假流 + mock 后端复现四组界面，只断言用户可见内容：

| 场景 | 断言要点 |
| --- | --- |
| 八件配置 | 硬件清单恰好 8 行；类别中文名与型号逐行配对；总价 `¥10,592.00`、预算徽标、选型理由均可见 |
| 演示价提示 | 顶部横幅 + 行内标签两处均出现，说明演示价不是只写在免责声明里 |
| 无解回退 | 只输出确定性文案，绝不渲染配置卡片（有卡片就等于给了不存在价格的方案） |
| HITL 表单 | 必填校验在本地拦截且不发请求；提交后表单消失；恢复请求携带 `interrupt_id` 与结构化答案 |

运行方式（Playwright 自动拉起 5273 端口开发服务器）：

```powershell
corepack pnpm --dir frontend e2e e2e/build-visual.spec.ts
```

截图落在 `frontend/e2e/__screenshots__/`（已在 `.gitignore`），供人工复核版式；判定以断言为准，截图不进 CI。

本次门禁结果：`e2e:critical` 18 条全绿；前端单测 75 个文件 / 503 用例通过，`test:coverage`（行覆盖 80% 阈值）通过。

验收中发现并修复：中断作答后旧表单仍留在页面上，用户会误以为可以改答案并重复提交（服务端只会返回「中断不存在」）。现在提交即清掉该消息的 `hitl` 并把状态置为完成，单测见 `message-model.spec.ts::clearAnsweredHitl`。
