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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from app.agent.pc.llm import (
    StructuredOutcome,
    extract_json_object,
    invoke_model_structured,
    invoke_model_structured_outcome,
    invoke_model_text,
    stream_model_text,
)
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
    has_demo_price,
    has_observed_price,
    overall_compatibility,
    render_build_markdown,
    render_failure_markdown,
)
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildProposal,
    BuildScenario,
    BuildStrategy,
    ComponentPriority,
    HardwareCategory,
    PCRequirements,
    Preference,
    RenderMode,
    RequirementExtraction,
    StrategyId,
)
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import (
    FAILURE_BUDGET_EXCEEDED,
    FAILURE_CANDIDATE_NOT_IN_POOL,
    FAILURE_COMPATIBILITY_CONFLICT,
    FAILURE_MODEL_UNAVAILABLE,
    FAILURE_OFFER_UNAVAILABLE,
    FAILURE_OUTPUT_TRUNCATED,
    FAILURE_STAGE_COMPOSE_ERROR_PREFIX,
    FAILURE_STAGE_ID_NOT_IN_CANDIDATES,
    FAILURE_STAGE_PARTIAL_CHECK,
    FAILURE_STAGE_SCHEMA_INVALID,
    FAILURE_TOOL_ERROR,
    FAILURE_USER_TOKEN_MISSING,
    STATUS_ARCHITECT_FAILED,
    STATUS_CLARIFICATION,
    STATUS_INVALID,
    STATUS_NO_CANDIDATES,
    STATUS_RETRIEVED,
    STATUS_SUCCESS,
    STATUS_UPSTREAM_ERROR,
    STATUS_VALIDATED,
    STRATEGY_SOURCE_DEFAULT,
    STRATEGY_SOURCE_MODEL,
)
from app.agent.registry import ToolExecutionError, get_governed_tool
from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# 自定义流事件：`turn.py` 按 kind 映射成 reasoning / token，不新增 SSE 事件类型
STREAM_KIND_REASONING = "reasoning"
STREAM_KIND_TOKEN = "token"
# 正文字符分片上限：只影响首屏节奏，拼接后必须与最终正文逐字一致
STREAM_CHUNK_CHARS = 240

# 候选摘要上限：CPU/GPU 需要横向比较，其余类别只保留定位够用的条目
MAX_CANDIDATE_ITEMS_DEFAULT = 10
MAX_CANDIDATE_ITEMS_BY_CATEGORY: dict[str, int] = {"CPU": 20, "GPU": 20}
# 摘要字段白名单：键为 State 中的规范名，值为工具输出里的候选字段名。
# Java 规格用 snake_case 且 TDP 字段名为 `tdp_w`，State 统一成 `tdp_watt`。
# 必须覆盖九条阻断级兼容规则读取的字段（插槽/内存代际/板型/长度/高度/功率/接口/条数），
# 否则模型只能靠型号猜测，而 compose 会直接判 COMPATIBILITY_CONFLICT。
_KEY_SPEC_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("socket", ("socket",)),
    ("supported_sockets", ("supported_sockets",)),
    ("memory_type", ("memory_type",)),
    ("form_factor", ("form_factor",)),
    ("supported_mainboard_form_factors", ("supported_mainboard_form_factors",)),
    ("tdp_watt", ("tdp_watt", "tdp_w")),
    ("vram_gb", ("vram_gb",)),
    ("length_mm", ("length_mm",)),
    ("max_gpu_length_mm", ("max_gpu_length_mm",)),
    ("height_mm", ("height_mm",)),
    ("max_cooler_height_mm", ("max_cooler_height_mm",)),
    ("capacity_gb", ("capacity_gb",)),
    ("wattage_w", ("wattage_w",)),
    ("module_count", ("module_count",)),
    ("memory_slots", ("memory_slots",)),
    ("m2_slot_count", ("m2_slot_count",)),
    ("sata_ports", ("sata_ports",)),
    ("interface", ("interface", "interface_type")),
    ("pcie_8pin_count", ("pcie_8pin_count",)),
    ("pcie_12vhpwr_count", ("pcie_12vhpwr_count",)),
)

# 兜底解析：模型不可用时仍要能从「8000 元、打游戏」得到可用需求
_YUAN_PATTERN = re.compile(r"(\d+)\s*(?:元|块|人民币)")
_WAN_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?\s*(?:万|w|W)")
# 预算区间与开区间：两条正则都优先于单值匹配，避免「12000–20000」只取到 20000
_BUDGET_RANGE_PATTERN = re.compile(
    r"(\d+)\s*(?:元|块)?\s*(?:-|–|—|~|～|至|到)\s*(\d+)\s*(?:元|块|人民币)"
)
_BUDGET_ABOVE_PATTERN = re.compile(r"(\d+)\s*(?:元|块|人民币)?\s*(?:以上|起|往上|起步)")
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
    (BuildScenario.MEDIA, ("影音", "htpc", "家庭影院", "客厅", "媒体中心")),
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

