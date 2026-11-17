"""评测侧用量采集：从 LangChain 回调统计每条用例的模型调用次数与 token。

为什么不直接读图状态：结构化节点只把解析结果写回状态，消息通常不带
`usage_metadata`；回调是唯一同时覆盖结构化、文本兜底与流式三条路径的观测点。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult


@dataclass
class UsageTotals:
    """一条用例的累计用量；Provider 未回传 token 时保持 None，不能用 0 冒充。"""

    calls: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def add(self, prompt: int | None, completion: int | None) -> None:
        if prompt is not None:
            self.prompt_tokens = (self.prompt_tokens or 0) + prompt
        if completion is not None:
            self.completion_tokens = (self.completion_tokens or 0) + completion


class UsageCollector(AsyncCallbackHandler):
    """每个用例挂一个实例：一次 `on_llm_end` 记为一次计费调用。"""

    raise_error = False

    def __init__(self) -> None:
        super().__init__()
        self.totals = UsageTotals()

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.totals.calls += 1
        prompt, completion = _usage_from_result(response)
        self.totals.add(prompt, completion)


def _usage_from_result(response: LLMResult) -> tuple[int | None, int | None]:
    """优先读生成结果上的 `usage_metadata`，缺失时退回 `llm_output.token_usage`。"""
    for generation_list in response.generations:
        for generation in generation_list:
            message = getattr(generation, "message", None)
            usage = getattr(message, "usage_metadata", None)
            if isinstance(usage, dict):
                prompt = usage.get("input_tokens")
                completion = usage.get("output_tokens")
                if isinstance(prompt, int) or isinstance(completion, int):
                    return (
                        prompt if isinstance(prompt, int) else None,
                        completion if isinstance(completion, int) else None,
                    )

    llm_output = response.llm_output if isinstance(response.llm_output, dict) else {}
    token_usage = llm_output.get("token_usage")
    if isinstance(token_usage, dict):
        prompt = token_usage.get("prompt_tokens") or token_usage.get("input_tokens")
        completion = token_usage.get("completion_tokens") or token_usage.get("output_tokens")
        return (
            prompt if isinstance(prompt, int) else None,
            completion if isinstance(completion, int) else None,
        )
    return None, None
