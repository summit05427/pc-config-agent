"""PC 配置推荐的图状态。

`messages` / `preference_prompt` / `use_history` 由 `turn.py` 原样写入并消费；
其余字段只在图内流转。状态里不得出现密钥、服务令牌、完整 JWT 或全量商品列表。
"""

from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class PCConfigState(TypedDict):
    """六节点确定性流水线的共享状态。"""

    # turn.py 契约字段：必须保留
    messages: Annotated[list[AnyMessage], add_messages]
    preference_prompt: NotRequired[str | None]
    use_history: NotRequired[bool]

    # 流水线字段
    requirements: NotRequired[dict[str, Any] | None]
    validation_result: NotRequired[dict[str, Any] | None]
    candidate_pool: NotRequired[dict[str, Any] | None]
    build_result: NotRequired[dict[str, Any] | None]
    build_failure: NotRequired[dict[str, Any] | None]
    compatibility_report: NotRequired[dict[str, Any] | None]
    budget_report: NotRequired[dict[str, Any] | None]
    reason_summary: NotRequired[str | None]
    retry_count: NotRequired[int]
    workflow_status: NotRequired[str]
    # 节点不直接发 SSE：统一累积事件，由 turn.py 翻译成 tool_call / tool_result
    tool_events: NotRequired[Annotated[list[dict[str, Any]], lambda left, right: left + right]]
