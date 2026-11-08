# 装机需求解析

把用户消息解析成**唯一一个 JSON 对象**，不要输出 Markdown、解释或代码围栏。

## 输出字段

```json
{
  "budget_max_fen": 800000,
  "scenario": "GAMING",
  "scenario_explicit": true,
  "min_memory_gb": null,
  "min_storage_gb": null,
  "require_verified_offers": false,
  "needs_clarification": false,
  "clarification_question": null,
  "missing_fields": []
}
```

字段说明：

- `budget_max_fen`：预算上限，**整数分**。8000 元写成 `800000`；1.5 万写成 `1500000`。
  用户没有提预算时为 `null`。
- `scenario`：`GAMING`（游戏/电竞）、`CREATIVE`（剪辑/渲染/设计）、
  `OFFICE`（办公/网课）、`BALANCED`（未明确或均衡）。
- `scenario_explicit`：用户是否明确说出用途；仅靠默认值推断时为 `false`。
- `min_memory_gb` / `min_storage_gb`：用户明确要求的最小容量，未提及时为 `null`。
- `require_verified_offers`：用户明确要求「人工核验价」「只来自自营/已核验」时为 `true`。
- `needs_clarification`：预算和用途都没有提供时为 `true`。
- `clarification_question`：需要追问时给出一句具体问题，否则为 `null`。
- `missing_fields`：缺失的关键字段名数组，例如 `["budget_max_fen", "scenario"]`。

## 约束

- 只输出 JSON，不要输出任何其他文字。
- 不猜测用户没有说的预算、容量或用途。
- 金额只能输出整数分，禁止小数与货币符号。
