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
from app.agent.pc.nodes import (
    build_solver,
    build_validator,
    candidate_retriever,
    requirement_parser,
    requirement_validator,
    response_generator,
)
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import (
    STATUS_CLARIFICATION,
    STATUS_INVALID,
    STATUS_NO_CANDIDATES,
    STATUS_RETRY,
    STATUS_SOLVED,
    STATUS_UPSTREAM_ERROR,
)
from app.agent.profiles import AgentProfile
from app.agent.prompts import load_prompt

PARSER_PROMPT_NAME = "requirement-parser"
GENERATOR_PROMPT_NAME = "response-generator"

NODE_REQUIREMENT_PARSER = "requirement_parser"
NODE_REQUIREMENT_VALIDATOR = "requirement_validator"
NODE_CANDIDATE_RETRIEVER = "candidate_retriever"
NODE_BUILD_SOLVER = "build_solver"
NODE_BUILD_VALIDATOR = "build_validator"
NODE_RESPONSE_GENERATOR = "response_generator"

PC_GRAPH_NODES: tuple[str, ...] = (
    NODE_REQUIREMENT_PARSER,
    NODE_REQUIREMENT_VALIDATOR,
    NODE_CANDIDATE_RETRIEVER,
    NODE_BUILD_SOLVER,
    NODE_BUILD_VALIDATOR,
    NODE_RESPONSE_GENERATOR,
)


def _route_after_validation(state: dict[str, Any]) -> str:
    status = state.get("workflow_status")
    if status in {STATUS_CLARIFICATION, STATUS_INVALID}:
        return NODE_RESPONSE_GENERATOR
    return NODE_CANDIDATE_RETRIEVER


def _route_after_retrieval(state: dict[str, Any]) -> str:
    if state.get("workflow_status") in {STATUS_NO_CANDIDATES, STATUS_UPSTREAM_ERROR}:
        return NODE_RESPONSE_GENERATOR
    return NODE_BUILD_SOLVER


def _route_after_solve(state: dict[str, Any]) -> str:
    if state.get("workflow_status") == STATUS_SOLVED:
        return NODE_BUILD_VALIDATOR
    return NODE_RESPONSE_GENERATOR


def _route_after_build_validation(state: dict[str, Any]) -> str:
    if state.get("workflow_status") == STATUS_RETRY:
        return NODE_BUILD_SOLVER
    return NODE_RESPONSE_GENERATOR


def build_pc_graph(
    *,
    model: BaseChatModel | None,
    profile: AgentProfile,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """组装六节点 PC 图；模型可为 None，此时全部走确定性兜底。"""
    system_prompt = load_prompt(profile.system_prompt)
    parser_prompt = load_prompt(PARSER_PROMPT_NAME)
    generator_prompt = load_prompt(GENERATOR_PROMPT_NAME)

    graph: StateGraph = StateGraph(PCConfigState)
    graph.add_node(
        NODE_REQUIREMENT_PARSER,
        partial(
            requirement_parser,
            model=model,
            agent_id=profile.id,
            parser_prompt=parser_prompt,
        ),
    )
    graph.add_node(NODE_REQUIREMENT_VALIDATOR, requirement_validator)
    graph.add_node(NODE_CANDIDATE_RETRIEVER, candidate_retriever)
    graph.add_node(NODE_BUILD_SOLVER, build_solver)
    graph.add_node(NODE_BUILD_VALIDATOR, build_validator)
    graph.add_node(
        NODE_RESPONSE_GENERATOR,
        partial(
            response_generator,
            model=model,
            agent_id=profile.id,
            system_prompt=system_prompt,
            generator_prompt=generator_prompt,
        ),
    )

    graph.add_edge(START, NODE_REQUIREMENT_PARSER)
    graph.add_edge(NODE_REQUIREMENT_PARSER, NODE_REQUIREMENT_VALIDATOR)
    graph.add_conditional_edges(
        NODE_REQUIREMENT_VALIDATOR,
        _route_after_validation,
        {
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
            NODE_CANDIDATE_RETRIEVER: NODE_CANDIDATE_RETRIEVER,
        },
    )
    graph.add_conditional_edges(
        NODE_CANDIDATE_RETRIEVER,
        _route_after_retrieval,
        {
            NODE_BUILD_SOLVER: NODE_BUILD_SOLVER,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_conditional_edges(
        NODE_BUILD_SOLVER,
        _route_after_solve,
        {
            NODE_BUILD_VALIDATOR: NODE_BUILD_VALIDATOR,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_conditional_edges(
        NODE_BUILD_VALIDATOR,
        _route_after_build_validation,
        {
            NODE_BUILD_SOLVER: NODE_BUILD_SOLVER,
            NODE_RESPONSE_GENERATOR: NODE_RESPONSE_GENERATOR,
        },
    )
    graph.add_edge(NODE_RESPONSE_GENERATOR, END)

    return graph.compile(checkpointer=checkpointer or get_checkpointer())
