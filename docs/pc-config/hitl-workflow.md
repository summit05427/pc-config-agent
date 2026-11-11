# HITL（人在回路）工作流

> 状态：批 2 已完成；默认关闭（`HITL__ENABLED=false`），关闭时链路与接入前完全一致。
> 代码：`agent-service/app/agent/pc/hitl.py`、`graph.py`、`app/api/v1/chat.py::_validate_resume`、`app/services/turn.py`。

## 1. 触发条件

| 门控节点 | 触发条件 | 交互类型 |
| --- | --- | --- |
| `clarification_gate` | `requirement_validator` 判定 `workflow_status=clarification`（缺预算/用途等关键槽位） | `clarify_requirements` |
| `compatibility_gate` | `build_validator` 复核结果为 `SUCCESS` 且整体兼容性 `UNKNOWN` | `confirm_compatibility` |

以下情况**不中断**：

- `HITL__ENABLED=false`（默认）：两个门控节点原样返回 `{}`。
- 兼容性为 `PASS` / `FAIL`：失败由既有 `response_generator` 输出确定性说明。
- 预算超限：Java 求解只返回 `WITHIN_BUDGET` / `NO_BUDGET`，`OVER_BUDGET` 不可达，因此不设预算门控。

## 2. 一轮完整时序

```
客户端 POST /api/v1/chat/stream（message）
  → requirement_parser → requirement_validator
  → clarification_gate（缺槽位时 interrupt）
  → SSE: interrupt（本轮结束，不发 done）
客户端 POST /api/v1/chat/stream（同 thread_id + resume{interrupt_id, answer}）
  → 校验 interrupt_id / TTL / 存储
  → 从 checkpoint 续跑：只重跑 clarification_gate
  → 合并补充信息 → requirement_parser → … → response_generator
  → SSE: token / done
```

- 恢复复用 `POST /api/v1/chat/stream`，不新增端点；请求体新增 `resume` 字段，与 `regenerate=true` 互斥（422 `validation_error`）。
- 门控节点无副作用且位于 `build_solver` / `build_validator` 之后，恢复不会重放求解与落库写操作。
- 兼容性门控选择 `abort` 时写入 `workflow_status=aborted`，`renderer` 输出固定终止文案，本轮正常 `done`。

## 3. 中断载荷

```json
{
  "interrupt_id": "int-1",
  "interaction_type": "clarify_requirements",
  "question": "请补充预算和主要用途，我再为你推荐具体配置。",
  "input_schema": {
    "fields": [
      { "name": "budget_yuan", "label": "预算上限（元）", "type": "number", "required": true, "min": 1 },
      { "name": "scenario", "label": "主要用途", "type": "select", "required": false, "options": [{ "value": "GAMING", "label": "游戏" }] }
    ],
    "submit_label": "继续生成配置"
  },
  "context": { "missing_slots": ["budget_max_fen", "scenario"] },
  "schema_version": "1"
}
```

- `interrupt_id` 由 LangGraph 生成，客户端必须原样回传；服务端不自行编号。
- 字段 `type` 仅支持 `number` / `select` / `radio` / `text`；`options[].value` 必须来自固定枚举。
- 载荷只含用户可见信息，不带内部图状态、令牌或服务地址。

## 4. 恢复校验（返回流之前）

| 条件 | HTTP | code |
| --- | --- | --- |
| `HITL__ENABLED=false` 或 `STORAGE__BACKEND != postgres` | 409 | `hitl_unavailable` |
| `thread_id` 没有待恢复中断 | 409 | `interrupt_not_found` |
| `interrupt_id` 与当前中断不一致 | 409 | `interrupt_mismatch` |
| 距 checkpoint 创建超过 `HITL__INTERRUPT_TTL_SECONDS` | 409 | `interrupt_expired` |
| `resume` 与 `regenerate` 同时出现 | 422 | `validation_error` |
| 回答缺少必填字段或取值非法 | 422（流内 `error` 事件） | `hitl_resume_invalid` |

## 5. 历史与持久化

- 提问文案在中断前由 `requirement_validator` / `build_validator` 追加 `AIMessage` 落库，恢复时历史里能看到本轮提问。
- 恢复时用户补充并入最后一条 `HumanMessage`（复用其 `id` 触发 `add_messages` 替换语义），不产生重复提问。
- 恢复回合以 `replace_existing=True` 覆盖写入本轮消息，避免 postgres `seq` 冲突与历史重复。
- 中断态不发送 `done`，前端把 `interrupt` 视为本轮终态（`awaiting_input`），刷新历史后表单不会重建，需在本轮内完成回答。

## 6. 存储约束

- 中断依赖 LangGraph checkpointer，只有 `STORAGE__BACKEND=postgres` 会持久化；`memory` 后端进程重启即丢失，无法恢复。
- 因此配置层强制：`HITL__ENABLED=true` 且 `storage.backend != "postgres"` 时启动即 `ValueError`，不做静默降级；`hitl.py::_ensure_hitl_available` 在运行期再兜底一次（防热更新绕过）。

## 7. 关闭时的回归保证

- 两个门控节点在关闭时直接返回 `{}`，图结构虽新增节点，但路由与输出不变。
- 提问 `AIMessage` 只在开启时追加，历史与既往会话一致。
- 全量 555 个后端测试与 `evals --fake` 在默认关闭下通过。
