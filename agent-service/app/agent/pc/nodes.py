"""PC 配置推荐的六个确定性节点。

设计约束：
- 节点不直接发 SSE，只累积 `tool_events`；
- 只有需求解析与推荐说明调用 LLM，且必须打 `TAG_NOSTREAM`；
- 型号、价格、总价、SKU、链接全部来自 Java 结构化结果；
- 任何失败路径都写入明确 `workflow_status`，禁止静默返回空。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.agent.pc.hitl import build_compatibility_question
from app.agent.pc.llm import extract_json_object, invoke_model_text
from app.agent.pc.openui_renderer import render_build_openui
from app.agent.pc.output_guard import (
    check_build_output,
    record_violations,
    render_guard_notice,
    sanitize_reason,
)
from app.agent.pc.renderer import (
    CATEGORY_LABELS,
    as_int,
    as_list,
    as_mapping,
    as_text,
    build_frontend_payload,
    format_fen,
    overall_compatibility,
    render_build_markdown,
    render_failure_markdown,
)
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildScenario,
    PCRequirements,
    Preference,
    RenderMode,
    RequirementExtraction,
)
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import (
    STATUS_CLARIFICATION,
    STATUS_COMPATIBILITY_FAILED,
    STATUS_INVALID,
    STATUS_NO_CANDIDATES,
    STATUS_NO_SOLUTION,
    STATUS_RETRIEVED,
    STATUS_RETRY,
    STATUS_SOLVED,
    STATUS_SUCCESS,
    STATUS_UPSTREAM_ERROR,
    STATUS_VALIDATED,
)
from app.agent.registry import ToolExecutionError, get_governed_tool
from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# 兜底解析：模型不可用时仍要能从「8000 元、打游戏」得到可用需求
_YUAN_PATTERN = re.compile(r"(\d+)\s*(?:元|块|人民币)")
_WAN_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?\s*(?:万|w|W)")
# 新用途值优先命中；旧值只在前述规则都未命中时兜底
_SCENARIO_KEYWORDS: tuple[tuple[BuildScenario, tuple[str, ...]], ...] = (
    (BuildScenario.RENDERING, ("渲染",)),
    (BuildScenario.AI_INFERENCE, ("本地推理", "ai 推理", "ai推理", "大模型", "深度学习")),
    (BuildScenario.VIDEO_EDITING, ("剪辑", "调色", "视频编辑", "视频后期")),
    (
        BuildScenario.PROGRAMMING,
        ("编程", "写代码", "开发", "编译", "容器", "docker", "虚拟机"),
    ),
    (BuildScenario.GAMING, ("游戏", "打游戏", "电竞", "3A", "网游")),
    (BuildScenario.GENERAL, ("综合", "日常使用")),
    (BuildScenario.CREATIVE, ("创作", "设计", "建模")),
    (BuildScenario.OFFICE, ("办公", "文档", "上网", "网课", "轻办公")),
)
# 只在渲染场景下生效：出现哪些词就说明用户指定了哪个执行单元
_RENDER_MODE_CPU_KEYWORDS = ("cpu", "处理器")
_RENDER_MODE_GPU_KEYWORDS = ("gpu", "显卡")
RENDER_MODE_CLARIFICATION = "渲染主要用 CPU 还是 GPU？两者配置方向差异较大。"
_VERIFIED_KEYWORDS = ("人工核验", "已核验", "只要自营", "仅要自营")
# 选型偏好只认用户原话中的明确措辞；按性能优先在前，避免「性能优先但预算有限」被判成性价比
_PREFERENCE_KEYWORDS: tuple[tuple[Preference, tuple[str, ...]], ...] = (
    (
        Preference.PERFORMANCE,
        ("性能优先", "性能第一", "要最好的", "预算不是问题", "不差钱", "顶配"),
    ),
    (Preference.VALUE, ("性价比", "便宜点", "够用就行", "别太贵", "省钱")),
)


def _last_human_text(state: PCConfigState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else ""
    return ""


def _fen_from_yuan_text(whole: str, fraction: str | None = None, *, wan: bool = False) -> int:
    """整数运算把「1.5 万」「8000 元」换算成分，不经过浮点。"""
    if wan:
        yuan = int(whole) * 10_000
        if fraction:
            yuan += int((fraction + "0000")[:4])
        return yuan * 100
    if fraction is None:
        return int(whole) * 100
    digits = (fraction + "00")[:2]
    return int(whole) * 100 + int(digits)


def _detect_render_mode(text: str) -> RenderMode | None:
    """从明确提及的执行单元推断渲染方式；没提就返回 None，不按场景猜。"""
    lowered = text.lower()
    uses_cpu = any(keyword in lowered for keyword in _RENDER_MODE_CPU_KEYWORDS)
    uses_gpu = any(keyword in lowered for keyword in _RENDER_MODE_GPU_KEYWORDS)
    if uses_cpu and uses_gpu:
        return RenderMode.BOTH
    if uses_cpu:
        return RenderMode.CPU
    if uses_gpu:
        return RenderMode.GPU
    return None


def _apply_render_mode(requirements: PCRequirements, text: str) -> PCRequirements:
    """只有渲染场景保留 `render_mode`；其他场景清空，避免把机型偏好误当渲染方式。"""
    render_mode = (
        _detect_render_mode(text)
        if requirements.scenario is BuildScenario.RENDERING
        else None
    )
    if requirements.render_mode is render_mode:
        return requirements
    return requirements.model_copy(update={"render_mode": render_mode})


def _detect_preference(text: str) -> Preference | None:
    """从用户原话识别选型偏好；没有明确措辞就返回 None，不按场景或预算猜。"""
    lowered = text.lower()
    for preference, keywords in _PREFERENCE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return preference
    return None


def _apply_preference(requirements: PCRequirements, text: str) -> PCRequirements:
    """以用户原话为唯一依据；模型可能臆测偏好，这里统一覆盖为确定性识别结果。"""
    preference = _detect_preference(text)
    if requirements.preference is preference:
        return requirements
    return requirements.model_copy(update={"preference": preference})


def fallback_requirements(text: str) -> PCRequirements:
    """确定性兜底解析；覆盖预算、用途与「只接受核验价」三类关键信号。"""
    budget_fen: int | None = None
    wan_match = _WAN_PATTERN.search(text)
    yuan_match = _YUAN_PATTERN.search(text)
    if wan_match:
        budget_fen = _fen_from_yuan_text(
            wan_match.group(1), wan_match.group(2), wan=True
        )
    elif yuan_match:
        budget_fen = _fen_from_yuan_text(yuan_match.group(1))

    scenario = BuildScenario.BALANCED
    scenario_explicit = False
    for candidate, keywords in _SCENARIO_KEYWORDS:
        if any(keyword in text.lower() for keyword in keywords):
            scenario = candidate
            scenario_explicit = True
            break

    require_verified = any(keyword in text for keyword in _VERIFIED_KEYWORDS)
    missing: list[str] = []
    if budget_fen is None:
        missing.append("budget_max_fen")
    if not scenario_explicit:
        missing.append("scenario")

    needs_clarification = budget_fen is None and not scenario_explicit
    question = None
    if needs_clarification:
        question = (
            "请告诉我预算范围（例如 8000 元）和主要用途"
            "（游戏、创作或办公），我再给出具体配置。"
        )

    requirements = PCRequirements(
        budget_max_fen=budget_fen,
        scenario=scenario,
        scenario_explicit=scenario_explicit,
        require_verified_offers=require_verified,
        needs_clarification=needs_clarification,
        clarification_question=question,
        missing_fields=missing,
    )
    return _apply_preference(_apply_render_mode(requirements, text), text)


async def requirement_parser(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    parser_prompt: str,
) -> dict[str, Any]:
    """把用户自然语言解析成结构化需求；模型失败时退化为确定性规则。"""
    user_text = _last_human_text(state).strip()
    preference = state.get("preference_prompt")
    prompt_text = user_text
    if preference:
        prompt_text = f"{user_text}\n\n用户偏好：{preference}"

    text = await invoke_model_text(
        model,
        [SystemMessage(content=parser_prompt), HumanMessage(content=prompt_text)],
        config=config,
        agent_id=agent_id,
        purpose="requirement_parser",
    )
    requirements = _parse_requirements(text) or fallback_requirements(user_text)
    # 模型可能臆测渲染方式与偏好，最终以用户原文中的明确措辞为准
    requirements = _apply_render_mode(requirements, user_text)
    requirements = _apply_preference(requirements, user_text)
    return {"requirements": requirements.model_dump(), "workflow_status": "parsed"}


def _parse_requirements(text: str | None) -> PCRequirements | None:
    payload = extract_json_object(text)
    if payload is None:
        return None
    try:
        return RequirementExtraction.model_validate(payload)
    except ValueError:
        logger.warning("pc.requirements_invalid", reason="schema_validation_failed")
        return None


def _with_hitl_question(update: dict[str, Any], question: str) -> dict[str, Any]:
    """HITL 开启时把提问写成 AI 消息，保证中断后历史里能看到问题本身。

    门控节点中断时不会提交自己的状态更新，问题必须由门控之前的确定性节点写入。
    """
    if not get_settings().hitl.enabled:
        return update
    messages = list(update.get("messages") or [])
    messages.append(AIMessage(content=question))
    return {**update, "messages": messages}


async def requirement_validator(state: PCConfigState) -> dict[str, Any]:
    """纯代码校验；不满足关键信息时明确追问，不进入检索。"""
    try:
        requirements = PCRequirements.model_validate(state.get("requirements") or {})
    except ValueError:
        return {
            "validation_result": {
                "status": "invalid",
                "message": "需求参数不合法，请补充预算、用途或容量要求后重试。",
                "missing_fields": [],
            },
            "workflow_status": STATUS_INVALID,
        }

    # 渲染场景必须先确认执行单元；预算也缺时只追问这一次，不拆成多轮
    if (
        requirements.scenario is BuildScenario.RENDERING
        and requirements.render_mode is None
        and requirements.budget_max_fen is None
    ):
        missing_fields = list(requirements.missing_fields)
        if "render_mode" not in missing_fields:
            missing_fields.append("render_mode")
        clarification = requirements.model_copy(
            update={
                "needs_clarification": True,
                "clarification_question": RENDER_MODE_CLARIFICATION,
                "missing_fields": missing_fields,
            }
        )
        return _with_hitl_question(
            {
                "validation_result": {
                    "status": "clarification",
                    "message": RENDER_MODE_CLARIFICATION,
                    "missing_fields": missing_fields,
                },
                "requirements": clarification.model_dump(),
                "workflow_status": STATUS_CLARIFICATION,
            },
            RENDER_MODE_CLARIFICATION,
        )

    if requirements.needs_clarification or (
        requirements.budget_max_fen is None and not requirements.scenario_explicit
    ):
        message = requirements.clarification_question or (
            "请告诉我预算范围和主要用途（游戏、创作或办公），我再给出具体配置。"
        )
        return _with_hitl_question(
            {
                "validation_result": {
                    "status": "clarification",
                    "message": message,
                    "missing_fields": requirements.missing_fields,
                },
                "requirements": requirements.model_dump(),
                "workflow_status": STATUS_CLARIFICATION,
            },
            message,
        )

    if requirements.budget_max_fen is not None and requirements.budget_max_fen <= 0:
        budget_message = "预算必须大于 0，请给出一个明确的预算范围。"
        return _with_hitl_question(
            {
                "validation_result": {
                    "status": "clarification",
                    "message": budget_message,
                    "missing_fields": ["budget_max_fen"],
                },
                "requirements": requirements.model_dump(),
                "workflow_status": STATUS_CLARIFICATION,
            },
            budget_message,
        )

    return {
        "validation_result": {"status": "ok", "message": None, "missing_fields": []},
        "requirements": requirements.model_dump(),
        "workflow_status": STATUS_VALIDATED,
    }


def _tool_start(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"phase": "start", "name": name, "args": args}


def _tool_end(name: str, preview: str) -> dict[str, Any]:
    return {"phase": "end", "name": name, "preview": preview}


async def _call_tool(
    tool: BaseTool, args: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """调用治理后的工具并解析 JSON；返回 (data, 安全错误文案)。"""
    try:
        raw = await tool.ainvoke(args)
    except ToolExecutionError as exc:
        return None, str(exc)
    except Exception:
        logger.warning("pc.tool_failed", tool=tool.name, error_type="unexpected")
        return None, "配置数据暂时不可用，请稍后重试"
    if not isinstance(raw, str):
        return None, "配置数据格式异常，请稍后重试"
    try:
        payload = json.loads(raw)
    except ValueError:
        # 治理层可能因调用上限/截断返回纯文本，不能当作结构化结果继续用
        return None, "配置数据查询受限，请稍后重试"
    return payload if isinstance(payload, dict) else None, None


async def candidate_retriever(state: PCConfigState) -> dict[str, Any]:
    """按八个类别检索候选、跑分与报价统计；缺任一类别即无候选。"""
    events: list[dict[str, Any]] = []
    search_tool = get_governed_tool("search_hardware_candidates")
    if search_tool is None:
        return {
            "workflow_status": STATUS_UPSTREAM_ERROR,
            "tool_events": [_tool_end("search_hardware_candidates", "工具未注册")],
        }

    requests = [
        (category, search_tool.ainvoke({"category": category.value}))
        for category in REQUIRED_CATEGORIES
    ]
    for category, _ in requests:
        events.append(_tool_start("search_hardware_candidates", {"category": category.value}))

    results = await asyncio.gather(
        *[coroutine for _, coroutine in requests], return_exceptions=True
    )
    counts: dict[str, int] = {}
    catalog_version = ""
    missing: list[str] = []
    upstream_failed = False
    for (category, _), result in zip(requests, results, strict=True):
        if isinstance(result, BaseException):
            upstream_failed = True
            events.append(_tool_end("search_hardware_candidates", "查询失败"))
            continue
        data, error = _decode_tool_result(result)
        if error is not None or data is None:
            upstream_failed = True
            events.append(_tool_end("search_hardware_candidates", error or "查询失败"))
            continue
        total = as_int(data.get("total"), len(as_list(data.get("list"))))
        counts[category.value] = total
        catalog_version = as_text(data.get("catalogVersion"), catalog_version)
        events.append(
            _tool_end(
                "search_hardware_candidates",
                f"{CATEGORY_LABELS[category.value]}候选 {total} 条",
            )
        )
        if total <= 0:
            missing.append(category.value)

    if upstream_failed:
        return {
            "workflow_status": STATUS_UPSTREAM_ERROR,
            "tool_events": events,
            "candidate_pool": {
                "catalog_version": catalog_version,
                "category_counts": counts,
                "missing_categories": missing,
            },
        }
    if missing:
        return {
            "workflow_status": STATUS_NO_CANDIDATES,
            "tool_events": events,
            "candidate_pool": {
                "catalog_version": catalog_version,
                "category_counts": counts,
                "missing_categories": missing,
            },
        }

    benchmarks, offer_summary = await _enrich_candidates(events)
    return {
        "workflow_status": STATUS_RETRIEVED,
        "tool_events": events,
        "candidate_pool": {
            "catalog_version": catalog_version,
            "category_counts": counts,
            "missing_categories": [],
            "benchmarks": benchmarks,
            "offer_summary": offer_summary,
        },
    }


def _decode_tool_result(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw, str):
        return None, "配置数据格式异常"
    try:
        payload = json.loads(raw)
    except ValueError:
        return None, "配置数据查询受限"
    return (payload, None) if isinstance(payload, dict) else (None, "配置数据格式异常")


async def _enrich_candidates(
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """补充跑分与报价统计；失败不影响主流程，但会如实标记为空。"""
    benchmark_tool = get_governed_tool("get_benchmark_data")
    offer_tool = get_governed_tool("get_verified_offers")
    benchmarks: dict[str, Any] = {}
    offer_summary: dict[str, Any] = {}

    if benchmark_tool is not None:
        events.append(_tool_start("get_benchmark_data", {"category": "CPU"}))
        events.append(_tool_start("get_benchmark_data", {"category": "GPU"}))
        pair: list[Any] = list(
            await asyncio.gather(
                benchmark_tool.ainvoke({"category": "CPU"}),
                benchmark_tool.ainvoke({"category": "GPU"}),
                return_exceptions=True,
            )
        )
        for category, raw in zip(("CPU", "GPU"), pair, strict=True):
            data, error = _decode_tool_result(raw)
            if error is None and data is not None:
                benchmarks[category] = _top_benchmark(data)
                events.append(_tool_end("get_benchmark_data", f"{category} 跑分已读取"))
            else:
                events.append(_tool_end("get_benchmark_data", error or "跑分不可用"))

    if offer_tool is not None:
        events.append(_tool_start("get_verified_offers", {"verified_only": False}))
        raw = await _safe_ainvoke(offer_tool, {"verified_only": False})
        data, error = _decode_tool_result(raw)
        if error is None and data is not None:
            offer_summary = {
                "data_status": as_text(data.get("dataStatus")),
                "verified": as_int(data.get("verifiedOfferCount")),
                "mock": as_int(data.get("mockOfferCount")),
            }
            events.append(
                _tool_end(
                    "get_verified_offers",
                    f"报价核验 {offer_summary['verified']} 条 / 演示 {offer_summary['mock']} 条",
                )
            )
        else:
            events.append(_tool_end("get_verified_offers", error or "报价不可用"))
    return benchmarks, offer_summary


async def _safe_ainvoke(tool: BaseTool, args: dict[str, Any]) -> Any:
    try:
        return await tool.ainvoke(args)
    except Exception:
        return None


def _top_benchmark(data: dict[str, Any]) -> dict[str, Any]:
    items = as_list(data.get("list"))
    if not items:
        return {}
    first = as_mapping(items[0])
    return {
        "hardware_id": as_text(first.get("hardwareId")),
        "type": as_text(first.get("benchmarkType")),
        "score": first.get("score"),
    }


async def build_solver(state: PCConfigState) -> dict[str, Any]:
    """调用 Java 求解；无解时保留结构化原因，绝不放宽预算。"""
    requirements = PCRequirements.model_validate(state.get("requirements") or {})
    retry_count = as_int(state.get("retry_count"))
    # 失败重解只放宽软偏好（是否只接受核验价），预算与兼容性约束保持不变
    require_verified = False if retry_count > 0 else requirements.require_verified_offers
    args = {
        "budget_max_fen": requirements.budget_max_fen,
        "scenario": requirements.scenario.value,
        "preference": requirements.preference.value if requirements.preference else None,
        "render_mode": requirements.render_mode.value if requirements.render_mode else None,
        "min_memory_gb": requirements.min_memory_gb,
        "min_storage_gb": requirements.min_storage_gb,
        "require_verified_offers": require_verified,
    }
    events = [_tool_start("solve_pc_build", args)]
    tool = get_governed_tool("solve_pc_build")
    if tool is None:
        return {
            "workflow_status": STATUS_UPSTREAM_ERROR,
            "tool_events": [_tool_end("solve_pc_build", "工具未注册")],
        }

    data, error = await _call_tool(tool, args)
    if error is not None or data is None:
        events.append(_tool_end("solve_pc_build", error or "求解失败"))
        return {"workflow_status": STATUS_UPSTREAM_ERROR, "tool_events": events}

    if not data.get("solved"):
        failure = as_mapping(data.get("failure"))
        events.append(_tool_end("solve_pc_build", "无可行配置"))
        return {
            "workflow_status": STATUS_NO_SOLUTION,
            "tool_events": events,
            "build_failure": failure,
            "budget_report": {
                "budget_max_fen": requirements.budget_max_fen,
                "minimum_required_budget_fen": failure.get("minimumRequiredBudgetFen"),
                "status": "NO_SOLUTION",
            },
        }

    build = as_mapping(data.get("build"))
    total_text = format_fen(as_int(build.get("totalPriceFen")))
    events.append(_tool_end("solve_pc_build", f"总价 {total_text}"))
    return {
        "workflow_status": STATUS_SOLVED,
        "tool_events": events,
        "build_result": build,
        "compatibility_report": as_mapping(build.get("compatibilityReport")),
        "budget_report": {
            "budget_max_fen": build.get("budgetMaxFen"),
            "total_price_fen": as_int(build.get("totalPriceFen")),
            "status": as_text(build.get("budgetStatus")),
        },
    }


async def build_validator(state: PCConfigState) -> dict[str, Any]:
    """校验八类组合；失败最多自动重解一次，次数来自配置。"""
    if as_text(state.get("workflow_status")) != STATUS_SOLVED:
        return {}

    build = as_mapping(state.get("build_result"))
    hardware_ids = _hardware_ids(build)
    if hardware_ids is None:
        return {
            "workflow_status": STATUS_UPSTREAM_ERROR,
            "tool_events": [_tool_end("validate_pc_build", "方案缺少硬件标识")],
        }

    events = [_tool_start("validate_pc_build", {"categories": sorted(hardware_ids)})]
    tool = get_governed_tool("validate_pc_build")
    if tool is None:
        return {"workflow_status": STATUS_UPSTREAM_ERROR, "tool_events": events}

    data, error = await _call_tool(tool, hardware_ids)
    if error is not None or data is None:
        # 校验不可用不能丢掉已求得的方案：如实标记为未验证
        unknown = {
            "overallStatus": "UNKNOWN",
            "checks": [
                {
                    "ruleId": "validation_unavailable",
                    "ruleName": "兼容性校验",
                    "status": "UNKNOWN",
                    "message": "兼容性校验服务暂不可用，本方案尚未完成验证。",
                }
            ],
        }
        events.append(_tool_end("validate_pc_build", error or "校验失败"))
        unknown_state = {**state, "compatibility_report": unknown}
        return _with_hitl_question(
            {
                "workflow_status": STATUS_SUCCESS,
                "tool_events": events,
                "compatibility_report": unknown,
            },
            build_compatibility_question(unknown_state),
        )

    report = as_mapping(data.get("report"))
    overall = overall_compatibility(report)
    events.append(_tool_end("validate_pc_build", f"兼容性 {overall}"))
    if data.get("valid") is False or report.get("hasFailure") is True:
        retry_count = as_int(state.get("retry_count"))
        max_retries = get_settings().agent.max_solve_retries
        if retry_count < max_retries:
            return {
                "workflow_status": STATUS_RETRY,
                "tool_events": events,
                "compatibility_report": report,
                "retry_count": retry_count + 1,
            }
        return {
            "workflow_status": STATUS_COMPATIBILITY_FAILED,
            "tool_events": events,
            "compatibility_report": report,
        }

    success = {
        "workflow_status": STATUS_SUCCESS,
        "tool_events": events,
        "compatibility_report": report,
    }
    if overall == "UNKNOWN":
        # 兼容性未验证：HITL 开启时先写入提问消息，恢复后不会重复生成
        return _with_hitl_question(
            success,
            build_compatibility_question({**state, "compatibility_report": report}),
        )
    return success


def _hardware_ids(build: dict[str, Any]) -> dict[str, str] | None:
    ids: dict[str, str] = {}
    for item in as_list(build.get("components")):
        component = as_mapping(item)
        category = as_text(component.get("category")).lower()
        hardware_id = as_text(component.get("hardwareId"))
        if category and hardware_id:
            ids[category] = hardware_id
    required = {category.value.lower() for category in REQUIRED_CATEGORIES}
    return ids if required <= set(ids) else None


def _reason_context(state: PCConfigState) -> str:
    """只把结构性结论交给模型，不提供型号、价格与链接。"""
    build = as_mapping(state.get("build_result"))
    requirements = as_mapping(build.get("requirements"))
    scenario = as_text(requirements.get("scenario"), "BALANCED")
    budget_status = as_text(build.get("budgetStatus"), "NO_BUDGET")
    overall = overall_compatibility(as_mapping(state.get("compatibility_report")))
    return (
        f"场景={scenario}；预算状态={budget_status}；兼容性={overall}；"
        f"组件类别={','.join(CATEGORY_LABELS[item.value] for item in REQUIRED_CATEGORIES)}"
    )


def _preference_reason(state: PCConfigState) -> str:
    """偏好说明必须与 Java 的实际排序一致：`VALUE` 只有预算存在时才生效。"""
    requirements = as_mapping(state.get("requirements"))
    preference = as_text(requirements.get("preference"))
    budget = as_mapping(as_mapping(state.get("build_result")).get("requirements")).get(
        "budgetMaxFen"
    )
    has_budget = isinstance(budget, int) and not isinstance(budget, bool) and budget > 0
    if preference == Preference.VALUE.value:
        if has_budget:
            return "选型按性价比优先，在预算内更看重单位价格能换到的性能。"
        return "你表达了性价比倾向，但没有给出预算，本次按默认性能排序选型。"
    if preference == Preference.PERFORMANCE.value:
        return "选型按性能总分优先，在预算内优先取得更高性能。"
    return "你没有指定性价比或性能倾向，方案按默认排序给出。"


def _deterministic_reason(state: PCConfigState) -> str:
    build = as_mapping(state.get("build_result"))
    requirements = as_mapping(build.get("requirements"))
    scenario = as_text(requirements.get("scenario"), "BALANCED")
    overall = overall_compatibility(as_mapping(state.get("compatibility_report")))
    reasons = {
        "GAMING": "在预算内优先保证图形性能与散热余量，适合主流游戏场景。",
        "VIDEO_EDITING": "在预算内平衡多核性能、内存容量与存储读写，适合剪辑与视频后期。",
        "PROGRAMMING": "在预算内侧重多核性能与内存容量，适合编译、容器与开发环境。",
        "RENDERING": "在预算内优先保证多核吞吐与稳定供电，适合离线渲染任务。",
        "AI_INFERENCE": "在预算内优先保证显存容量与内存带宽，适合本地模型推理。",
        "CREATIVE": "在预算内平衡多核性能、内存容量与存储速度，适合剪辑和渲染。",
        "OFFICE": "以稳定、静音和日常响应为重点，性能足以覆盖办公与网课。",
        "BALANCED": "在预算内追求性能与价格的平衡，覆盖日常使用与轻度娱乐。",
    }
    reason = reasons.get(scenario, reasons["BALANCED"]) + _preference_reason(state)
    if overall == "UNKNOWN":
        reason += "机箱散热高度等少数规格尚未验证，装机前请再次确认。"
    if as_int(build.get("demoOfferCount")) > 0:
        reason += "当前方案包含演示价格，请以商品页实时信息为准。"
    return reason


async def response_generator(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    system_prompt: str,
    generator_prompt: str,
) -> dict[str, Any]:
    """写最终正文；模型只生成推荐说明，Markdown 由代码确定性渲染。"""
    status = as_text(state.get("workflow_status"))
    if status != STATUS_SUCCESS:
        return {
            "messages": [AIMessage(content=render_failure_markdown(state))],
        }

    build = as_mapping(state.get("build_result"))
    reason = await _generate_reason(
        state,
        config=config,
        model=model,
        agent_id=agent_id,
        system_prompt=system_prompt,
        generator_prompt=generator_prompt,
    )
    reason = reason or _deterministic_reason(state)
    body = _render_success(build, reason)
    violations = check_build_output(
        build=build,
        compatibility_report=as_mapping(state.get("compatibility_report")),
        reason=reason,
        markdown=body,
    )
    if violations:
        # 命中即丢弃模型文案并改用确定性说明；数据类问题追加用户可见提示，不静默掩盖
        record_violations(violations, agent_id=agent_id)
        reason = _deterministic_reason(state)
        body = _render_success(build, reason) + render_guard_notice(violations)
    return {
        "messages": [AIMessage(content=body)],
        "build_result": build,
        "reason_summary": reason,
        "workflow_status": STATUS_SUCCESS,
    }


def _render_success(build: dict[str, Any], reason: str) -> str:
    """开关打开时输出 OpenUI 清单与详情按钮，否则保持 Markdown 表格兜底。"""
    if get_settings().openui.enabled:
        return render_build_openui(build, reason)
    return render_build_markdown(build, reason)


async def _generate_reason(
    state: PCConfigState,
    *,
    config: RunnableConfig,
    model: BaseChatModel | None,
    agent_id: str,
    system_prompt: str,
    generator_prompt: str,
) -> str | None:
    if model is None:
        return None
    text = await invoke_model_text(
        model,
        [
            SystemMessage(content=f"{system_prompt}\n\n{generator_prompt}"),
            HumanMessage(content=_reason_context(state)),
        ],
        config=config,
        agent_id=agent_id,
        purpose="response_generator",
    )
    return sanitize_reason(text, as_mapping(state.get("build_result")))


def build_result_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    """供 `turn.py` 生成 `done.build_result`；失败路径不返回卡片。"""
    if as_text(state.get("workflow_status")) != STATUS_SUCCESS:
        return None
    build = as_mapping(state.get("build_result"))
    if not build:
        return None
    # Java 缺少 workloadProfile 时回退到本地解析出的用途，不用默认值冒充
    local_scenario = as_text(as_mapping(state.get("requirements")).get("scenario"))
    return build_frontend_payload(
        build,
        as_text(state.get("reason_summary")),
        fallback_scenario=local_scenario,
    )
