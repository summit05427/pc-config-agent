# 用单一 PC 配置工作流替换通用聊天

| 项 | 内容 |
| --- | --- |
| 状态 | Accepted |
| 决策日期 | 2026-11-08 |
| 相关 | `docs/planning/pc-config-implementation-plan.md`、ADR-0010、ADR-0012 |

## 背景

模板当前的核心是通用 ReAct 图与多 Agent Profile：`build_agent` 用 `StateGraph(AgentState)` 装配 `model` 与 `tools` 两个节点，靠 `tools_condition` 在“调工具 / 直接回答”之间循环；请求通过 `agent_id` 选择人格、工具集与模型参数。

本次产品目标只有一个——PC 配置智能推荐。继续维护通用聊天会带来两套图、两套 State、两套 Prompt 与两套测试的长期成本；而把 PC 工作流做成通用图上的一个 Profile 分支，则会让“确定性求解、零超支、零幻觉链接”这些硬指标无法保证。

## 决策

1. **删除通用 ReAct 图**：`graph.py` 中的 `model` / `tools` 节点、`ToolNode`、`tools_condition` 全部移除；`build_agent` 保留函数名与签名，内部改为装配 PC 图。
2. **唯一工作流是确定性流水线**：

   ```text
   START
     → requirement_parser      LLM 结构化输出（TAG_NOSTREAM）
     → requirement_validator   纯代码校验
     → candidate_retriever     工具调用
     → build_solver            工具调用（Java 求解）
     → build_validator         工具调用；失败最多重解 1 次
     → response_generator      LLM 摘要 + 代码渲染
     → END
   ```

   LLM 只出现在解析与生成两个节点；选型、价格、兼容性判断全部在 Java 中完成。
3. **节点直接调用治理后的工具**，不把工具交给 LLM 自主选择。为保留前端工具进度，节点在状态更新中返回 `tool_events`，由 `turn.py` 映射为既有 `tool_call` / `tool_result` 事件；SSE 事件类型与 payload 形状不变。
4. **解析节点的模型调用打 `TAG_NOSTREAM`**，避免结构化 JSON 以 `token` 事件漏进正文流。
5. **保留聊天基础设施**：`chat.py` 传输层、`sse.py` 与 `turn.py` 的事件翻译、会话存储、模型运行时、鉴权、会话级模型选择与聊天偏好。
6. **保留 Profile 加载与校验机制，但仓库只保留 `pc-config.yaml`**。不做 workflow dispatcher；未知 `agent_id` 继续返回 404。
7. **删除通用图测试与示例评测用例，同步补齐 PC 图测试**；回归基线调整为基础设施回归。不得以减少断言换取通过率。

## 考虑过的替代方案

- **保留双图，前端只开 PC 入口**：改动更小，但通用图仍占用维护与回归成本，且未来容易被误用。
- **保留通用图作为 fallback**：需要 dispatcher 与两套 State 的 checkpointer 兼容验证，收益仅为“以后可能恢复聊天”，与当前产品目标不符。
- **保留 ReAct 循环，只替换工具**：实现最快，但 LLM 可能跳过求解工具直接编造配置，无法满足预算与真实性指标。
- **在通用图上加 PC 分支节点**：同一张图混入两套状态语义，`turn.py` 的落库与事件翻译会同时承担两种模式，属于长期负债。

## 影响

- 这是破坏性变更，必须单独提交并保留 `git revert` 回退路径。
- `PCConfigState` 必须包含 `messages` / `preference_prompt` / `use_history`，否则 `turn.py` 的输入与落库需要大改。
- `response_generator` 必须把最终回答写入 `messages`，历史接口才可回放。
- 通用图的评测 runner 改造为 PC 图评测，不能直接删除评测入口。
- `ChatRequest.agent_id` 可暂时保留为可选字段但不再参与分流，避免一次性改完前端与评测脚本。
- 未来若恢复通用聊天，应作为新的 ADR 重新引入，而不是在 PC 图中加分支。
