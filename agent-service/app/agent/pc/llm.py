"""节点内的模型调用：统一打 `TAG_NOSTREAM`、记录用量并执行安全钩子。

`TAG_NOSTREAM` 必须加在每次节点内调用上：结构化 JSON 和解释文案都不能进入
`stream_mode=messages` 的正文流，否则前端会把中间产物当成回答。
模型失败时不抛出，由节点回退到确定性数据。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import TAG_NOSTREAM
from pydantic import BaseModel

from app.agent.hooks import HookContext, HookPoint, run_hooks
from app.core.config import get_settings
from app.core.metrics import LLM_TOKENS_TOTAL
from app.services.model_resolver import ResolvedRuntime
from app.services.model_usage import STATUS_FAILURE, STATUS_SUCCESS, UsageRecord, record_usage

logger = structlog.get_logger(__name__)


def runtime_from_config(config: RunnableConfig | None) -> ResolvedRuntime | None:
    """运行时只从 configurable 读取，绝不写进状态，避免被 checkpointer 持久化。"""
    if not config:
        return None
    runtime = (config.get("configurable") or {}).get("model_runtime")
    return runtime if isinstance(runtime, ResolvedRuntime) else None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _extract_token_usage(message: BaseMessage) -> tuple[int | None, int | None]:
    """Provider 未返回 usage 时保持 None，不能用 0 冒充。"""
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None, None
    prompt_tokens = usage.get("input_tokens")
    completion_tokens = usage.get("output_tokens")
    return (
        int(prompt_tokens) if isinstance(prompt_tokens, int) else None,
        int(completion_tokens) if isinstance(completion_tokens, int) else None,
    )


def _record_token_usage(
    message: BaseMessage, model_label: str
) -> tuple[int | None, int | None]:
    input_tokens, output_tokens = _extract_token_usage(message)
    if input_tokens:
        LLM_TOKENS_TOTAL.labels(model=model_label, type="input").inc(input_tokens)
    if output_tokens:
        LLM_TOKENS_TOTAL.labels(model=model_label, type="output").inc(output_tokens)
    logger.info(
        "pc.llm_usage",
        model=model_label,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return input_tokens, output_tokens


def _build_usage_record(
    runtime: ResolvedRuntime,
    invocation_id: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_ms: int,
    error_type: str | None,
) -> UsageRecord:
    return UsageRecord(
        invocation_id=invocation_id,
        task_id=runtime.task_id,
        model_role=runtime.model_role,
        provider=runtime.provider,
        model_key=runtime.model_key,
        credential_source=runtime.credential_source,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        status=STATUS_FAILURE if error_type else STATUS_SUCCESS,
        error_type=error_type,
        occurred_at=_utc_now_iso(),
    )


async def _report_usage(
    runtime: ResolvedRuntime | None,
    invocation_id: str,
    response: BaseMessage | None,
    latency_ms: int,
    error_type: str | None,
) -> None:
    model_label = runtime.model_key if runtime is not None else get_settings().llm.model
    if response is not None:
        prompt_tokens, completion_tokens = _record_token_usage(response, model_label)
    else:
        prompt_tokens, completion_tokens = None, None
    if runtime is not None:
        await record_usage(
            _build_usage_record(
                runtime,
                invocation_id,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                error_type,
            )
        )


def _thread_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None
    thread_id = (config.get("configurable") or {}).get("thread_id")
    return thread_id if isinstance(thread_id, str) else None


def _message_text(message: BaseMessage) -> str | None:
    return message.content if isinstance(message.content, str) and message.content else None


async def invoke_model_text(
    model: BaseChatModel | None,
    messages: list[BaseMessage],
    *,
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
) -> str | None:
    """调用模型并返回纯文本；任何失败都返回 None，由调用方使用确定性兜底。"""
    if model is None:
        return None

    thread_id = _thread_id(config)
    await run_hooks(
        HookContext(
            point=HookPoint.BEFORE_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
        )
    )

    runtime = runtime_from_config(config)
    invocation_id = str(uuid4())
    started_at = perf_counter()
    response: BaseMessage | None = None
    error_type: str | None = None
    try:
        response = await model.ainvoke(messages, config={"tags": [TAG_NOSTREAM]})
    except Exception as exc:
        # 只记录类型：异常文本可能含上游地址或对话内容
        error_type = type(exc).__name__
        logger.warning("pc.llm_failed", purpose=purpose, error_type=error_type)
    finally:
        latency_ms = int((perf_counter() - started_at) * 1000)
        await _report_usage(runtime, invocation_id, response, latency_ms, error_type)

    if response is None:
        return None

    text = _message_text(response)
    await run_hooks(
        HookContext(
            point=HookPoint.AFTER_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
            text=text,
        )
    )
    return text


def _split_structured_result[SchemaT: BaseModel](
    result: Any, schema: type[SchemaT]
) -> tuple[SchemaT | None, BaseMessage | None, bool]:
    """拆解 `include_raw=True` 的返回值：对象、原始消息、是否解析失败。"""
    if isinstance(result, dict):
        raw = result.get("raw")
        raw_message = raw if isinstance(raw, BaseMessage) else None
        parsed = result.get("parsed")
        if result.get("parsing_error") is None and isinstance(parsed, schema):
            return parsed, raw_message, False
        return None, raw_message, True
    if isinstance(result, schema):
        return result, None, False
    return None, None, True


async def invoke_model_structured[SchemaT: BaseModel](
    model: BaseChatModel | None,
    messages: list[BaseMessage],
    *,
    schema: type[SchemaT],
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
) -> SchemaT | None:
    """结构化调用：返回通过 Schema 校验的对象，任何失败都返回 None。

    复用文本调用的钩子、`TAG_NOSTREAM` 与用量上报；结构化结果同样不能进入
    `stream_mode=messages`，否则前端会把中间 JSON 当成回答。
    """
    if model is None:
        return None

    thread_id = _thread_id(config)
    await run_hooks(
        HookContext(
            point=HookPoint.BEFORE_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
        )
    )

    runtime = runtime_from_config(config)
    invocation_id = str(uuid4())
    started_at = perf_counter()
    raw_message: BaseMessage | None = None
    parsed: SchemaT | None = None
    error_type: str | None = None
    try:
        structured_model = model.with_structured_output(schema, include_raw=True)
        result = await structured_model.ainvoke(messages, config={"tags": [TAG_NOSTREAM]})
        parsed, raw_message, is_invalid = _split_structured_result(result, schema)
        if is_invalid:
            error_type = "structured_output_invalid"
            logger.warning(
                "pc.llm_structured_invalid",
                purpose=purpose,
                error_type=error_type,
            )
    except Exception as exc:
        # 只记录类型：异常文本可能含上游地址或对话内容
        error_type = type(exc).__name__
        logger.warning("pc.llm_failed", purpose=purpose, error_type=error_type)
    finally:
        latency_ms = int((perf_counter() - started_at) * 1000)
        await _report_usage(runtime, invocation_id, raw_message, latency_ms, error_type)

    if parsed is None:
        return None

    await run_hooks(
        HookContext(
            point=HookPoint.AFTER_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
            text=_message_text(raw_message) if raw_message is not None else None,
        )
    )
    return parsed


async def stream_model_text(
    model: BaseChatModel | None,
    messages: list[BaseMessage],
    *,
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
    on_reasoning: Callable[[str], None] | None = None,
) -> str | None:
    """流式调用模型：思考内容即时回调，正文缓冲后整体返回。

    仍打 `TAG_NOSTREAM`：PC 节点正文由确定性渲染器拼装，原始片段不能进入
    `messages` 流，否则用户会看到未通过输出校验的半成品。思考内容只用于
    `reasoning` 面板，不参与最终正文。
    """
    if model is None:
        return None

    thread_id = _thread_id(config)
    await run_hooks(
        HookContext(
            point=HookPoint.BEFORE_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
        )
    )

    runtime = runtime_from_config(config)
    invocation_id = str(uuid4())
    started_at = perf_counter()
    collected: list[str] = []
    reasoning_chars = 0
    # 只保留带 usage_metadata 的分片，Provider 未返回用量时保持 None
    usage_message: BaseMessage | None = None
    error_type: str | None = None
    try:
        # 显式要求流式用量：否则 Provider 只在非流式响应里返回 usage，统计会丢 token
        async for chunk in model.astream(
            messages, config={"tags": [TAG_NOSTREAM]}, stream_usage=True
        ):
            reasoning = (getattr(chunk, "additional_kwargs", None) or {}).get(
                "reasoning_content"
            )
            if isinstance(reasoning, str) and reasoning:
                reasoning_chars += len(reasoning)
                if on_reasoning is not None:
                    on_reasoning(reasoning)
            content = chunk.content
            if isinstance(content, str) and content:
                collected.append(content)
            if getattr(chunk, "usage_metadata", None):
                usage_message = chunk
    except Exception as exc:
        # 只记录类型：异常文本可能含上游地址或对话内容
        error_type = type(exc).__name__
        logger.warning("pc.llm_failed", purpose=purpose, error_type=error_type)
    finally:
        latency_ms = int((perf_counter() - started_at) * 1000)
        # 只记录长度：用于区分「模型没给思考」与「思考事件没下发」，不落正文
        logger.info(
            "pc.llm_stream",
            purpose=purpose,
            reasoning_chars=reasoning_chars,
            content_chars=len("".join(collected)),
        )
        await _report_usage(runtime, invocation_id, usage_message, latency_ms, error_type)

    if error_type is not None:
        return None

    text = "".join(collected) or None
    await run_hooks(
        HookContext(
            point=HookPoint.AFTER_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
            text=text,
        )
    )
    return text


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    """从模型输出中提取第一个 JSON 对象；允许 ```json 围栏与前后解释文本。"""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None
