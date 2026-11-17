"""多 Agent 骨架：并行 Specialist 分析与 Critic 独立评审。

设计边界：
- 默认关闭（`AGENT__MULTI_AGENT_ENABLED=false`），关闭时图路由直接绕过本模块；
- Specialist 只读结构化需求、策略与候选摘要，不调用工具、不产出最终选型；
- Critic 只评审已通过 Java 校验的方案，不改方案、不改价格；
  仅当判定 REVISE 且存在 HIGH/MEDIUM 问题时请求一次受限修正，LOW 问题只做披露；
- 任何模型失败都降级为空结果，绝不阻断回合或伪造内容。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.pc.llm import invoke_model_structured
from app.agent.pc.nodes import candidate_summary_line
from app.agent.pc.renderer import as_int, as_list, as_mapping, as_text
from app.agent.pc.schemas import (
    REQUIRED_CATEGORIES,
    BuildScenario,
    CriticDecision,
    CriticReport,
    PCRequirements,
    SpecialistReport,
    SpecialistRole,
)
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import STATUS_SUCCESS
from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# 只有这些场景才值得并行分析：办公/影音等轻负载场景引入 Specialist 收益不足以抵消延迟
COMPLEX_SCENARIOS = frozenset(
    {
        BuildScenario.GAMING,
        BuildScenario.CREATIVE,
        BuildScenario.VIDEO_EDITING,
        BuildScenario.RENDERING,
        BuildScenario.PROGRAMMING,
    }
)
SPECIALIST_MAX_CONTEXT_CHARS = 6000
# Critic 与 Specialist 使用同一量级的上下文预算，避免评审被候选清单淹没
CRITIC_MAX_CONTEXT_CHARS = 4000

# 每类最多 3 条候选：Specialist 只做方向性判断，八类都要出现才不会被截断
MAX_CANDIDATES_PER_CATEGORY = 3


def should_run_specialists(state: PCConfigState) -> bool:
    """确定性判定是否启用 Specialist；只看配置、场景枚举与候选是否存在。"""
    if not get_settings().agent.multi_agent_enabled:
        return False
    try:
        requirements = PCRequirements.model_validate(state.get("requirements") or {})
    except ValueError:
        # 需求不合法时流程本身会失败或澄清，这里不额外消耗模型调用
        return False
    if requirements.scenario not in COMPLEX_SCENARIOS:
        return False
    candidate_sets = as_mapping(state.get("candidate_sets"))
    return any(as_list(candidate_sets.get(category.value)) for category in REQUIRED_CATEGORIES)


def _candidate_digest(candidate_sets: dict[str, Any]) -> str:
    """只给决策字段的候选摘要；要求模型只能引用这里出现的 hardware_id。

    与 Architect 共用 `candidate_summary_line`：插槽、内存代际、限长等字段
    如果缺失，平台分析师只能靠型号名猜兼容性，报告价值会大打折扣。
    """
    lines = ["## 候选摘要（只能引用下列 hardware_id，禁止编造型号或价格）"]
    for category in REQUIRED_CATEGORIES:
        summaries = as_list(candidate_sets.get(category.value))[:MAX_CANDIDATES_PER_CATEGORY]
        if not summaries:
            continue
        lines.append(f"### {category.value}")
        lines.extend(candidate_summary_line(as_mapping(raw)) for raw in summaries)
    return "\n".join(lines) if len(lines) > 1 else ""


def _fit_to_line_budget(text: str, budget: int) -> str:
    """按整行裁剪候选摘要：切在半条记录里会让模型误读价格与规格。"""
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    cut = text.rfind("\n", 0, budget)
    if cut <= 0:
        return ""
    return text[:cut] + "\n（候选摘要因长度上限截断）"


def _specialist_context(state: PCConfigState) -> str:
    """紧凑上下文：需求 JSON + 策略 JSON + 候选摘要，不复制完整工具输出。

    先放需求与策略，再用剩余预算装候选摘要，并按整行截断，
    确保截断不会落在某条候选的中间、制造虚假的「价格缺失」。
    """
    head = "\n\n".join(
        [
            "## 结构化需求\n"
            + json.dumps(as_mapping(state.get("requirements")), ensure_ascii=False),
            "## 配置策略\n"
            + json.dumps(as_mapping(state.get("build_strategy")), ensure_ascii=False),
        ]
    )
    budget = SPECIALIST_MAX_CONTEXT_CHARS - len(head) - len("\n\n")
    if budget <= 0:
        return head[:SPECIALIST_MAX_CONTEXT_CHARS]
    digest = _fit_to_line_budget(
        _candidate_digest(as_mapping(state.get("candidate_sets"))), budget
    )
    return f"{head}\n\n{digest}" if digest else head


async def specialist_panel(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    prompts: dict[SpecialistRole, str],
) -> dict[str, Any]:
    """并行调用各角色；单角色失败只跳过该角色，全部失败返回空更新。"""
    if not should_run_specialists(state):
        return {}

    context = _specialist_context(state)
    roles = list(prompts)
    results = await asyncio.gather(
        *[
            invoke_model_structured(
                model,
                [SystemMessage(content=prompts[role]), HumanMessage(content=context)],
                schema=SpecialistReport,
                config=config,
                agent_id=agent_id,
                purpose=f"specialist_{role.value.lower()}",
            )
            for role in roles
        ],
        return_exceptions=True,
    )

    reports: dict[str, dict[str, Any]] = {}
    used_roles: list[str] = []
    for role, result in zip(roles, results, strict=True):
        if not isinstance(result, SpecialistReport):
            # 只记录角色与异常类型：异常文本可能含上游地址或模型输出片段
            logger.warning(
                "pc.specialist_failed",
                role=role.value,
                error_type=(
                    type(result).__name__
                    if isinstance(result, BaseException)
                    else "empty_result"
                ),
            )
            continue
        reports[role.value] = result.model_dump(mode="json")
        used_roles.append(role.value)

    if not reports:
        return {}
    logger.info("pc.specialist_reports", roles=used_roles, count=len(used_roles))
    return {"specialist_reports": reports, "specialist_roles_used": used_roles}


def _critic_context(state: PCConfigState) -> str:
    """只放评审必需信息：需求、策略、最终八类组件、质量评审与 Specialist 报告。"""
    components: list[dict[str, Any]] = []
    for raw in as_list(as_mapping(state.get("build_result")).get("components")):
        component = as_mapping(raw)
        components.append(
            {
                "category": as_text(component.get("category")),
                "name": as_text(component.get("modelName")),
                "hardwareId": as_text(component.get("hardwareId")),
                "priceFen": component.get("priceFen"),
            }
        )
    sections = [
        "## 结构化需求\n"
        + json.dumps(as_mapping(state.get("requirements")), ensure_ascii=False),
        "## 配置策略\n"
        + json.dumps(as_mapping(state.get("build_strategy")), ensure_ascii=False),
        "## 最终方案组件\n" + json.dumps(components, ensure_ascii=False),
        "## 质量评审\n"
        + json.dumps(as_mapping(state.get("quality_review")), ensure_ascii=False),
    ]
    specialist_reports = as_mapping(state.get("specialist_reports"))
    if specialist_reports:
        sections.append(
            "## Specialist 报告\n" + json.dumps(specialist_reports, ensure_ascii=False)
        )
    text = "\n\n".join(section for section in sections if section)
    return text[:CRITIC_MAX_CONTEXT_CHARS]


# 只有影响可用性的问题才值得再花一次修正调用；LOW 问题只做披露，
# 避免为了「可以更好」再消耗一次模型调用与交付时延。
_CRITIC_ACTIONABLE_SEVERITIES = frozenset({"HIGH", "MEDIUM"})


def _requires_revision(report: CriticReport) -> bool:
    """REVISE + HIGH/MEDIUM 才触发受限修正；其余结论保持只评审。"""
    if report.decision is not CriticDecision.REVISE:
        return False
    return any(
        issue.severity in _CRITIC_ACTIONABLE_SEVERITIES for issue in report.issues
    )


async def critic_review(
    state: PCConfigState,
    config: RunnableConfig,
    *,
    model: BaseChatModel | None,
    agent_id: str,
    critic_prompt: str,
) -> dict[str, Any]:
    """独立评审成功方案；结果默认只写状态，REVISE + 高严重度问题才请求修正。"""
    settings = get_settings().agent
    if not (settings.multi_agent_enabled and settings.critic_enabled):
        return {}
    if as_text(state.get("workflow_status")) != STATUS_SUCCESS:
        return {}
    if not as_mapping(state.get("build_result")):
        return {}
    # 已发生修正时本轮不再评审：Critic 只评审「首提案」，
    # 否则复杂场景会突破 ADR 0030 的 9 次调用上限
    if as_int(state.get("architect_repair_count")) > 0:
        logger.info("pc.critic_skipped", reason="repair_budget_used")
        return {}

    report = await invoke_model_structured(
        model,
        [
            SystemMessage(content=critic_prompt),
            HumanMessage(content=_critic_context(state)),
        ],
        schema=CriticReport,
        config=config,
        agent_id=agent_id,
        purpose="critic_review",
    )
    if not isinstance(report, CriticReport):
        logger.warning("pc.critic_failed", error_type="empty_result")
        return {}
    requires_revision = _requires_revision(report)
    logger.info(
        "pc.critic_reviewed",
        decision=report.decision.value,
        requires_revision=requires_revision,
    )
    return {
        "critic_report": report.model_dump(mode="json"),
        # 显式写回 False：避免上一轮遗留标记让本轮误触发修正
        "critic_revision_requested": requires_revision,
    }
