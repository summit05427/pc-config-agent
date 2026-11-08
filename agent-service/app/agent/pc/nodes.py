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

from app.agent.pc.llm import extract_json_object, invoke_model_text
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
_SCENARIO_KEYWORDS: tuple[tuple[BuildScenario, tuple[str, ...]], ...] = (
    (BuildScenario.GAMING, ("游戏", "打游戏", "电竞", "3A", "网游")),
    (BuildScenario.CREATIVE, ("剪辑", "渲染", "创作", "设计", "建模", "视频")),
    (BuildScenario.OFFICE, ("办公", "文档", "上网", "网课", "轻办公")),
)
_VERIFIED_KEYWORDS = ("人工核验", "已核验", "只要自营", "仅要自营")
# 推荐说明只允许描述取舍，不允许出现数字、型号、价格和购买渠道
_REASON_FORBIDDEN = ("http", "www", "京东", "淘宝", "天猫", "¥", "元", "￥")
_REASON_MAX_CHARS = 300


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
        if any(keyword in text for keyword in keywords):
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

    return PCRequirements(
        budget_max_fen=budget_fen,
        scenario=scenario,
        scenario_explicit=scenario_explicit,
        require_verified_offers=require_verified,
        needs_clarification=needs_clarification,
        clarification_question=question,
        missing_fields=missing,
    )


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

    if requirements.needs_clarification or (
        requirements.budget_max_fen is None and not requirements.scenario_explicit
    ):
        message = requirements.clarification_question or (
            "请告诉我预算范围和主要用途（游戏、创作或办公），我再给出具体配置。"
        )
        return {
            "validation_result": {
                "status": "clarification",
                "message": message,
                "missing_fields": requirements.missing_fields,
            },
            "requirements": requirements.model_dump(),
            "workflow_status": STATUS_CLARIFICATION,
        }

    if requirements.budget_max_fen is not None and requirements.budget_max_fen <= 0:
        return {
            "validation_result": {
                "status": "clarification",
                "message": "预算必须大于 0，请给出一个明确的预算范围。",
                "missing_fields": ["budget_max_fen"],
            },
            "requirements": requirements.model_dump(),
            "workflow_status": STATUS_CLARIFICATION,
        }

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
        return {
            "workflow_status": STATUS_SUCCESS,
            "tool_events": events,
            "compatibility_report": unknown,
        }

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

    return {
        "workflow_status": STATUS_SUCCESS,
        "tool_events": events,
        "compatibility_report": report,
    }


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


def _safe_reason(text: str | None, build: dict[str, Any]) -> str | None:
    """模型文案只允许谈取舍；出现数字、型号、价格或渠道一律丢弃。"""
    if not text:
        return None
    reason = " ".join(text.split()).strip()
    if not reason or len(reason) > _REASON_MAX_CHARS:
        return None
    if any(char.isdigit() for char in reason):
        return None
    if any(keyword in reason for keyword in _REASON_FORBIDDEN):
        return None
    lowered = reason.lower()
    for component in as_list(build.get("components")):
        item = as_mapping(component)
        for field in ("modelName", "brand"):
            value = as_text(item.get(field))
            if value and value.lower() in lowered:
                return None
    return reason


def _deterministic_reason(state: PCConfigState) -> str:
    build = as_mapping(state.get("build_result"))
    requirements = as_mapping(build.get("requirements"))
    scenario = as_text(requirements.get("scenario"), "BALANCED")
    overall = overall_compatibility(as_mapping(state.get("compatibility_report")))
    reasons = {
        "GAMING": "在预算内优先保证图形性能与散热余量，适合主流游戏场景。",
        "CREATIVE": "在预算内平衡多核性能、内存容量与存储速度，适合剪辑和渲染。",
        "OFFICE": "以稳定、静音和日常响应为重点，性能足以覆盖办公与网课。",
        "BALANCED": "在预算内追求性能与价格的平衡，覆盖日常使用与轻度娱乐。",
    }
    reason = reasons.get(scenario, reasons["BALANCED"])
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
    markdown = render_build_markdown(build, reason)
    return {
        "messages": [AIMessage(content=markdown)],
        "build_result": build,
        "reason_summary": reason,
        "workflow_status": STATUS_SUCCESS,
    }


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
    return _safe_reason(text, as_mapping(state.get("build_result")))


def build_result_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    """供 `turn.py` 生成 `done.build_result`；失败路径不返回卡片。"""
    if as_text(state.get("workflow_status")) != STATUS_SUCCESS:
        return None
    build = as_mapping(state.get("build_result"))
    if not build:
        return None
    return build_frontend_payload(build, as_text(state.get("reason_summary")))
