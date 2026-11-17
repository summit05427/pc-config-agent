"""HITL 门控测试：中断、恢复、终止与恢复请求校验。

图相关用例复用 test_agent_graph 的假工具与假模型，不访问 Java 服务或真实 LLM；
恢复校验只测纯函数，不建立 SSE 连接。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt
from pydantic import ValidationError
from test_agent_graph import (
    REQUIREMENT_JSON,
    PipelineModel,
    _build,
    _install_tools,
)

from app.agent.pc.graph import build_pc_graph
from app.agent.pc.hitl import build_compatibility_question
from app.agent.pc.status import STATUS_ABORTED, STATUS_CLARIFICATION, STATUS_SUCCESS
from app.agent.profiles import resolve_profile
from app.api.v1 import chat as chat_module
from app.core.config import AuthSettings, Settings, get_settings
from app.core.error_codes import (
    CODE_HITL_UNAVAILABLE,
    CODE_INTERRUPT_EXPIRED,
    CODE_INTERRUPT_MISMATCH,
    CODE_INTERRUPT_NOT_FOUND,
)
from app.core.exceptions import AppError, HitlResumeInvalidError
from app.services.turn import _interrupt_events

CLARIFY_REQUIREMENT_JSON = json.dumps(
    {
        "scenario": "BALANCED",
        "scenario_explicit": False,
        "needs_clarification": True,
        "missing_fields": ["budget_max_fen", "scenario"],
    }
)
# 第一轮故意缺预算与用途，触发澄清门控；恢复后模型返回完整需求


@pytest.fixture
def hitl_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启 HITL 并切到 postgres 配置；图仍用 MemorySaver，不连真实数据库。"""
    monkeypatch.setenv("HITL__ENABLED", "true")
    monkeypatch.setenv("STORAGE__BACKEND", "postgres")
    monkeypatch.setenv("STORAGE__POSTGRES_URL", "postgresql://u:p@localhost:5432/agent")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _graph(model: PipelineModel | None = None):
    return build_pc_graph(
        model=model,
        profile=resolve_profile("pc-config"),
        checkpointer=MemorySaver(),
    )


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


async def _start(agent: Any, text: str, thread_id: str) -> None:
    await agent.ainvoke(
        {"messages": [HumanMessage(text)], "use_history": True},
        _config(thread_id),
    )


def test_hitl_enabled_rejects_memory_backend(public_key_pem: str) -> None:
    with pytest.raises(ValidationError, match="HITL"):
        Settings(
            _env_file=None,
            auth=AuthSettings(jwt_public_key=public_key_pem),
            storage={"backend": "memory"},
            hitl={"enabled": True},
        )


async def test_clarification_without_hitl_keeps_original_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_tools(monkeypatch)
    agent = _graph()
    await _start(agent, "帮我配台电脑", "hitl-off")

    snapshot = await agent.aget_state(_config("hitl-off"))
    assert not snapshot.interrupts
    assert snapshot.values["workflow_status"] == STATUS_CLARIFICATION
    # 未开启 HITL 时仍由 response_generator 给出澄清文案
    assert "预算" in str(snapshot.values["messages"][-1].content)


