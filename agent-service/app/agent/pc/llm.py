"""节点内的模型调用：统一打 `TAG_NOSTREAM`、记录用量并执行安全钩子。

`TAG_NOSTREAM` 必须加在每次节点内调用上：结构化 JSON 和解释文案都不能进入
`stream_mode=messages` 的正文流，否则前端会把中间产物当成回答。
模型失败时不抛出，由节点回退到确定性数据。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import TAG_NOSTREAM
from pydantic import BaseModel

from app.agent.hooks import HookContext, HookPoint, run_hooks
from app.agent.pc.status import (
    FAILURE_STAGE_MODEL_MISSING,
    FAILURE_STAGE_OUTPUT_TRUNCATED,
    FAILURE_STAGE_PROVIDER_UNSUPPORTED,
    FAILURE_STAGE_SCHEMA_INVALID,
)
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


def _message_text(message: BaseMessage | None) -> str | None:
    if message is None:
        return None
    return message.content if isinstance(message.content, str) and message.content else None


# 各 Provider 表示「输出预算耗尽」的 finish_reason 取值（OpenAI 兼容为 length）
_TRUNCATION_FINISH_REASONS = frozenset({"length", "max_tokens", "max_output_tokens"})


def _with_max_tokens(model: BaseChatModel, max_tokens: int | None) -> BaseChatModel:
    """按次调用覆盖输出预算：复制实例而不是改原件，其他节点仍用全局预算。

    `with_structured_output` 内部是 RunnableMap，调用期 kwargs 不会透传给模型，
    所以只能在实例上覆盖 `max_tokens`；测试替身等非 pydantic 模型没有
    `model_copy`，此时保持原实例。
    """
    if max_tokens is None:
        return model
    model_copy = getattr(model, "model_copy", None)
    if not callable(model_copy):
        return model
    return model_copy(update={"max_tokens": max_tokens})


def _finish_reason(message: BaseMessage | None) -> str | None:
    """读取 finish_reason；不同网关会写在 response_metadata 或 additional_kwargs。"""
    if message is None:
        return None
    for container in (
        getattr(message, "response_metadata", None),
        getattr(message, "additional_kwargs", None),
    ):
        if not isinstance(container, dict):
            continue
        for key in ("finish_reason", "stop_reason"):
            value = container.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _is_truncated_finish_reason(finish_reason: str | None) -> bool:
    return finish_reason in _TRUNCATION_FINISH_REASONS if finish_reason else False


def _looks_like_truncated_json(text: str | None) -> bool:
    """没有 finish_reason 时的等价信号：JSON 对象没闭合通常就是输出被截断。"""
    if not text:
        return False
    return text.count("{") > text.count("}")


def _output_fingerprint(text: str | None) -> tuple[int, str | None]:
    """只保留长度与哈希前缀：便于比对同一次输出，又不把正文写进日志。"""
    if not text:
        return 0, None
    return len(text), hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


async def invoke_model_text(
    model: BaseChatModel | None,
    messages: list[BaseMessage],
    *,
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
    max_tokens: int | None = None,
) -> str | None:
    """调用模型并返回纯文本；任何失败都返回 None，由调用方使用确定性兜底。"""
    if model is None:
        return None
    response = await _invoke_text_message(
        model,
        messages,
        config=config,
        agent_id=agent_id,
        purpose=purpose,
        max_tokens=max_tokens,
    )
    return _message_text(response) if response is not None else None


async def _invoke_text_message(
    model: BaseChatModel,
    messages: list[BaseMessage],
    *,
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
    max_tokens: int | None = None,
) -> BaseMessage | None:
    """文本通道的原始调用：返回完整消息，供需要 finish_reason 的诊断逻辑使用。"""
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
        response = await _with_max_tokens(model, max_tokens).ainvoke(
            messages, config={"tags": [TAG_NOSTREAM]}
        )
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
    return response


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
    max_tokens: int | None = None,
) -> SchemaT | None:
    """兼容入口：只返回对象；需要失败阶段时用 `invoke_model_structured_outcome`。"""
    outcome = await invoke_model_structured_outcome(
        model,
        messages,
        schema=schema,
        config=config,
        agent_id=agent_id,
        purpose=purpose,
        max_tokens=max_tokens,
    )
    return outcome.value


@dataclass(frozen=True, slots=True)
class StructuredOutcome[SchemaT: BaseModel]:
    """结构化调用结果；`failure_stage` 供节点写入 `build_failure` 定位失败环节。"""

    value: SchemaT | None
    failure_stage: str | None


def _json_schema_instruction(schema: type[BaseModel]) -> str:
    """文本兜底唯一的约束来源：Provider 不支持结构化输出时只能靠提示词。"""
    schema_json = json.dumps(
        schema.model_json_schema(), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "上一次调用未返回可解析的结构化结果。请只输出一个 JSON 对象，"
        "不要输出解释、注释或 Markdown 围栏；JSON 必须严格符合以下 JSON Schema：\n"
        f"{schema_json}"
    )


async def _structured_text_fallback[SchemaT: BaseModel](
    model: BaseChatModel,
    messages: list[BaseMessage],
    *,
    schema: type[SchemaT],
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
    max_tokens: int | None = None,
) -> tuple[SchemaT | None, bool]:
    """一次性文本兜底：注入 Schema → 纯文本调用 → 提取 JSON → Pydantic 校验。

    只有结构化输出失败才会走到这里；不循环、不重试第二次。文本调用已复用
    文本通道的钩子、`TAG_NOSTREAM` 与用量上报，这里不再重复触发钩子。

    返回 `(对象, 是否截断)`：截断要单独上报，否则会被误判成「Provider 不支持」。
    """
    response = await _invoke_text_message(
        model,
        [*messages, HumanMessage(content=_json_schema_instruction(schema))],
        config=config,
        agent_id=agent_id,
        purpose=f"{purpose}:json_fallback",
        max_tokens=max_tokens,
    )
    if response is None:
        logger.warning("pc.llm_fallback_invalid", purpose=purpose, reason="no_response")
        return None, False

    text = _message_text(response)
    finish_reason = _finish_reason(response)
    output_chars, output_hash = _output_fingerprint(text)
    payload = extract_json_object(text)
    is_truncated = _is_truncated_finish_reason(finish_reason) or (
        payload is None and finish_reason is None and _looks_like_truncated_json(text)
    )
    if payload is None:
        # 只记录结论、finish_reason、长度与哈希前缀：正文与密钥一律不落日志
        logger.warning(
            "pc.llm_fallback_invalid",
            purpose=purpose,
            reason="json_not_found",
            finish_reason=finish_reason,
            is_truncated=is_truncated,
            output_chars=output_chars,
            output_sha256_prefix=output_hash,
        )
        return None, is_truncated
    try:
        return schema.model_validate(payload), False
    except ValueError:
        # 只记录结论：校验错误文本可能包含完整模型输出片段
        logger.warning(
            "pc.llm_fallback_invalid",
            purpose=purpose,
            reason="schema_validation_failed",
            finish_reason=finish_reason,
            is_truncated=is_truncated,
            output_chars=output_chars,
            output_sha256_prefix=output_hash,
        )
        return None, is_truncated


async def invoke_model_structured_outcome[SchemaT: BaseModel](
    model: BaseChatModel | None,
    messages: list[BaseMessage],
    *,
    schema: type[SchemaT],
    config: RunnableConfig | None,
    agent_id: str,
    purpose: str,
    max_tokens: int | None = None,
) -> StructuredOutcome[SchemaT]:
    """结构化调用：失败时做一次文本兜底，并返回可诊断的失败阶段。

    部分 Provider（如经 LiteLLM 代理的 deepseek）不支持结构化输出/tool-calling，
    `with_structured_output` 会直接返回 None 或抛错；此时把 JSON Schema 注入提示词
    改走普通文本调用，再用 `extract_json_object` 严格解析并交给 Pydantic 校验。
    兜底只允许一次，仍失败才返回空结果。

    `max_tokens` 只作用于本次调用（复制实例），其他节点仍用全局预算。
    输出被截断时返回 `output_truncated`，不能误报成「Provider 不支持」。

    结构化结果与兜底 JSON 都不能进入 `stream_mode=messages`，否则前端会把中间
    JSON 当成回答。
    """
    if model is None:
        return StructuredOutcome(None, FAILURE_STAGE_MODEL_MISSING)

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
    failure_stage = FAILURE_STAGE_PROVIDER_UNSUPPORTED
    error_type: str | None = None
    finish_reason: str | None = None
    output_chars = 0
    output_hash: str | None = None
    is_truncated = False
    try:
        structured_model = _with_max_tokens(model, max_tokens).with_structured_output(
            schema, include_raw=True
        )
        result = await structured_model.ainvoke(messages, config={"tags": [TAG_NOSTREAM]})
        if result is None:
            # Provider 不支持结构化输出时可能返回 None 而不是抛错
            error_type = "structured_output_empty"
        else:
            parsed, raw_message, is_invalid = _split_structured_result(result, schema)
            finish_reason = _finish_reason(raw_message)
            is_truncated = _is_truncated_finish_reason(finish_reason)
            output_chars, output_hash = _output_fingerprint(_message_text(raw_message))
            if is_invalid:
                failure_stage = FAILURE_STAGE_SCHEMA_INVALID
                error_type = "structured_output_invalid"
    except Exception as exc:
        # 只记录类型：异常文本可能含上游地址或对话内容
        error_type = type(exc).__name__
    finally:
        latency_ms = int((perf_counter() - started_at) * 1000)
        await _report_usage(runtime, invocation_id, raw_message, latency_ms, error_type)

    if is_truncated:
        failure_stage = FAILURE_STAGE_OUTPUT_TRUNCATED

    if parsed is None:
        # 脱敏：只记录阶段、finish_reason、长度与哈希前缀，不落模型输出正文
        logger.warning(
            "pc.llm_structured_failed",
            purpose=purpose,
            failure_stage=failure_stage,
            error_type=error_type,
            has_raw=raw_message is not None,
            finish_reason=finish_reason,
            is_truncated=is_truncated,
            output_chars=output_chars,
            output_sha256_prefix=output_hash,
        )
        parsed, fallback_truncated = await _structured_text_fallback(
            model,
            messages,
            schema=schema,
            config=config,
            agent_id=agent_id,
            purpose=purpose,
            max_tokens=max_tokens,
        )
        if parsed is not None:
            return StructuredOutcome(parsed, None)
        if fallback_truncated:
            return StructuredOutcome(None, FAILURE_STAGE_OUTPUT_TRUNCATED)
        return StructuredOutcome(None, failure_stage)

    await run_hooks(
        HookContext(
            point=HookPoint.AFTER_MODEL,
            thread_id=thread_id,
            agent_id=agent_id,
            text=_message_text(raw_message),
        )
    )
    return StructuredOutcome(parsed, None)


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