# Architect 修正上限：首次提案之外最多再修正两次，避免无限重选
ARCHITECT_MAX_REPAIRS = 2
# 知识检索工具名；调用次数受 AGENT__ARCHITECT_MAX_KNOWLEDGE_CALLS 与工具配额双重限制
KNOWLEDGE_TOOL_NAME = "search_knowledge"
# 单条引用片段进入提示词的上限：只保留解释取舍所需的长度
MAX_KNOWLEDGE_PROMPT_SNIPPET_CHARS = 300
# 场景 → 检索词：只描述取舍方向，不携带型号、价格或任何用户隐私字段
_KNOWLEDGE_SCENARIO_TERMS: dict[str, str] = {
    "GAMING": "游戏 装机 显卡 与 处理器 预算 取舍 原则",
    "VIDEO_EDITING": "视频剪辑 装机 多核 内存 存储 取舍 原则",
    "PROGRAMMING": "编程开发 装机 多核 内存 取舍 原则",
    "RENDERING": "渲染 装机 多核 功耗 散热 取舍 原则",
    "AI_INFERENCE": "本地推理 装机 显存 内存带宽 取舍 原则",
    "CREATIVE": "创作设计 装机 性能 内存 取舍 原则",
    "OFFICE": "办公 装机 静音 稳定 取舍 原则",
    "MEDIA": "影音 装机 静音 功耗 取舍 原则",
    "BALANCED": "整机 装机 预算 分配 性能 取舍 原则",
}
# 失败类型 → 检索词：修正阶段只查「怎么权衡」，不查具体型号
_KNOWLEDGE_FAILURE_TERMS: dict[str, str] = {
    FAILURE_CANDIDATE_NOT_IN_POOL: "候选范围 选型 原则",
    FAILURE_OFFER_UNAVAILABLE: "报价不可用 选型 原则",
    FAILURE_COMPATIBILITY_CONFLICT: "硬件兼容性 冲突 权衡 原则",
    FAILURE_BUDGET_EXCEEDED: "预算超限 取舍 原则",
    FAILURE_USER_TOKEN_MISSING: "身份失效 修正 原则",
    FAILURE_TOOL_ERROR: "组装失败 修正 原则",
    FAILURE_OUTPUT_TRUNCATED: "结果截断 修正 原则",
    FAILURE_MODEL_UNAVAILABLE: "模型不可用 修正 原则",
}
# 增量校验覆盖的核心组件：插槽、内存代际、显卡供电等冲突都在这一组里交叉判定。
# 散热器插槽也在此预检：否则候选摘要缺失插槽信息时只能等到 compose 才暴露冲突。
ARCHITECT_PARTIAL_CORE_CATEGORIES: tuple[HardwareCategory, ...] = (
    HardwareCategory.CPU,
    HardwareCategory.MOTHERBOARD,
    HardwareCategory.MEMORY,
    HardwareCategory.GPU,
    HardwareCategory.COOLER,
)
# 模型不可用时的确定性默认策略；来源标记为 DEFAULT，不得伪装成模型产物
DEFAULT_STRATEGY_RATIONALE = "未获得可用策略，按预算内性能与价格平衡的默认方向组装。"
DEFAULT_STRATEGY_TRADEOFFS: tuple[str, ...] = (
    "预算上限不可突破；出现冲突时优先保证核心性能，其次考虑静音与升级空间。",
)
# 部分校验状态：只有 FAIL 触发修正，UNKNOWN 只记录
PARTIAL_STATUS_FAIL = "FAIL"
PARTIAL_STATUS_UNKNOWN = "UNKNOWN"
# 候选清单注入模型的摘要字段；与 `_candidate_summary` 的白名单保持一致
_ARCHITECT_SPEC_FIELDS: tuple[tuple[str, str], ...] = (
    ("socket", "插槽"),
    ("supported_sockets", "支持插槽"),
    ("memory_type", "内存类型"),
    ("form_factor", "板型"),
    ("supported_mainboard_form_factors", "支持板型"),
    ("memory_slots", "内存槽"),
    ("module_count", "条数"),
    ("tdp_watt", "TDP(W)"),
    ("vram_gb", "显存GB"),
    ("length_mm", "长度MM"),
    ("max_gpu_length_mm", "限长MM"),
    ("height_mm", "高MM"),
    ("max_cooler_height_mm", "限高MM"),
    ("capacity_gb", "容量GB"),
    ("wattage_w", "功率W"),
    ("pcie_8pin_count", "8pin数"),
    ("pcie_12vhpwr_count", "12VHPWR数"),
    ("external_power", "外接供电"),
    ("m2_slot_count", "M.2数"),
    ("sata_ports", "SATA数"),
    ("interface", "接口"),
)
# 结构化失败类型 → 被违反的规则标识，供修正提示使用
_FAILURE_RULE_IDS: dict[str, tuple[str, ...]] = {
    FAILURE_CANDIDATE_NOT_IN_POOL: ("candidate_id_membership",),
    FAILURE_OFFER_UNAVAILABLE: ("offer_available",),
    FAILURE_COMPATIBILITY_CONFLICT: ("compatibility_rules",),
    FAILURE_BUDGET_EXCEEDED: ("budget_max",),
    FAILURE_USER_TOKEN_MISSING: ("user_token",),
    FAILURE_TOOL_ERROR: ("compose_available",),
    FAILURE_OUTPUT_TRUNCATED: ("compose_output_complete",),
    FAILURE_MODEL_UNAVAILABLE: ("structured_output",),
}


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
    """确定性兜底解析；覆盖预算区间、用途与「只接受核验价」三类关键信号。"""
    budget_min_fen, budget_max_fen = _parse_budget(text)

    scenario = BuildScenario.BALANCED
    scenario_explicit = False
    for candidate, keywords in _SCENARIO_KEYWORDS:
        if any(keyword in text.lower() for keyword in keywords):
            scenario = candidate
            scenario_explicit = True
            break

    require_verified = any(keyword in text for keyword in _VERIFIED_KEYWORDS)
    missing: list[str] = []
    if budget_min_fen is None and budget_max_fen is None:
        missing.append("budget_max_fen")
    if not scenario_explicit:
        missing.append("scenario")

    needs_clarification = (
        budget_min_fen is None and budget_max_fen is None and not scenario_explicit
    )
    question = None
    if needs_clarification:
        question = (
            "请告诉我预算范围（例如 8000 元）和主要用途"
            "（游戏、创作或办公），我再给出具体配置。"
        )

    requirements = PCRequirements(
        budget_min_fen=budget_min_fen,
        budget_max_fen=budget_max_fen,
        scenario=scenario,
        scenario_explicit=scenario_explicit,
        require_verified_offers=require_verified,
        needs_clarification=needs_clarification,
        clarification_question=question,
        missing_fields=missing,
    )
    return _apply_preference(_apply_render_mode(requirements, text), text)


def _parse_budget(text: str) -> tuple[int | None, int | None]:
    """解析预算区间、开区间与单值；区间必须同时保留上下限。

    「12000–20000 元」不能只取 20000，「20000 元以上」也不能被当成上限 20000。
    """
    range_match = _BUDGET_RANGE_PATTERN.search(text)
    if range_match:
        first = _fen_from_yuan_text(range_match.group(1))
        second = _fen_from_yuan_text(range_match.group(2))
        return min(first, second), max(first, second)
    above_match = _BUDGET_ABOVE_PATTERN.search(text)
    if above_match:
        return _fen_from_yuan_text(above_match.group(1)), None
    wan_match = _WAN_PATTERN.search(text)
    if wan_match:
        return None, _fen_from_yuan_text(wan_match.group(1), wan_match.group(2), wan=True)
    yuan_match = _YUAN_PATTERN.search(text)
    if yuan_match:
        return None, _fen_from_yuan_text(yuan_match.group(1))
    return None, None


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
    # 只记录结构化字段，不记录用户原文：用于复盘预算、场景与偏好是否解析正确
    logger.info(
        "pc.requirements_parsed",
        budget_min_fen=requirements.budget_min_fen,
        budget_max_fen=requirements.budget_max_fen,
        scenario=requirements.scenario.value,
        scenario_explicit=requirements.scenario_explicit,
        preference=requirements.preference.value if requirements.preference else None,
        min_memory_gb=requirements.min_memory_gb,
        min_storage_gb=requirements.min_storage_gb,
        needs_clarification=requirements.needs_clarification,
    )
    return {
        "requirements": requirements.model_dump(),
        # 质量评审是单轮状态：新回合必须清空，避免上一轮的约束与提示串到下一轮
        "quality_review": None,
        "quality_notice": None,
        "quality_feedback": None,
        "quality_retry_count": 0,
        "workflow_status": "parsed",
    }


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


def default_build_strategy() -> BuildStrategy:
    """确定性默认策略；只在模型不可用或输出非法时使用。"""
    return BuildStrategy(
        strategy_id=StrategyId.BALANCED,
        rationale_summary=DEFAULT_STRATEGY_RATIONALE,
        component_priorities=[
            ComponentPriority(category=HardwareCategory.CPU, focus="多核性能与平台扩展"),
            ComponentPriority(category=HardwareCategory.GPU, focus="图形性能与显存容量"),
        ],
        tradeoff_policy=list(DEFAULT_STRATEGY_TRADEOFFS),
    )


