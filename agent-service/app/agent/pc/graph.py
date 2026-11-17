"""唯一的生产图：PC 配置推荐确定性流水线。

节点顺序固定，禁止在此之外再保留通用 ReAct 分支。
"""

from __future__ import annotations

from functools import partial
from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.checkpointer import get_checkpointer
from app.agent.pc.hitl import clarification_gate, compatibility_gate
from app.agent.pc.node_tracing import trace_node
from app.agent.pc.nodes import (
    build_architect,
    build_strategist,
    candidate_retriever,
    requirement_parser,
    requirement_validator,
    response_generator,
)
from app.agent.pc.quality import quality_review
from app.agent.pc.renderer import as_int, as_mapping, overall_compatibility
from app.agent.pc.schemas import SpecialistRole
from app.agent.pc.specialists import critic_review, should_run_specialists, specialist_panel
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import (
    STATUS_CLARIFICATION,
    STATUS_INVALID,
    STATUS_NO_CANDIDATES,
    STATUS_RETRY,
    STATUS_SUCCESS,
    STATUS_UPSTREAM_ERROR,
)
from app.agent.profiles import AgentProfile
from app.agent.prompts import load_pc_prompt, load_prompt
from app.core.config import get_settings

PARSER_PROMPT_NAME = "requirement-parser"
GENERATOR_PROMPT_NAME = "response-generator"
ARCHITECT_PROMPT_NAME = "build-architect"
STRATEGIST_PROMPT_NAME = "build-strategist"
PERFORMANCE_SPECIALIST_PROMPT_NAME = "performance-specialist"
PLATFORM_SPECIALIST_PROMPT_NAME = "platform-specialist"
CRITIC_PROMPT_NAME = "critic"

NODE_REQUIREMENT_PARSER = "requirement_parser"
NODE_REQUIREMENT_VALIDATOR = "requirement_validator"
NODE_CLARIFICATION_GATE = "clarification_gate"
NODE_BUILD_STRATEGIST = "build_strategist"
NODE_CANDIDATE_RETRIEVER = "candidate_retriever"
NODE_SPECIALIST_PANEL = "specialist_panel"
NODE_BUILD_ARCHITECT = "build_architect"
NODE_QUALITY_REVIEW = "quality_review"
NODE_CRITIC_REVIEW = "critic_review"
NODE_COMPATIBILITY_GATE = "compatibility_gate"
NODE_RESPONSE_GENERATOR = "response_generator"

PC_GRAPH_NODES: tuple[str, ...] = (
    NODE_REQUIREMENT_PARSER,
    NODE_REQUIREMENT_VALIDATOR,
    NODE_CLARIFICATION_GATE,
    NODE_BUILD_STRATEGIST,
    NODE_CANDIDATE_RETRIEVER,
    NODE_SPECIALIST_PANEL,
    NODE_BUILD_ARCHITECT,
    NODE_QUALITY_REVIEW,
    NODE_CRITIC_REVIEW,
    NODE_COMPATIBILITY_GATE,
    NODE_RESPONSE_GENERATOR,
)


def _route_after_validation(state: dict[str, Any]) -> str:
    status = state.get("workflow_status")
    # 参数非法直接给失败文案；仅「缺槽位」进入 HITL 门控
    if status == STATUS_INVALID:
        return NODE_RESPONSE_GENERATOR
    if status == STATUS_CLARIFICATION:
        return NODE_CLARIFICATION_GATE
    # 检索前先由 Strategist 定策略，再按类别检索候选
    return NODE_BUILD_STRATEGIST


def _route_after_clarification_gate(state: dict[str, Any]) -> str:
    # 未启用 HITL 时门控原样放行，沿用原有澄清回复
    if state.get("workflow_status") == STATUS_CLARIFICATION:
        return NODE_RESPONSE_GENERATOR
    # 已恢复：用户补充信息已并入最后一条用户消息，重新解析
    return NODE_REQUIREMENT_PARSER


def _route_after_retrieval(state: dict[str, Any]) -> str:
    if state.get("workflow_status") in {STATUS_NO_CANDIDATES, STATUS_UPSTREAM_ERROR}:
        return NODE_RESPONSE_GENERATOR
    # 只依据枚举状态分流，不解析任何自然语言
    return NODE_BUILD_ARCHITECT


def _route_after_architect(state: dict[str, Any]) -> str:
    if state.get("workflow_status") == STATUS_SUCCESS:
        return NODE_QUALITY_REVIEW
    return NODE_RESPONSE_GENERATOR


