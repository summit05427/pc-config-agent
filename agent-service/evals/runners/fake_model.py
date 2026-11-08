"""假模型模式：零 API 费用，校验用例与 Agent 配置是否对得上。

能验证：Profile 是否存在、`tool_called` 指向的工具是否已注册且被该 Profile 绑定、
PC 图能否按该 Profile 编译、六个节点是否齐全。
不能验证：模型是否真的按用例回答——内容断言一律记为 `skipped`，需要 `--real`。
"""

from dataclasses import dataclass
from time import perf_counter
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from app.agent.pc.graph import PC_GRAPH_NODES, build_pc_graph
from app.agent.profiles import (
    AgentProfile,
    ProfileNotFoundError,
    resolve_profile,
    resolve_profile_tools,
)
from app.agent.registry import list_tool_specs
from app.core.config import get_settings
from evals.report import (
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    CaseResult,
    CheckResult,
)
from evals.schema import EvalCase

# 内容断言在假模型模式下没有回答可供比对，如实标记为未校验
_CONTENT_SKIP_REASON = "假模型不产生回答，内容断言需用 --real 校验"


class _StructuralModel:
    """假模型替身：只为让图能编译通过，永远不会被真正调用。"""

    async def ainvoke(self, messages: object, config: object = None) -> AIMessage:
        raise NotImplementedError(_CONTENT_SKIP_REASON)


@dataclass(frozen=True)
class _PreparedProfile:
    """一个 Profile 编译出来的结构快照。"""

    profile: AgentProfile
    tool_names: tuple[str, ...]
    graph_nodes: tuple[str, ...]


@dataclass(frozen=True)
class _Preparation:
    """成功时带快照，失败时带可读原因；两种情况都缓存，避免逐条用例重复编译。"""

    prepared: _PreparedProfile | None = None
    error: str | None = None


_PREPARATIONS: dict[str, _Preparation] = {}


def _compile(profile: AgentProfile) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """按 Profile 编译图，返回 (绑定工具名, 节点名)。

    注入假模型与内存 checkpointer：编译不触发任何模型调用，也不会连数据库。
    """
    tools = resolve_profile_tools(profile)
    graph: CompiledStateGraph = build_pc_graph(
        model=cast("BaseChatModel", _StructuralModel()),
        checkpointer=MemorySaver(),
        profile=profile,
    )
    return (
        tuple(tool.name for tool in tools),
        tuple(graph.get_graph().nodes),
    )


def _prepare(agent_id: str) -> _Preparation:
    cached = _PREPARATIONS.get(agent_id)
    if cached is not None:
        return cached

    try:
        profile = resolve_profile(agent_id)
        tool_names, graph_nodes = _compile(profile)
        preparation = _Preparation(_PreparedProfile(profile, tool_names, graph_nodes))
    except ProfileNotFoundError:
        preparation = _Preparation(
            error=f"Profile 不存在：{agent_id}"
            "（需在 AGENT__PROFILES_DIR 下新增同名 YAML，默认 app/agents/）"
        )
    except Exception as exc:  # 图编译失败属于配置错误，转成用例失败而不是中断整轮评测
        preparation = _Preparation(error=f"{type(exc).__name__}: {exc}")

    _PREPARATIONS[agent_id] = preparation
    return preparation


def _check_tool(tool_name: str, prepared: _PreparedProfile) -> CheckResult:
    """期望调用的工具必须既已注册，又被当前 Profile 绑定。"""
    registered = {spec.tool.name for spec in list_tool_specs()}
    if tool_name not in registered:
        return CheckResult(
            "tool_called",
            STATUS_FAILED,
            f"工具未注册：{tool_name}（已注册：{', '.join(sorted(registered)) or '无'}）",
        )

    if tool_name not in prepared.tool_names:
        bound = ", ".join(prepared.tool_names) or "无"
        return CheckResult(
            "tool_called",
            STATUS_FAILED,
            f"Profile {prepared.profile.id} 未绑定工具 {tool_name}（已绑定：{bound}）",
        )
    return CheckResult("tool_called", STATUS_PASSED, tool_name)


def _check_graph(prepared: _PreparedProfile) -> CheckResult:
    """六个节点缺一不可，避免悄悄退回多图或残缺图。"""
    missing = [node for node in PC_GRAPH_NODES if node not in prepared.graph_nodes]
    if missing:
        return CheckResult(
            "graph",
            STATUS_FAILED,
            f"缺少节点：{', '.join(missing)}；实际节点：{', '.join(prepared.graph_nodes)}",
        )
    return CheckResult("graph", STATUS_PASSED, f"节点：{', '.join(PC_GRAPH_NODES)}")


def _skipped_content_checks(case: EvalCase) -> list[CheckResult]:
    checks = []
    if case.expect.must_contain:
        checks.append(CheckResult("must_contain", STATUS_SKIPPED, _CONTENT_SKIP_REASON))
    if case.expect.must_not_contain:
        checks.append(CheckResult("must_not_contain", STATUS_SKIPPED, _CONTENT_SKIP_REASON))
    return checks


def run_case(case: EvalCase) -> CaseResult:
    started_at = perf_counter()
    agent_id = case.agent_id or get_settings().agent.default_profile
    preparation = _prepare(agent_id)
    latency_ms = int((perf_counter() - started_at) * 1000)

    if preparation.prepared is None:
        return CaseResult(
            case_id=case.id,
            agent_id=agent_id,
            checks=[
                CheckResult(
                    "profile",
                    STATUS_FAILED,
                    preparation.error or "Profile 不可用",
                )
            ],
            latency_ms=latency_ms,
        )

    prepared = preparation.prepared
    checks = [
        CheckResult(
            "profile",
            STATUS_PASSED,
            f"system_prompt={prepared.profile.system_prompt}",
        ),
        _check_graph(prepared),
    ]
    if case.expect.tool_called is not None:
        checks.append(_check_tool(case.expect.tool_called, prepared))
    checks.extend(_skipped_content_checks(case))

    return CaseResult(
        case_id=case.id,
        agent_id=agent_id,
        checks=checks,
        latency_ms=latency_ms,
    )


def run_cases(cases: list[EvalCase]) -> list[CaseResult]:
    """顺序执行；Profile 级结果在本次运行内复用。"""
    _PREPARATIONS.clear()
    return [run_case(case) for case in cases]
