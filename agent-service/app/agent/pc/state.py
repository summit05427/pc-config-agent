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
    # 配置策略与来源（MODEL / DEFAULT）；DEFAULT 表示模型不可用后的确定性兜底
    build_strategy: NotRequired[dict[str, Any] | None]
    strategy_source: NotRequired[str | None]
    candidate_pool: NotRequired[dict[str, Any] | None]
    # 按类别保留的候选摘要；只含决策字段，不复制工具原始输出
    candidate_sets: NotRequired[dict[str, list[dict[str, Any]]]]
    # 因单类上限被截断的条数；只记录实际发生截断的类别
    candidate_truncated: NotRequired[dict[str, int]]
    build_result: NotRequired[dict[str, Any] | None]
    build_failure: NotRequired[dict[str, Any] | None]
    # LLM 选型产物与修正计数
    build_proposal: NotRequired[dict[str, Any] | None]
    architect_repair_count: NotRequired[int]
    # 提交整机前的增量校验：报告与已用次数（同一回合内累计，受配置上限约束）
    partial_compatibility_reports: NotRequired[list[dict[str, Any]]]
    partial_check_count: NotRequired[int]
    # 知识检索引用（函数级业务引用）与已用次数；由 turn.py 去重后下发 citations 事件
    knowledge_citations: NotRequired[list[dict[str, Any]]]
    knowledge_call_count: NotRequired[int]
    compatibility_report: NotRequired[dict[str, Any] | None]
    reason_summary: NotRequired[str | None]
    # 质量评审：问题列表、可下发提示与重解反馈（仅图内流转）
    quality_review: NotRequired[dict[str, Any] | None]
    quality_notice: NotRequired[str | None]
    # 结构化质量反馈：失败类型、逐项发现与必须保持不变的类别
    quality_feedback: NotRequired[dict[str, Any] | None]
    quality_retry_count: NotRequired[int]
    workflow_status: NotRequired[str]
    # 节点不直接发 SSE：统一累积事件，由 turn.py 翻译成 tool_call / tool_result
    tool_events: NotRequired[Annotated[list[dict[str, Any]], lambda left, right: left + right]]
