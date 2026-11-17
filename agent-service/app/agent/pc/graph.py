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
from app.agent.pc.renderer import as_mapping, overall_compatibility
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

PARSER_PROMPT_NAME = "requirement-parser"
GENERATOR_PROMPT_NAME = "response-generator"
ARCHITECT_PROMPT_NAME = "build-architect"
STRATEGIST_PROMPT_NAME = "build-strategist"

NODE_REQUIREMENT_PARSER = "requirement_parser"
NODE_REQUIREMENT_VALIDATOR = "requirement_validator"
NODE_CLARIFICATION_GATE = "clarification_gate"
NODE_BUILD_STRATEGIST = "build_strategist"
NODE_CANDIDATE_RETRIEVER = "candidate_retriever"
NODE_BUILD_ARCHITECT = "build_architect"
NODE_QUALITY_REVIEW = "quality_review"
NODE_COMPATIBILITY_GATE = "compatibility_gate"
NODE_RESPONSE_GENERATOR = "response_generator"

PC_GRAPH_NODES: tuple[str, ...] = (
    NODE_REQUIREMENT_PARSER,
    NODE_REQUIREMENT_VALIDATOR,
    NODE_CLARIFICATION_GATE,
    NODE_BUILD_STRATEGIST,
    NODE_CANDIDATE_RETRIEVER,
    NODE_BUILD_ARCHITECT,
    NODE_QUALITY_REVIEW,
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
    """组装 PC 配置流水线：七个业务节点 + 两个 HITL 门控；模型可为 None。"""
    system_prompt = load_prompt(profile.system_prompt)
    parser_prompt = load_prompt(PARSER_PROMPT_NAME)
    generator_prompt = load_prompt(GENERATOR_PROMPT_NAME)
    architect_prompt = load_pc_prompt(ARCHITECT_PROMPT_NAME)
    strategist_prompt = load_pc_prompt(STRATEGIST_PROMPT_NAME)

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
        _route_after_retrieval,
        {
            NODE_BUILD_ARCHITECT: NODE_BUILD_ARCHITECT,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
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
        _route_after_quality_review,
        {
            NODE_BUILD_ARCHITECT: NODE_BUILD_ARCHITECT,
            NODE_COMPATIBILITY_GATE: NODE_COMPATIBILITY_GATE,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_edge(NODE_COMPATIBILITY_GATE, NODE_RESPONSE_GENERATOR)
    graph.add_edge(NODE_RESPONSE_GENERATOR, END)

    return graph.compile(checkpointer=checkpointer or get_checkpointer())
