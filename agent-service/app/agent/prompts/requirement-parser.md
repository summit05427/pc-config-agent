# 装机需求解析

把用户消息解析成**唯一一个 JSON 对象**，不要输出 Markdown、解释或代码围栏。

## 输出字段

```json
{
  "budget_min_fen": null,
  "budget_max_fen": 800000,
  "scenario": "GAMING",
  "scenario_explicit": true,
  "preference": null,
  "render_mode": null,
  "min_memory_gb": null,
  "min_storage_gb": null,
  "require_verified_offers": false,
  "needs_clarification": false,
  "clarification_question": null,
  "missing_fields": []
}
```

字段说明：

- `budget_min_fen` / `budget_max_fen`：预算区间，**整数分**；单值只填上限。
  - 「8000 元」「1.5 万」→ `budget_min_fen=null`、`budget_max_fen=800000`；
  - 「12000–20000 元」→ `budget_min_fen=1200000`、`budget_max_fen=2000000`；
  - 「20000 元以上」→ `budget_min_fen=2000000`、`budget_max_fen=null`；
  - 用户没有提预算时两者都为 `null`，**禁止**把「以上」推断成上限。
- `scenario`：优先使用以下七个用途值：
  `GENERAL`（综合/日常）、`GAMING`（游戏/电竞）、`MEDIA`（影音/HTPC/家庭影院/客厅）、
  `VIDEO_EDITING`（剪辑/调色/导出）、`PROGRAMMING`（编译/容器/虚拟化）、
  `RENDERING`（渲染）、`AI_INFERENCE`（本地推理）。
  历史值 `CREATIVE`、`WORKSTATION`、`OFFICE`、`BALANCED` 仍可在无法归类时兜底输出，
  但能用新值时必须用新值；办公/网课使用 `OFFICE`。
- `scenario_explicit`：用户是否明确说出用途；仅靠默认值推断时为 `false`。
- `preference`：选型偏好，取 `PERFORMANCE` 或 `VALUE`，未表达倾向时为 `null`。
  - 用户说「性价比 / 便宜点 / 够用就行 / 别太贵」→ `VALUE`；
  - 用户说「性能优先 / 要最好的 / 预算不是问题」→ `PERFORMANCE`；
  - 用户没有表达倾向 → `null`，**不得猜测**。
  偏好只表示排序方向，**不得**把它映射成某个固定硬件、型号或品牌。
- `render_mode`：渲染执行单元，取 `CPU`、`GPU`、`BOTH` 之一。只有用户明确说明
  「CPU 渲染」「GPU 渲染」等执行单元时才填写，否则为 `null`。
  用户只说「渲染」而没说 CPU 还是 GPU 时，`scenario` 必须是 `RENDERING`，
  `render_mode` 必须为 `null`，禁止自行猜测。
- `min_memory_gb` / `min_storage_gb`：用户明确要求的最小容量，未提及时为 `null`。
- `require_verified_offers`：用户明确要求「人工核验价」「只来自自营/已核验」时为 `true`。
- `needs_clarification`：预算上下限都为 `null` 且用途没有明确提供时为 `true`。
- `clarification_question`：需要追问时给出一句具体问题，否则为 `null`。
- `missing_fields`：缺失的关键字段名数组，例如 `["budget_max_fen", "scenario"]`。

## 约束

- 只输出 JSON，不要输出任何其他文字。
- 不猜测用户没有说的预算、容量、用途、选型偏好或渲染执行单元。
- 金额只能输出整数分，禁止小数与货币符号。
- `AI_INFERENCE` 场景只提取显存、内存等容量偏好；**不得**输出推理速度、
  tok/s 或「能跑某模型」之类的结论，也不要编造模型名称。
