"""Agent 状态定义。

State 是贯穿整张图的"共享内存"：每个节点读取它、返回增量修改它。
"""

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """对话状态。

    messages 使用 add_messages 作为 reducer：
    节点返回 {"messages": [新消息]} 时，会被"追加"而不是覆盖原有历史。
    这是多轮对话能记住上下文的关键。

    偏好相关字段只描述「本轮」行为，每次调用都必须显式传入：
    不传时按默认值处理，避免上一轮的偏好残留到下一轮。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    # 用户偏好渲染出的提示词片段；None 表示不追加任何内容
    preference_prompt: NotRequired[str | None]
    # False 时模型只看到本轮消息，但消息仍会写入状态与业务表
    use_history: NotRequired[bool]