async def test_clarification_interrupt_and_resume(
    monkeypatch: pytest.MonkeyPatch, hitl_on: None
) -> None:
    counters = _install_tools(
        monkeypatch,
        compose_payloads=[{"composed": True, "build": _build("PASS")}],
    )
    agent = _graph(
        PipelineModel(
            requirements=[CLARIFY_REQUIREMENT_JSON, REQUIREMENT_JSON],
        )
    )
    await _start(agent, "帮我配台电脑", "hitl-clarify")

    snapshot = await agent.aget_state(_config("hitl-clarify"))
    assert len(snapshot.interrupts) == 1
    payload = snapshot.interrupts[0].value
    assert payload["interaction_type"] == "clarify_requirements"
    assert payload["schema_version"] == "1"
    assert {field["name"] for field in payload["input_schema"]["fields"]} >= {
        "budget_yuan",
        "scenario",
    }
    assert "budget_max_fen" in payload["context"]["missing_slots"]
    # 提问已写入历史，断线后重新进会话也能看到
    questions = [
        message
        for message in snapshot.values["messages"]
        if isinstance(message, AIMessage) and "预算" in str(message.content)
    ]
    assert questions

    await agent.ainvoke(
        Command(
            resume={
                "message": "预算 8000 元，主要用来打游戏",
                "answer": {"budget_yuan": 8000, "scenario": "GAMING"},
            }
        ),
        _config("hitl-clarify"),
    )

    final = await agent.aget_state(_config("hitl-clarify"))
    assert final.values["workflow_status"] == STATUS_SUCCESS
    assert counters["compose"] == 1
    # 恢复后重新解析，用户补充信息并入同一条用户消息而不是新增一轮
    human_messages = [
        message
        for message in final.values["messages"]
        if isinstance(message, HumanMessage)
    ]
    assert len(human_messages) == 1
    assert "补充" in str(human_messages[0].content)
    assert not final.interrupts


async def test_clarification_resume_rejects_empty_answer(
    monkeypatch: pytest.MonkeyPatch, hitl_on: None
) -> None:
    _install_tools(monkeypatch)
    agent = _graph()
    await _start(agent, "帮我配台电脑", "hitl-empty")

    with pytest.raises(HitlResumeInvalidError):
        await agent.ainvoke(
            Command(resume={"message": "", "answer": {}}),
            _config("hitl-empty"),
        )


def test_compatibility_question_reports_passed_count() -> None:
    """未验证项存在时，提问要给出已通过条数与具体规则，而不是只说「未验证」。"""
    checks = [
        {"ruleId": f"rule_{index}", "ruleName": f"规则{index}", "status": "PASS"}
        for index in range(8)
    ]
    checks.append(
        {
            "ruleId": "cooler_case_height",
            "ruleName": "散热器高度不超过机箱限高",
            "status": "UNKNOWN",
        }
    )

    question = build_compatibility_question({"compatibility_report": {"checks": checks}})

    assert "8 项兼容性检查通过" in question
    assert "1 项因数据缺失无法确认" in question
    assert "散热器高度不超过机箱限高" in question


async def test_unknown_compatibility_interrupt_and_abort(
    monkeypatch: pytest.MonkeyPatch, hitl_on: None
) -> None:
    _install_tools(
        monkeypatch,
        compose_payloads=[{"composed": True, "build": _build("UNKNOWN")}],
    )
    agent = _graph(PipelineModel())
    await _start(agent, "预算一万元，打游戏", "hitl-compat")

    snapshot = await agent.aget_state(_config("hitl-compat"))
    assert len(snapshot.interrupts) == 1
    payload = snapshot.interrupts[0].value
    assert payload["interaction_type"] == "confirm_compatibility"
    assert payload["context"]["overall_status"] == "UNKNOWN"
    assert payload["context"]["unverified_rules"]

    await agent.ainvoke(
        Command(resume={"message": "终止", "answer": {"decision": "abort"}}),
        _config("hitl-compat"),
    )
    final = await agent.aget_state(_config("hitl-compat"))
    assert final.values["workflow_status"] == STATUS_ABORTED
    assert "终止本轮方案" in str(final.values["messages"][-1].content)


async def test_interrupt_survives_graph_rebuild(
    monkeypatch: pytest.MonkeyPatch, hitl_on: None
) -> None:
    """模拟 Agent 重启：新编译的图复用同一 checkpoint 存储仍能恢复中断。"""
    counters = _install_tools(
        monkeypatch,
        compose_payloads=[{"composed": True, "build": _build("PASS")}],
    )
    profile = resolve_profile("pc-config")
    saver = MemorySaver()
    thread_id = "hitl-restart"

    await _start(
        build_pc_graph(
            model=PipelineModel(requirements=[CLARIFY_REQUIREMENT_JSON]),
            profile=profile,
            checkpointer=saver,
        ),
        "帮我配台电脑",
        thread_id,
    )
    paused = await build_pc_graph(
        model=PipelineModel(requirements=[CLARIFY_REQUIREMENT_JSON]),
        profile=profile,
        checkpointer=saver,
    ).aget_state(_config(thread_id))
    assert len(paused.interrupts) == 1

    # 重新构图等价于新进程装配图：状态只来自 checkpoint，而非内存中的上一实例
    rebuilt = build_pc_graph(
        model=PipelineModel(), profile=profile, checkpointer=saver
    )
    await rebuilt.ainvoke(
        Command(
            resume={
                "message": "预算 8000 元，打游戏",
                "answer": {"budget_yuan": 8000, "scenario": "GAMING"},
            }
        ),
        _config(thread_id),
    )

    final = await rebuilt.aget_state(_config(thread_id))
    assert final.values["workflow_status"] == STATUS_SUCCESS
    assert counters["compose"] == 1
    assert not final.interrupts