async def build_strategist(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    strategist_prompt: str,
) -> dict[str, Any]:
    """制定配置策略；模型不可用或 Schema 非法时退化为默认策略，不阻断回合。"""
    strategy = await invoke_model_structured(
        model,
        [
            SystemMessage(content=strategist_prompt),
            HumanMessage(content=_requirements_text(as_mapping(state.get("requirements")))),
        ],
        schema=BuildStrategy,
        config=config,
        agent_id=agent_id,
        purpose="build_strategist",
    )
    if strategy is None:
        # 兜底不阻断，但必须如实标记来源：默认策略不能伪装成模型产出
        logger.warning("pc.strategy_defaulted", reason="model_unavailable_or_invalid")
        fallback = default_build_strategy()
        return {
            "build_strategy": fallback.model_dump(mode="json"),
            "strategy_source": STRATEGY_SOURCE_DEFAULT,
        }
    logger.info("pc.strategy_selected", strategy_id=strategy.strategy_id.value)
    return {
        "build_strategy": strategy.model_dump(mode="json"),
        "strategy_source": STRATEGY_SOURCE_MODEL,
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
        # 文案本身是安全的用户提示，但必须留日志，否则上游故障无法定位
        logger.warning(
            "pc.tool_failed",
            tool=tool.name,
            error_type="tool_execution",
            message=str(exc),
        )
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
    candidate_sets: dict[str, list[dict[str, Any]]] = {}
    truncated: dict[str, int] = {}
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
        items, items_error = _candidate_items(data)
        if items is None:
            # `list` 存在但不是对象数组：如实标记上游异常，不能当成「没有候选」继续
            upstream_failed = True
            events.append(_tool_end("search_hardware_candidates", items_error or "查询失败"))
            continue
        total = as_int(data.get("total"), len(items))
        counts[category.value] = total
        catalog_version = as_text(data.get("catalogVersion"), catalog_version)
        summaries, dropped = _summarize_candidates(category.value, items)
        candidate_sets[category.value] = summaries
        if dropped:
            truncated[category.value] = dropped
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
            "candidate_sets": candidate_sets,
            "candidate_truncated": truncated,
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
            "candidate_sets": candidate_sets,
            "candidate_truncated": truncated,
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
        "candidate_sets": candidate_sets,
        "candidate_truncated": truncated,
        "candidate_pool": {
            "catalog_version": catalog_version,
            "category_counts": counts,
            "missing_categories": [],
            "benchmarks": benchmarks,
            "offer_summary": offer_summary,
        },
    }