def _route_after_quality_review(state: dict[str, Any]) -> str:
    status = state.get("workflow_status")
    if status == STATUS_RETRY:
        return NODE_BUILD_ARCHITECT
    # 方案已生成但兼容性未验证：HITL 开启时先让用户确认
    if status == STATUS_SUCCESS and overall_compatibility(
        as_mapping(state.get("compatibility_report"))
    ) == "UNKNOWN":
        return NODE_COMPATIBILITY_GATE
    return NODE_RESPONSE_GENERATOR


def build_pc_graph(
    *,
    model: BaseChatModel | None,
    profile: AgentProfile,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """组装 PC 配置流水线：确定性主链 + 两个 HITL 门控 + 可选多 Agent 节点。

    Specialist / Critic 节点始终注册，但默认配置下路由直接绕过，行为与单 Agent 一致。
    """
    system_prompt = load_prompt(profile.system_prompt)
    parser_prompt = load_prompt(PARSER_PROMPT_NAME)
    generator_prompt = load_prompt(GENERATOR_PROMPT_NAME)
    architect_prompt = load_pc_prompt(ARCHITECT_PROMPT_NAME)
    strategist_prompt = load_pc_prompt(STRATEGIST_PROMPT_NAME)
    specialist_prompts = {
        SpecialistRole.PERFORMANCE: load_pc_prompt(PERFORMANCE_SPECIALIST_PROMPT_NAME),
        SpecialistRole.PLATFORM: load_pc_prompt(PLATFORM_SPECIALIST_PROMPT_NAME),
    }
    critic_prompt = load_pc_prompt(CRITIC_PROMPT_NAME)
    # 配置在构图时读取一次：路由函数需要它，但不应在每次状态流转时重复解析设置
    agent_settings = get_settings().agent

    def route_after_retrieval(state: PCConfigState) -> str:
        """检索成功后按配置与确定性场景判定是否进入并行分析。"""
        if state.get("workflow_status") in {STATUS_NO_CANDIDATES, STATUS_UPSTREAM_ERROR}:
            return NODE_RESPONSE_GENERATOR
        if agent_settings.multi_agent_enabled and should_run_specialists(state):
            return NODE_SPECIALIST_PANEL
        return NODE_BUILD_ARCHITECT

    def route_after_review(state: PCConfigState, *, allow_critic: bool) -> str:
        """质量评审/Critic 之后共用的路由；`allow_critic` 防止 Critic 自循环。

        兼容性 UNKNOWN 优先于 Critic：方案未验证时先走 HITL 门控，
        与单 Agent 时代的 `_route_after_quality_review` 语义保持一致。
        """
        status = state.get("workflow_status")
        if status == STATUS_RETRY:
            return NODE_BUILD_ARCHITECT
        if status == STATUS_SUCCESS and overall_compatibility(
            as_mapping(state.get("compatibility_report"))
        ) == "UNKNOWN":
            return NODE_COMPATIBILITY_GATE
        if (
            allow_critic
            and status == STATUS_SUCCESS
            and agent_settings.multi_agent_enabled
            and agent_settings.critic_enabled
            # 修正已占用最后 1 次预算，本轮不再评审，保证复杂场景 ≤7 次调用
            and as_int(state.get("architect_repair_count")) == 0
        ):
            return NODE_CRITIC_REVIEW
        return NODE_RESPONSE_GENERATOR

    graph: StateGraph = StateGraph(PCConfigState)
    graph.add_node(
        NODE_REQUIREMENT_PARSER,
        trace_node(
            NODE_REQUIREMENT_PARSER,
            partial(
                requirement_parser,
                model=model,
                agent_id=profile.id,
                parser_prompt=parser_prompt,
            ),
            agent_id=profile.id,
        ),
    )
    graph.add_node(
        NODE_REQUIREMENT_VALIDATOR,
        trace_node(NODE_REQUIREMENT_VALIDATOR, requirement_validator, agent_id=profile.id),
    )
    graph.add_node(
        NODE_CLARIFICATION_GATE,
        trace_node(NODE_CLARIFICATION_GATE, clarification_gate, agent_id=profile.id),
    )
    graph.add_node(
        NODE_BUILD_STRATEGIST,
        trace_node(
            NODE_BUILD_STRATEGIST,
            partial(
                build_strategist,
                model=model,
                agent_id=profile.id,
                strategist_prompt=strategist_prompt,
            ),
            agent_id=profile.id,
        ),
    )
    graph.add_node(
        NODE_CANDIDATE_RETRIEVER,
        trace_node(NODE_CANDIDATE_RETRIEVER, candidate_retriever, agent_id=profile.id),
    )
    graph.add_node(
        NODE_SPECIALIST_PANEL,
        trace_node(
            NODE_SPECIALIST_PANEL,
            partial(
                specialist_panel,
                model=model,
                agent_id=profile.id,
                prompts=specialist_prompts,
            ),
            agent_id=profile.id,
        ),
    )
    graph.add_node(
        NODE_BUILD_ARCHITECT,
        trace_node(
            NODE_BUILD_ARCHITECT,
            partial(
                build_architect,
                model=model,
                agent_id=profile.id,
                architect_prompt=architect_prompt,
            ),
            agent_id=profile.id,
        ),
    )
    graph.add_node(
        NODE_QUALITY_REVIEW,
        trace_node(NODE_QUALITY_REVIEW, quality_review, agent_id=profile.id),
    )
    graph.add_node(
        NODE_CRITIC_REVIEW,
        trace_node(
            NODE_CRITIC_REVIEW,
            partial(
                critic_review,
                model=model,
                agent_id=profile.id,
                critic_prompt=critic_prompt,
            ),
            agent_id=profile.id,
        ),
    )
    graph.add_node(
        NODE_COMPATIBILITY_GATE,
        trace_node(NODE_COMPATIBILITY_GATE, compatibility_gate, agent_id=profile.id),
    )
    graph.add_node(
        NODE_RESPONSE_GENERATOR,
        trace_node(
            NODE_RESPONSE_GENERATOR,
            partial(
                response_generator,
                model=model,
                agent_id=profile.id,
                system_prompt=system_prompt,
                generator_prompt=generator_prompt,
            ),
            agent_id=profile.id,
        ),
    )

    graph.add_edge(START, NODE_REQUIREMENT_PARSER)
    graph.add_edge(NODE_REQUIREMENT_PARSER, NODE_REQUIREMENT_VALIDATOR)
    graph.add_conditional_edges(
        NODE_REQUIREMENT_VALIDATOR,
        _route_after_validation,
        {
            NODE_CLARIFICATION_GATE: NODE_CLARIFICATION_GATE,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
            NODE_BUILD_STRATEGIST: NODE_BUILD_STRATEGIST,
        },
    )
    graph.add_edge(NODE_BUILD_STRATEGIST, NODE_CANDIDATE_RETRIEVER)
    graph.add_conditional_edges(
        NODE_CLARIFICATION_GATE,
        _route_after_clarification_gate,
        {
            NODE_REQUIREMENT_PARSER: NODE_REQUIREMENT_PARSER,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_conditional_edges(
        NODE_CANDIDATE_RETRIEVER,
        route_after_retrieval,
        {
            NODE_SPECIALIST_PANEL: NODE_SPECIALIST_PANEL,
            NODE_BUILD_ARCHITECT: NODE_BUILD_ARCHITECT,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    # Specialist 失败返回空更新，但仍必须直连 Architect，不改变主链顺序
    graph.add_edge(NODE_SPECIALIST_PANEL, NODE_BUILD_ARCHITECT)
    graph.add_conditional_edges(
        NODE_BUILD_ARCHITECT,
        _route_after_architect,
        {
            NODE_QUALITY_REVIEW: NODE_QUALITY_REVIEW,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_conditional_edges(
        NODE_QUALITY_REVIEW,
        partial(route_after_review, allow_critic=True),
        {
            NODE_BUILD_ARCHITECT: NODE_BUILD_ARCHITECT,
            NODE_CRITIC_REVIEW: NODE_CRITIC_REVIEW,
            NODE_COMPATIBILITY_GATE: NODE_COMPATIBILITY_GATE,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    # Critic 只评审：复用同一路由但关闭 Critic 分支，避免自循环
    graph.add_conditional_edges(
        NODE_CRITIC_REVIEW,
        partial(route_after_review, allow_critic=False),
        {
            NODE_BUILD_ARCHITECT: NODE_BUILD_ARCHITECT,
            NODE_COMPATIBILITY_GATE: NODE_COMPATIBILITY_GATE,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_edge(NODE_COMPATIBILITY_GATE, NODE_RESPONSE_GENERATOR)
    graph.add_edge(NODE_RESPONSE_GENERATOR, END)

    return graph.compile(checkpointer=checkpointer or get_checkpointer())