class _FakeGraph:
    def __init__(self, snapshot: Any) -> None:
        self._snapshot = snapshot

    async def aget_state(self, config: Any) -> Any:
        return self._snapshot


def _settings(*, enabled: bool = True, backend: str = "postgres", ttl: int = 1800) -> Any:
    return SimpleNamespace(
        hitl=SimpleNamespace(enabled=enabled, interrupt_ttl_seconds=ttl),
        storage=SimpleNamespace(backend=backend),
    )


def _resume(interrupt_id: str = "int-1") -> chat_module.ChatResume:
    return chat_module.ChatResume(interrupt_id=interrupt_id, answer={"decision": "continue"})


def _snapshot(*, interrupt_id: str = "int-1", created_at: str | None = None) -> Any:
    return SimpleNamespace(
        interrupts=(SimpleNamespace(id=interrupt_id),),
        created_at=created_at or "2099-01-01T00:00:00+00:00",
    )


async def test_resume_rejected_when_hitl_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_module, "get_settings", lambda: _settings(enabled=False))
    with pytest.raises(AppError) as excinfo:
        await chat_module._validate_resume(_FakeGraph(_snapshot()), "thread", _resume())
    assert excinfo.value.code == CODE_HITL_UNAVAILABLE


async def test_resume_rejected_on_memory_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_module, "get_settings", lambda: _settings(backend="memory"))
    with pytest.raises(AppError) as excinfo:
        await chat_module._validate_resume(_FakeGraph(_snapshot()), "thread", _resume())
    assert excinfo.value.code == CODE_HITL_UNAVAILABLE


async def test_resume_rejected_without_pending_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_module, "get_settings", _settings)
    snapshot = SimpleNamespace(interrupts=(), created_at="2099-01-01T00:00:00+00:00")
    with pytest.raises(AppError) as excinfo:
        await chat_module._validate_resume(_FakeGraph(snapshot), "thread", _resume())
    assert excinfo.value.code == CODE_INTERRUPT_NOT_FOUND


async def test_resume_rejected_on_id_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_module, "get_settings", _settings)
    with pytest.raises(AppError) as excinfo:
        await chat_module._validate_resume(
            _FakeGraph(_snapshot(interrupt_id="other")), "thread", _resume("int-1")
        )
    assert excinfo.value.code == CODE_INTERRUPT_MISMATCH


async def test_resume_rejected_when_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_module, "get_settings", _settings)
    with pytest.raises(AppError) as excinfo:
        await chat_module._validate_resume(
            _FakeGraph(_snapshot(created_at="2020-01-01T00:00:00+00:00")),
            "thread",
            _resume(),
        )
    assert excinfo.value.code == CODE_INTERRUPT_EXPIRED


def test_interrupt_events_expose_public_payload_only() -> None:
    events = _interrupt_events(
        (
            Interrupt(
                value={
                    "interaction_type": "clarify_requirements",
                    "question": "请补充预算",
                    "input_schema": {"fields": []},
                    "context": {"missing_slots": ["budget_max_fen"]},
                },
                id="int-42",
            ),
        )
    )
    assert len(events) == 1
    assert events[0].type == "interrupt"
    # interrupt_id 以 LangGraph 为准
    assert events[0].data["interrupt_id"] == "int-42"
    assert events[0].data["question"] == "请补充预算"