def _candidate_items(data: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """校验候选数组形状；`list` 存在但不是对象数组时按上游结构异常处理。"""
    raw_items = data.get("list")
    if raw_items is None:
        return [], None
    if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
        return None, "配置数据格式异常"
    return raw_items, None


def _compact_spec_value(value: object) -> str | int | None:
    """把规格值压成可进提示词的短文本：列表用 `/` 连接，空值与布尔值丢弃。

    兼容规则读取的 `supported_sockets` / `supported_mainboard_form_factors` 都是数组，
    只接受标量会让这些字段整段消失，模型只能靠型号名猜兼容性。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value or None
    if isinstance(value, (list, tuple)):
        parts = [as_text(item) for item in value]
        text = "/".join(part for part in parts if part)
        return text or None
    return None


def _external_power_text(value: object) -> str | None:
    """显卡外接供电压成 `PCIE_8PIN×1`：供电规则同时看接口类型与数量。"""
    payload = as_mapping(value)
    connector = as_text(payload.get("connector_type"))
    count = as_int(payload.get("count"))
    if not connector:
        return None
    return f"{connector}×{count}" if count and count > 0 else connector


def _candidate_summary(item: dict[str, Any]) -> dict[str, Any]:
    """按白名单生成候选摘要；型号文本、链接与整段规格都不进入 State。"""
    specifications = as_mapping(item.get("specifications"))
    summary: dict[str, Any] = {
        "hardware_id": as_text(item.get("hardwareId")),
        "display_name": as_text(item.get("displayName"), as_text(item.get("modelName"))),
    }
    for output_key, source_keys in _KEY_SPEC_FIELDS:
        for source_key in source_keys:
            compact = _compact_spec_value(specifications.get(source_key))
            if compact is not None:
                summary[output_key] = compact
                break
    external_power = _external_power_text(specifications.get("external_power"))
    if external_power is not None:
        summary["external_power"] = external_power
    price_fen = item.get("priceFen")
    if isinstance(price_fen, int) and not isinstance(price_fen, bool):
        summary["price_fen"] = price_fen
    summary["data_quality_status"] = as_text(item.get("dataQualityStatus"))
    summary["lifecycle_status"] = as_text(item.get("lifecycleStatus"))
    summary["missing_fields"] = [
        field for field in (as_text(raw) for raw in as_list(item.get("missingFields"))) if field
    ]
    return summary


def _summarize_candidates(
    category: str, items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """按工具返回顺序截断；返回 (摘要列表, 被丢弃条数)。"""
    limit = MAX_CANDIDATE_ITEMS_BY_CATEGORY.get(category, MAX_CANDIDATE_ITEMS_DEFAULT)
    return [_candidate_summary(item) for item in items[:limit]], max(0, len(items) - limit)


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


def _architect_fen_text(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return format_fen(value)
    return "未设置"


def _requirements_text(requirements: dict[str, Any]) -> str:
    """只给结构化需求，不把用户原文当成可覆盖系统规则的指令。"""
    preference = as_text(requirements.get("preference"), "未指定")
    render_mode = as_text(requirements.get("render_mode"), "未指定")
    return "\n".join(
        [
            "## 用户需求",
            f"- 预算下限：{_architect_fen_text(requirements.get('budget_min_fen'))}",
            f"- 预算上限：{_architect_fen_text(requirements.get('budget_max_fen'))}",
            f"- 用途：{as_text(requirements.get('scenario'), 'BALANCED')}",
            f"- 选型偏好：{preference}",
            f"- 渲染方式：{render_mode}",
            f"- 最低内存：{requirements.get('min_memory_gb') or '未指定'} GB",
            f"- 最低存储：{requirements.get('min_storage_gb') or '未指定'} GB",
            f"- 只接受核验报价：{'是' if requirements.get('require_verified_offers') else '否'}",
        ]
    )


# 质量反馈的修正方向只有两种；渲染成中文，避免模型把字段名当成可执行指令
_QUALITY_DIRECTION_LABELS: dict[str, str] = {
    "increase": "提高（不低于目标值）",
    "decrease": "降低（不高于目标值）",
}

# 策略标识的中文说明只用于提示词可读性，不参与任何路由判断
_STRATEGY_LABELS: dict[str, str] = {
    "GPU_FIRST": "图形优先",
    "CPU_FIRST": "处理器优先",
    "BALANCED": "均衡",
    "QUIET": "静音优先",
    "POWER_EFFICIENT": "低功耗优先",
    "UPGRADEABLE": "升级优先",
    "VALUE": "性价比优先",
}
_STRATEGY_TENDENCY_LABELS: dict[str, str] = {
    "HIGHER": "更充裕",
    "BALANCED": "居中",
    "LOWER": "更节制",
}


def _category_labels(raw: Any) -> str:
    """把类别代码渲染成中文标签；未知值原样保留，避免丢失定位信息。"""
    labels = [
        CATEGORY_LABELS.get(category, category)
        for category in (as_text(item) for item in as_list(raw))
        if category
    ]
    return "、".join(labels)


def _architect_quality_feedback_text(feedback: dict[str, Any]) -> str:
    """把质量评审的结构化发现翻译成换件要求；不出现求解器字段名与原始参数。"""
    findings = [as_mapping(item) for item in as_list(feedback.get("findings"))]
    if not findings:
        return ""
    lines = [
        "## 上一轮质量评审（必须据此修正）",
        f"- 失败类型：{as_text(feedback.get('failure_type'))}",
    ]
    for entry in findings:
        direction = as_text(entry.get("direction"))
        lines.append(
            f"- 问题：{as_text(entry.get('issue'))}"
            f"；受影响类别：{_category_labels(entry.get('affected_categories'))}"
            f"；当前值：{format_fen(as_int(entry.get('current_value_fen')))}"
            f"；目标值：{format_fen(as_int(entry.get('target_value_fen')))}"
            f"；方向：{_QUALITY_DIRECTION_LABELS.get(direction, direction or '未指定')}"
        )
    preserve = _category_labels(feedback.get("must_preserve_categories"))
    if preserve:
        lines.append(f"- 必须保持不变：{preserve}")
    allowed = _category_labels(feedback.get("allowed_changes"))
    if allowed:
        lines.append(f"- 允许修改：{allowed}")
    lines.append(f"- 质量重解次数：{as_int(feedback.get('repair_attempt'))}")
    return "\n".join(lines)


def _architect_candidate_line(summary: dict[str, Any]) -> str:
    fields = [
        f"ID={as_text(summary.get('hardware_id'), '缺失')}",
        f"名称={as_text(summary.get('display_name'), '未提供')}",
    ]
    price = summary.get("price_fen")
    if isinstance(price, int) and not isinstance(price, bool) and price > 0:
        fields.append(f"价格={format_fen(price)}")
    else:
        fields.append("价格=未提供")
    for key, label in _ARCHITECT_SPEC_FIELDS:
        value = summary.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and value != "":
            fields.append(f"{label}={value}")
    if as_text(summary.get("data_quality_status")):
        fields.append(f"数据质量={as_text(summary.get('data_quality_status'))}")
    if as_text(summary.get("lifecycle_status")):
        fields.append(f"生命周期={as_text(summary.get('lifecycle_status'))}")
    missing = [as_text(item) for item in as_list(summary.get("missing_fields"))]
    if missing:
        fields.append(f"缺失字段={','.join(missing)}")
    return "- " + " | ".join(fields)


def _architect_catalog_text(candidate_sets: dict[str, Any]) -> str:
    """按类别注入紧凑候选清单：只放摘要字段，并要求只能从中选择 ID。"""
    lines = ["## 候选清单（只能选择以下硬件 ID，禁止编造）"]
    for category in REQUIRED_CATEGORIES:
        summaries = as_list(candidate_sets.get(category.value))
        lines.append(f"### {CATEGORY_LABELS[category.value]}（{category.value}）")
        if not summaries:
            lines.append("- 无候选；不得为该类别虚构硬件")
            continue
        lines.extend(_architect_candidate_line(as_mapping(item)) for item in summaries)
    return "\n".join(lines)


def _architect_repair_text(failure: dict[str, Any]) -> str:
    if not failure:
        return ""
    failure_type = as_text(failure.get("failure_type"), as_text(failure.get("reason"), "UNKNOWN"))
    lines = [
        "## 上一轮失败（必须据此修正）",
        f"- 失败类型：{failure_type}",
    ]
    for key, label in (
        ("affected_categories", "受影响类别"),
        ("affected_hardware_ids", "受影响硬件"),
        ("violated_rule_ids", "违反规则"),
        ("authoritative_error_details", "服务端错误"),
        ("must_preserve_categories", "必须保持不变"),
        ("allowed_changes", "允许修改"),
    ):
        raw = failure.get(key)
        if isinstance(raw, list):
            text = "、".join(as_text(item) for item in raw if as_text(item))
        else:
            text = as_text(raw)
        if text:
            lines.append(f"- {label}：{text}")
    lines.append(f"- 已用修正次数：{as_int(failure.get('repair_attempt'))}/{ARCHITECT_MAX_REPAIRS}")
    return "\n".join(lines)


def _categories_with_values(mapping: dict[str, str]) -> str:
    """渲染「类别=值」列表；空映射返回空串，避免提示词出现空行。"""
    return "；".join(f"{category}={value}" for category, value in mapping.items() if value)


def _strategy_summary_lines(strategy: dict[str, Any]) -> list[str]:
    raw_id = as_text(strategy.get("strategy_id"))
    priorities = {
        as_text(as_mapping(item).get("category")): as_text(as_mapping(item).get("focus"))
        for item in as_list(strategy.get("component_priorities"))
        if as_mapping(item)
    }
    tendencies = {
        as_text(as_mapping(item).get("category")): _STRATEGY_TENDENCY_LABELS.get(
            as_text(as_mapping(item).get("tendency")), ""
        )
        for item in as_list(strategy.get("budget_allocation_guidance"))
        if as_mapping(item)
    }
    lines = [
        f"- 策略：{raw_id}（{_STRATEGY_LABELS.get(raw_id, '未分类')}）",
        f"- 方向说明：{as_text(strategy.get('rationale_summary'), '未提供')}",
    ]
    if priorities:
        lines.append(f"- 组件关注点：{_categories_with_values(priorities)}")
    if tendencies:
        lines.append(
            f"- 预算倾向（仅类别之间的软取向，不是预算表）：{_categories_with_values(tendencies)}"
        )
    policies = [as_text(item) for item in as_list(strategy.get("tradeoff_policy")) if as_text(item)]
    if policies:
        lines.append(f"- 权衡原则：{'；'.join(policies)}")
    notes = [as_text(item) for item in as_list(strategy.get("retrieval_notes")) if as_text(item)]
    if notes:
        lines.append(f"- 补充关注点：{'；'.join(notes)}")
    return lines


def _strategy_text(state: PCConfigState) -> str:
    """把策略摘要注入 Architect 上下文；预算倾向只给方向，不给金额。"""
    strategy = as_mapping(state.get("build_strategy"))
    if not strategy:
        return ""
    lines = ["## 配置策略（软规划）", *_strategy_summary_lines(strategy)]
    if as_text(state.get("strategy_source")) == STRATEGY_SOURCE_DEFAULT:
        lines.append("- 策略来源：模型未返回可用策略，当前为确定性默认策略（DEFAULT）。")
    else:
        lines.append("- 策略来源：模型产出（MODEL）。")
    lines.append(
        "- 约束：策略是软倾向，不得覆盖预算上限、用户硬约束与 Java 校验结果，"
        "也不得据此推算或填入任何预算金额。"
    )
    return "\n".join(lines)


def _architect_context(
    state: PCConfigState,
    failure: dict[str, Any],
    knowledge_text: str = "",
) -> str:
    sections = [
        _requirements_text(as_mapping(state.get("requirements"))),
        _strategy_text(state),
        _architect_quality_feedback_text(as_mapping(state.get("quality_feedback"))),
        knowledge_text,
        _architect_catalog_text(as_mapping(state.get("candidate_sets"))),
        _architect_repair_text(failure),
    ]
    return "\n\n".join(section for section in sections if section)


def _architect_failure(
    failure_type: str,
    *,
    message: str,
    categories: list[str] | None = None,
    hardware_ids: list[str] | None = None,
    rule_ids: tuple[str, ...] | None = None,
    preserve: list[str] | None = None,
    repair_attempt: int = 0,
    stage: str | None = None,
    error_type: str | None = None,
    http_status: int | None = None,
) -> dict[str, Any]:
    """按方案 §12.2 的形状描述失败；没有服务端明细时不编造受影响类别。

    `error_type` / `http_status` 只承载异常类型与上游状态码：排查「模型没有输出」
    时必须能区分鉴权失败、超时与 Provider 不支持，但不能把异常正文或密钥带出去。
    """
    affected = list(categories or [])
    keep = list(preserve or [])
    all_categories = [category.value for category in REQUIRED_CATEGORIES]
    allowed = [item for item in all_categories if item not in set(keep)]
    return {
        # `reason` 兼容现有失败文案的结构，`failure_type` 是修正闭环的正式字段
        "reason": failure_type,
        "failure_type": failure_type,
        # 具体阶段：区分 Provider 不支持、Schema 非法、候选越界与组装失败
        "failure_stage": stage,
        # 脱敏诊断：仅异常类型与 HTTP 状态码，不含异常文本、模型输出与密钥
        "error_type": error_type,
        "http_status": http_status,
        "affected_categories": affected,
        "affected_hardware_ids": list(hardware_ids or []),
        "violated_rule_ids": list(rule_ids or _FAILURE_RULE_IDS.get(failure_type, ())),
        "authoritative_error_details": message,
        "must_preserve_categories": keep,
        "allowed_changes": allowed,
        "repair_attempt": repair_attempt,
    }


def _compose_failure_stage(code: str) -> str:
    """把组装失败细化到原因码，例如 `compose_error:budget_exceeded`。"""
    return f"{FAILURE_STAGE_COMPOSE_ERROR_PREFIX}{code.lower()}"


@dataclass
class _ArchitectSession:
    """一次 Architect 节点执行的可变上下文，避免循环里传递大量参数。"""

    requirements: dict[str, Any]
    candidate_sets: dict[str, Any]
    events: list[dict[str, Any]]
    partial_reports: list[dict[str, Any]]
    partial_checks: int
    repair_count: int
    max_partial_checks: int
    knowledge_calls: int
    max_knowledge_calls: int
    knowledge_citations: list[dict[str, Any]]

    def can_repair(self) -> bool:
        """修正次数上限对所有失败类型统一生效。"""
        return self.repair_count < ARCHITECT_MAX_REPAIRS

    def can_search_knowledge(self) -> bool:
        """知识检索与工具配额是两道独立闸门，任一耗尽都不再调用。"""
        return self.knowledge_calls < self.max_knowledge_calls

    def bump_repair(self, failure: dict[str, Any]) -> dict[str, Any]:
        self.repair_count += 1
        return {**failure, "repair_attempt": self.repair_count}


def _architect_failure_update(
    failure: dict[str, Any],
    session: _ArchitectSession,
    proposal: BuildProposal | None,
) -> dict[str, Any]:
    """失败必须清空上一轮方案，禁止把未验证结果带到渲染与前端。"""
    return {
        "workflow_status": STATUS_ARCHITECT_FAILED,
        "build_failure": failure,
        "build_result": None,
        "compatibility_report": None,
        "build_proposal": proposal.model_dump(mode="json") if proposal is not None else None,
        "architect_repair_count": session.repair_count,
        "partial_compatibility_reports": session.partial_reports,
        "partial_check_count": session.partial_checks,
        "knowledge_citations": session.knowledge_citations,
        "knowledge_call_count": session.knowledge_calls,
        "tool_events": session.events,
    }


def _invalid_proposal_components(
    proposal: BuildProposal, candidate_sets: dict[str, Any]
) -> list[tuple[str, str]]:
    """ID 存在性校验必须独立于 Schema：越界提案不能交给 Java。"""
    invalid: list[tuple[str, str]] = []
    for component in proposal.selected_components:
        allowed = {
            as_text(as_mapping(item).get("hardware_id"))
            for item in as_list(candidate_sets.get(component.category.value))
        }
        if component.hardware_id not in allowed:
            invalid.append((component.category.value, component.hardware_id))
    return invalid


def _proposal_hardware_args(proposal: BuildProposal) -> dict[str, Any]:
    return {
        component.category.value.lower(): component.hardware_id
        for component in proposal.selected_components
    }


def _partial_check_args(proposal: BuildProposal) -> dict[str, str]:
    """只提交核心组件：插槽、内存代际与显卡供电的依赖都落在这一组。"""
    return {
        component.category.value.lower(): component.hardware_id
        for component in proposal.selected_components
        if component.category in ARCHITECT_PARTIAL_CORE_CATEGORIES
    }


def _partial_unknown(rule_id: str) -> dict[str, Any]:
    """校验不可用时如实返回 UNKNOWN；不能省略状态让调用方误判为通过。"""
    return {
        "overallStatus": PARTIAL_STATUS_UNKNOWN,
        "checks": [
            {
                "ruleId": rule_id,
                "status": PARTIAL_STATUS_UNKNOWN,
                "componentIds": [],
                "missingFields": [],
            }
        ],
    }


def _partial_report(data: dict[str, Any]) -> dict[str, Any] | None:
    """裁剪 Java 响应：只保留规则标识、状态、关联组件与缺失字段。"""
    overall = as_text(data.get("overallStatus")).upper()
    if overall not in {"PASS", "WARNING", PARTIAL_STATUS_FAIL, PARTIAL_STATUS_UNKNOWN}:
        return None
    checks: list[dict[str, Any]] = []
    for item in as_list(data.get("checks")):
        check = as_mapping(item)
        rule_id = as_text(check.get("ruleId"))
        if not rule_id:
            continue
        checks.append(
            {
                "ruleId": rule_id,
                "status": as_text(check.get("status")).upper(),
                "componentIds": [
                    as_text(raw) for raw in as_list(check.get("componentIds")) if as_text(raw)
                ],
                "missingFields": [
                    as_text(raw) for raw in as_list(check.get("missingFields")) if as_text(raw)
                ],
            }
        )
    return {"overallStatus": overall, "checks": checks}


async def _run_partial_check(
    proposal: BuildProposal, events: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """调用增量校验；返回 None 表示本次没有发生调用（不占用配额）。"""
    args = _partial_check_args(proposal)
    tool = get_governed_tool("check_partial_compatibility") if args else None
    if tool is None:
        logger.warning("pc.partial_check_unavailable", reason="tool_missing_or_no_components")
        return None

    events.append(_tool_start("check_partial_compatibility", dict(args)))
    data, error = await _call_tool(tool, args)
    if error is not None or data is None:
        events.append(_tool_end("check_partial_compatibility", error or "校验失败"))
        return _partial_unknown("partial_check_unavailable")
    report = _partial_report(data)
    if report is None:
        events.append(_tool_end("check_partial_compatibility", "返回结构异常"))
        return _partial_unknown("partial_check_invalid_payload")
    events.append(
        _tool_end("check_partial_compatibility", f"部分兼容性 {report['overallStatus']}")
    )
    return report


def _failed_check_categories(
    report: dict[str, Any], proposal: BuildProposal
) -> tuple[list[str], list[str]]:
    """把失败规则的组件标识映射成类别；返回 (类别, 规则标识)。"""
    category_by_id = {
        component.hardware_id.lower(): component.category.value
        for component in proposal.selected_components
    }
    all_categories = {category.value for category in REQUIRED_CATEGORIES}
    categories: list[str] = []
    rule_ids: list[str] = []
    for item in as_list(report.get("checks")):
        check = as_mapping(item)
        if as_text(check.get("status")) != PARTIAL_STATUS_FAIL:
            continue
        rule_id = as_text(check.get("ruleId"))
        if rule_id and rule_id not in rule_ids:
            rule_ids.append(rule_id)
        for raw in as_list(check.get("componentIds")):
            token = as_text(raw)
            if not token:
                continue
            category = category_by_id.get(token.lower()) or (
                token.upper() if token.upper() in all_categories else ""
            )
            if category and category not in categories:
                categories.append(category)
    return categories, rule_ids


def _partial_failure(
    report: dict[str, Any], proposal: BuildProposal, repair_count: int
) -> dict[str, Any] | None:
    """只有 FAIL 生成修正反馈；UNKNOWN 不得当作通过，也不强制重选。"""
    if as_text(report.get("overallStatus")) != PARTIAL_STATUS_FAIL:
        return None
    categories, rule_ids = _failed_check_categories(report, proposal)
    if not categories:
        # 规则没给出可定位的组件：按本次检查范围处理，避免凭空点名其他类别
        categories = [category.value for category in ARCHITECT_PARTIAL_CORE_CATEGORIES]
    affected = set(categories)
    hardware_ids = [
        component.hardware_id
        for component in proposal.selected_components
        if component.category.value in affected
    ]
    return _architect_failure(
        FAILURE_COMPATIBILITY_CONFLICT,
        message="增量校验发现已选核心组件冲突：" + "、".join(rule_ids or ["compatibility_rules"]),
        categories=categories,
        hardware_ids=hardware_ids,
        rule_ids=tuple(rule_ids) or ("compatibility_rules",),
        preserve=[
            category.value
            for category in REQUIRED_CATEGORIES
            if category.value not in affected
        ],
        repair_attempt=repair_count,
        stage=FAILURE_STAGE_PARTIAL_CHECK,
    )


async def _partial_gate(
    proposal: BuildProposal, session: _ArchitectSession
) -> dict[str, Any] | None:
    """提交整机前的增量校验；返回 FAIL 修正反馈，其余情况返回 None 继续组装。"""
    if session.partial_checks >= session.max_partial_checks:
        return None
    report = await _run_partial_check(proposal, session.events)
    if report is None:
        return None
    session.partial_checks += 1
    session.partial_reports.append(report)
    if as_text(report.get("overallStatus")) == PARTIAL_STATUS_UNKNOWN:
        logger.info("pc.partial_check_unknown", checked=len(session.partial_reports))
    return _partial_failure(report, proposal, session.repair_count)


def _normalize_compose_build(data: dict[str, Any]) -> dict[str, Any] | None:
    """把 compose 响应归一成与 solve 成功分支一致的 build 字典。"""
    build = as_mapping(data.get("build"))
    components = [as_mapping(item) for item in as_list(build.get("components"))]
    components = [item for item in components if item]
    categories = {as_text(item.get("category")) for item in components}
    required = {category.value for category in REQUIRED_CATEGORIES}
    if not build or len(components) != len(REQUIRED_CATEGORIES) or categories != required:
        return None
    normalized = dict(build)
    normalized["components"] = components
    normalized["compatibilityReport"] = as_mapping(build.get("compatibilityReport"))
    return normalized


@dataclass(frozen=True)
class _ComposeOutcome:
    """一次组装调用的结果；`retryable` 决定是否进入修正。"""

    build: dict[str, Any] | None
    failure: dict[str, Any] | None
    retryable: bool


def _compose_args(
    proposal: BuildProposal, requirements: dict[str, Any]
) -> dict[str, Any]:
    args = _proposal_hardware_args(proposal)
    budget_max = requirements.get("budget_max_fen")
    args["budget_max_fen"] = (
        budget_max
        if isinstance(budget_max, int) and not isinstance(budget_max, bool) and budget_max > 0
        else None
    )
    return args


async def _compose_proposal(
    proposal: BuildProposal,
    requirements: dict[str, Any],
    events: list[dict[str, Any]],
) -> _ComposeOutcome:
    args = _compose_args(proposal, requirements)
    events.append(_tool_start("compose_pc_build", args))
    tool = get_governed_tool("compose_pc_build")
    if tool is None:
        events.append(_tool_end("compose_pc_build", "工具未注册"))
        return _ComposeOutcome(
            None,
            _architect_failure(
                FAILURE_TOOL_ERROR,
                message="配置组装工具未注册。",
                stage=_compose_failure_stage("tool_missing"),
            ),
            False,
        )

    data, error = await _call_tool(tool, args)
    if error is not None or data is None:
        events.append(_tool_end("compose_pc_build", error or "组装失败"))
        return _ComposeOutcome(
            None,
            _architect_failure(
                FAILURE_TOOL_ERROR,
                message=error or "配置组装失败。",
                stage=_compose_failure_stage("tool_error"),
            ),
            True,
        )
    return _compose_payload_outcome(data, events)


def _compose_payload_outcome(
    data: dict[str, Any], events: list[dict[str, Any]]
) -> _ComposeOutcome:
    """解释治理层返回的载荷；业务失败与结构异常必须区分是否可修正。"""
    if data.get("_truncated") is True:
        events.append(_tool_end("compose_pc_build", "结果被截断"))
        return _ComposeOutcome(
            None,
            _architect_failure(
                FAILURE_OUTPUT_TRUNCATED,
                message="组装结果被治理层截断，无法作为完整方案使用。",
                stage=_compose_failure_stage("output_truncated"),
            ),
            False,
        )
    if data.get("composed") is False:
        failure_payload = as_mapping(data.get("failure"))
        reason = as_text(failure_payload.get("reason"), FAILURE_TOOL_ERROR)
        message = as_text(failure_payload.get("message"), "服务端未能生成配置。")
        retryable = failure_payload.get("retryable") is not False
        events.append(_tool_end("compose_pc_build", message))
        return _ComposeOutcome(
            None,
            _architect_failure(reason, message=message, stage=_compose_failure_stage(reason)),
            retryable,
        )

    build = _normalize_compose_build(data)
    if build is None:
        events.append(_tool_end("compose_pc_build", "返回结构异常"))
        return _ComposeOutcome(
            None,
            _architect_failure(
                FAILURE_TOOL_ERROR,
                message="组装结果缺少八类组件或兼容性报告。",
                stage=_compose_failure_stage("invalid_payload"),
            ),
            False,
        )
    events.append(
        _tool_end("compose_pc_build", f"总价 {format_fen(as_int(build.get('totalPriceFen')))}")
    )
    return _ComposeOutcome(build, None, True)


async def _request_architect_proposal(
    state: PCConfigState,
    failure: dict[str, Any],
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    architect_prompt: str,
    knowledge_text: str = "",
) -> StructuredOutcome[BuildProposal]:
    return await invoke_model_structured_outcome(
        model,
        [
            SystemMessage(content=architect_prompt),
            HumanMessage(content=_architect_context(state, failure, knowledge_text)),
        ],
        schema=BuildProposal,
        config=config,
        agent_id=agent_id,
        purpose="build_architect",
        # 推理模型的思考 token 计入输出：Architect 单独放大预算，其他节点保持全局值
        max_tokens=get_settings().agent.architect_max_tokens,
        # 选型是 8 类组合决策，长思考会把单次请求拖过 60s 客户端超时，SDK 再重试
        # 超时 2 次，一次选型就变成数分钟。Architect 关闭思考并禁用超时重试，
        # 把最坏耗时压到单次请求上限内；失败仍按 build_failure 正常上报。
        reasoning_effort="none",
        max_retries=0,
    )


def _architect_candidate_failure(
    invalid: list[tuple[str, str]], repair_count: int
) -> dict[str, Any]:
    invalid_categories = sorted({category for category, _ in invalid})
    return _architect_failure(
        FAILURE_CANDIDATE_NOT_IN_POOL,
        message="提案中的硬件 ID 不在本轮候选清单内。",
        categories=invalid_categories,
        hardware_ids=[hardware_id for _, hardware_id in invalid],
        preserve=[
            category.value
            for category in REQUIRED_CATEGORIES
            if category.value not in invalid_categories
        ],
        repair_attempt=repair_count,
        stage=FAILURE_STAGE_ID_NOT_IN_CANDIDATES,
    )


def _architect_success_update(
    proposal: BuildProposal,
    build: dict[str, Any],
    session: _ArchitectSession,
) -> dict[str, Any]:
    return {
        "workflow_status": STATUS_SUCCESS,
        "tool_events": session.events,
        "build_result": build,
        "build_failure": None,
        "compatibility_report": as_mapping(build.get("compatibilityReport")),
        "build_proposal": proposal.model_dump(mode="json"),
        "architect_repair_count": session.repair_count,
        "partial_compatibility_reports": session.partial_reports,
        "partial_check_count": session.partial_checks,
        "knowledge_citations": session.knowledge_citations,
        "knowledge_call_count": session.knowledge_calls,
    }


def _architect_session(state: PCConfigState) -> _ArchitectSession:
    return _ArchitectSession(
        requirements=as_mapping(state.get("requirements")),
        candidate_sets=as_mapping(state.get("candidate_sets")),
        events=[],
        # 增量校验、知识检索与修正次数按回合累计：质量重解重入时共享同一份上限
        partial_reports=list(as_list(state.get("partial_compatibility_reports"))),
        partial_checks=as_int(state.get("partial_check_count")),
        repair_count=as_int(state.get("architect_repair_count")),
        max_partial_checks=get_settings().agent.architect_max_partial_checks,
        knowledge_calls=as_int(state.get("knowledge_call_count")),
        max_knowledge_calls=get_settings().agent.architect_max_knowledge_calls,
        knowledge_citations=[
            as_mapping(item) for item in as_list(state.get("knowledge_citations"))
        ],
    )


def _knowledge_query_for_proposal(state: PCConfigState) -> str:
    """提案前查方法学依据：只用结构化需求拼检索词，不带型号与用户原文。"""
    requirements = as_mapping(state.get("requirements"))
    scenario = as_text(requirements.get("scenario"), "BALANCED")
    terms = _KNOWLEDGE_SCENARIO_TERMS.get(scenario, _KNOWLEDGE_SCENARIO_TERMS["BALANCED"])
    preference = as_text(requirements.get("preference"))
    if preference == Preference.PERFORMANCE.value:
        terms = f"{terms} 性能优先"
    elif preference == Preference.VALUE.value:
        terms = f"{terms} 性价比"
    return terms


def _knowledge_query_for_repair(failure: dict[str, Any]) -> str:
    """修正阶段查权衡原则：按失败类型与受影响类别检索，不查具体型号。"""
    failure_type = as_text(failure.get("failure_type"), as_text(failure.get("reason")))
    terms = _KNOWLEDGE_FAILURE_TERMS.get(failure_type, "选型修正 权衡 原则")
    categories = _category_labels(failure.get("affected_categories"))
    return f"{terms} {categories}".strip()


async def _search_knowledge(
    query: str,
    session: _ArchitectSession,
) -> str:
    """调用受治理工具检索知识；引用写入 session，返回可注入提示词的片段文本。

    检索不可用或未启用都只返回空串：Architect 必须继续用候选与校验结果决策。
    """
    tool = get_governed_tool(KNOWLEDGE_TOOL_NAME)
    if tool is None:
        logger.warning("pc.knowledge_tool_missing")
        return ""
    session.knowledge_calls += 1
    session.events.append(_tool_start(KNOWLEDGE_TOOL_NAME, {"query": query}))
    data, error = await _call_tool(tool, {"query": query})
    if error is not None or data is None:
        session.events.append(_tool_end(KNOWLEDGE_TOOL_NAME, error or "检索失败"))
        return ""
    if data.get("enabled") is False:
        session.events.append(_tool_end(KNOWLEDGE_TOOL_NAME, "知识检索未启用"))
        return ""
    citations = [as_mapping(item) for item in as_list(data.get("citations"))]
    citations = [item for item in citations if as_text(item.get("source_id"))]
    session.knowledge_citations = _merge_knowledge_citations(
        session.knowledge_citations, citations
    )
    message = as_text(data.get("error")) or f"引用 {len(citations)} 条"
    session.events.append(_tool_end(KNOWLEDGE_TOOL_NAME, message))
    return _knowledge_prompt_text(citations)


async def _architect_knowledge(session: _ArchitectSession, query: str) -> str:
    """RAG 关闭或次数耗尽时不发起调用；开启时失败也只降级为空文本。"""
    if not get_settings().rag.enabled or not session.can_search_knowledge():
        return ""
    return await _search_knowledge(query, session)


def _merge_knowledge_citations(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按 `source_id` 去重合并；同一来源在多轮检索中只保留首次出现的片段。"""
    merged = list(existing)
    seen = {as_text(item.get("source_id")) for item in existing}
    for item in incoming:
        source_id = as_text(item.get("source_id"))
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        merged.append(item)
    return merged


def _knowledge_prompt_text(citations: list[dict[str, Any]]) -> str:
    """渲染方法学依据；明确写出边界，防止模型把知识当成规格来源。"""
    if not citations:
        return ""
    lines = [
        "## 方法学依据（仅用于解释取舍，不得用于型号/规格/价格/兼容性结论）",
        (
            "- 下列片段只支撑「为什么这样取舍」；"
            "型号、规格、价格与兼容性只能来自候选清单与服务端校验结果。"
        ),
    ]
    for index, item in enumerate(citations, start=1):
        title = as_text(item.get("title"), "无标题")
        snippet = " ".join(as_text(item.get("snippet")).split())[
            :MAX_KNOWLEDGE_PROMPT_SNIPPET_CHARS
        ]
        source_name = as_text(item.get("source_name"))
        confidence = as_text(item.get("confidence_level"))
        meta = "；".join(
            part
            for part in (
                f"来源：{source_name}" if source_name else "",
                f"置信：{confidence}" if confidence else "",
            )
            if part
        )
        heading = f"[{index}] {title}（{meta}）" if meta else f"[{index}] {title}"
        lines.append(f"{heading}\n{snippet}")
    return "\n".join(lines)


async def build_architect(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    architect_prompt: str,
) -> dict[str, Any]:
    """LLM 选型：结构化提案 → 候选校验 → 增量校验 → Java 组装 → 有限修正。

    模型不可用或结构化输出失败时直接失败，绝不回退到旧求解器冒充 LLM 结果。
    """
    session = _architect_session(state)
    failure = as_mapping(state.get("build_failure"))
    last_proposal: BuildProposal | None = None
    # 提案前查一次方法学依据；RAG 关闭或配额耗尽时为空文本
    knowledge_text = await _architect_knowledge(
        session, _knowledge_query_for_proposal(state)
    )

    while True:
        proposal_outcome = await _request_architect_proposal(
            state,
            failure,
            config,
            model=model,
            agent_id=agent_id,
            architect_prompt=architect_prompt,
            knowledge_text=knowledge_text,
        )
        proposal = proposal_outcome.value
        if proposal is None:
            unavailable = _architect_failure(
                FAILURE_MODEL_UNAVAILABLE,
                message="模型未能返回符合 Schema 的选型提案。",
                repair_attempt=session.repair_count,
                # 模型返回空但未给出阶段时按 Schema 非法处理，避免失败不可定位
                stage=proposal_outcome.failure_stage or FAILURE_STAGE_SCHEMA_INVALID,
                # 鉴权失败 / 超时等真实异常必须随失败一起落盘，否则只能看到笼统阶段
                error_type=proposal_outcome.error_type,
                http_status=proposal_outcome.http_status,
            )
            return _architect_failure_update(unavailable, session, last_proposal)
        last_proposal = proposal

        invalid = _invalid_proposal_components(proposal, session.candidate_sets)
        if invalid:
            failure = _architect_candidate_failure(invalid, session.repair_count)
            if not session.can_repair():
                return _architect_failure_update(failure, session, proposal)
            failure = session.bump_repair(failure)
            knowledge_text = await _architect_repair_knowledge(session, failure, knowledge_text)
            continue

        # 增量校验只提前暴露核心组件冲突；整机校验仍由 compose 负责
        partial_failure = await _partial_gate(proposal, session)
        if partial_failure is not None:
            if not session.can_repair():
                return _architect_failure_update(partial_failure, session, proposal)
            failure = session.bump_repair(partial_failure)
            knowledge_text = await _architect_repair_knowledge(session, failure, knowledge_text)
            continue

        outcome = await _compose_proposal(proposal, session.requirements, session.events)
        if outcome.build is not None:
            return _architect_success_update(proposal, outcome.build, session)

        failure = outcome.failure or _architect_failure(
            FAILURE_TOOL_ERROR,
            message="配置组装失败。",
            stage=_compose_failure_stage("tool_error"),
        )
        if not outcome.retryable or not session.can_repair():
            return _architect_failure_update(failure, session, proposal)
        failure = session.bump_repair(failure)
        knowledge_text = await _architect_repair_knowledge(session, failure, knowledge_text)


async def _architect_repair_knowledge(
    session: _ArchitectSession,
    failure: dict[str, Any],
    previous_text: str,
) -> str:
    """修正时查权衡原则；没有新片段就沿用上一轮文本，避免提示词凭空消失。"""
    text = await _architect_knowledge(session, _knowledge_query_for_repair(failure))
    return text or previous_text


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
    if has_demo_price(build):
        reason += "当前方案包含演示价格，请以商品页实时信息为准。"
    elif has_observed_price(build):
        reason += "当前方案价格为平台检索参考价，未经人工核验，请以商品页实时信息为准。"
    return reason


def _stream_emitter() -> Callable[[dict[str, Any]], None]:
    """取 LangGraph 自定义流写入器；节点被单测直接调用时退化为空实现。"""
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return lambda _payload: None
    return writer


def _chunk_body(body: str, limit: int = STREAM_CHUNK_CHARS) -> list[str]:
    """按行合并成不超过 `limit` 的块；`"".join(结果)` 必须与 `body` 完全一致。"""
    chunks: list[str] = []
    current = ""
    for line in body.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


async def response_generator(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    system_prompt: str,
    generator_prompt: str,
) -> dict[str, Any]:
    """写最终正文：思考内容实时下发，正文在校验通过后按块下发。"""
    emit = _stream_emitter()
    status = as_text(state.get("workflow_status"))
    if status != STATUS_SUCCESS:
        body = render_failure_markdown(state)
        for piece in _chunk_body(body):
            emit({"kind": STREAM_KIND_TOKEN, "text": piece})
        return {"messages": [AIMessage(content=body)]}

    build = as_mapping(state.get("build_result"))
    reason = await _generate_reason(
        state,
        config=config,
        model=model,
        agent_id=agent_id,
        system_prompt=system_prompt,
        generator_prompt=generator_prompt,
        on_reasoning=lambda text: emit({"kind": STREAM_KIND_REASONING, "text": text}),
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
    # 模型文案必须整段通过校验后才下发：命中数字或型号时整段替换，不能先流后改。
    # 正文必须等思考结束后再下发，保证用户先看到思考过程，再看到最终结果
    quality_notice = as_text(state.get("quality_notice"))
    if quality_notice:
        # 质量提示放在自检之后追加：它描述的是取舍事实，不参与兼容性文案断言
        body = f"{body}\n\n> 质量提示：{quality_notice}"
    for piece in _chunk_body(body):
        emit({"kind": STREAM_KIND_TOKEN, "text": piece})
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
    on_reasoning: Callable[[str], None] | None = None,
) -> str | None:
    if model is None:
        return None
    text = await stream_model_text(
        model,
        [
            SystemMessage(content=f"{system_prompt}\n\n{generator_prompt}"),
            HumanMessage(content=_reason_context(state)),
        ],
        config=config,
        agent_id=agent_id,
        purpose="response_generator",
        on_reasoning=on_reasoning,
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
