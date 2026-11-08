"""Agent 图测试：用脚本化假模型验证 ReAct 循环，不发起真实请求。

节点是异步函数，因此统一用 ainvoke（pytest 已配置 asyncio_mode=auto）。
"""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agent import graph as graph_module
from app.agent.graph import build_agent, clear_agent_cache, get_agent, get_agent_for_runtime
from app.agent.prompts import load_system_prompt
from app.agent.registry import get_default_tools
from app.services.model_resolver import ResolvedRuntime
from app.services.model_usage import STATUS_FAILURE, STATUS_SUCCESS


class ScriptedModel:
    """测试替身：按顺序返回预设消息，并提供一个空实现的 bind_tools。"""

    def __init__(self, responses: list[AIMessage]) -> None:
        self._responses = iter(responses)

    def bind_tools(self, tools: Any) -> "ScriptedModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        return next(self._responses)


def _tool_call_message() -> AIMessage:
    """构造一条"我要调用 get_current_time"的模型消息。"""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_current_time",
                "args": {"timezone": "Asia/Shanghai"},
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )


async def test_agent_returns_model_reply() -> None:
    """无工具调用时：直接回答并结束。"""
    agent = build_agent(ScriptedModel([AIMessage(content="你好，我是 Agent")]))
    config = {"configurable": {"thread_id": "single-turn"}}

    result = await agent.ainvoke({"messages": [HumanMessage("你好")]}, config)

    assert result["messages"][-1].content == "你好，我是 Agent"
    assert not any(isinstance(m, ToolMessage) for m in result["messages"])


async def test_agent_executes_tool_then_answers() -> None:
    """有工具调用时：走 tools 节点，拿到结果后再生成最终回答。"""
    agent = build_agent(ScriptedModel([_tool_call_message(), AIMessage(content="现在时间已获取")]))
    config = {"configurable": {"thread_id": "react-loop"}}

    result = await agent.ainvoke({"messages": [HumanMessage("现在几点？")]}, config)

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].name == "get_current_time"
    assert "20" in tool_messages[0].content  # 年份，避免依赖具体时间
    assert result["messages"][-1].content == "现在时间已获取"


async def test_agent_remembers_previous_turns() -> None:
    """同一 thread_id 下，历史消息应被追加而不是覆盖。"""
    agent = build_agent(
        ScriptedModel([AIMessage(content="第一轮回复"), AIMessage(content="第二轮回复")])
    )
    config = {"configurable": {"thread_id": "multi-turn"}}

    await agent.ainvoke({"messages": [HumanMessage("第一句")]}, config)
    result = await agent.ainvoke({"messages": [HumanMessage("第二句")]}, config)

    assert len(result["messages"]) == 4
    assert result["messages"][0].content == "第一句"
    assert result["messages"][-1].content == "第二轮回复"


async def test_different_threads_are_isolated() -> None:
    """不同 thread_id 之间不应共享历史。"""
    agent = build_agent(
        ScriptedModel([AIMessage(content="A 的回复"), AIMessage(content="B 的回复")])
    )

    await agent.ainvoke(
        {"messages": [HumanMessage("我是用户 A")]},
        {"configurable": {"thread_id": "user-a"}},
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage("我是用户 B")]},
        {"configurable": {"thread_id": "user-b"}},
    )

    assert len(result["messages"]) == 2
    assert result["messages"][0].content == "我是用户 B"


class RecordingModel:
    """记录每次实际收到的消息，用于验证上下文裁剪是否生效。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.received: list[list[Any]] = []

    def bind_tools(self, tools: Any) -> "RecordingModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        self.received.append(list(messages))
        return AIMessage(content=self.reply)


async def test_model_receives_trimmed_history() -> None:
    """历史超出预算时，模型只能看到裁剪后的消息，但状态仍保留完整历史。"""
    model = RecordingModel("收到")
    agent = build_agent(
        model=model,
        tools=[],
        checkpointer=MemorySaver(),
        context_max_tokens=30,
    )
    config = {"configurable": {"thread_id": "trim-history"}}

    await agent.ainvoke(
        {"messages": [HumanMessage("旧" * 200), AIMessage("旧回复")]},
        config,
    )
    model.received.clear()
    result = await agent.ainvoke({"messages": [HumanMessage("新问题")]}, config)

    assert len(model.received[-1]) < 4
    assert model.received[-1][-1].content == "新问题"
    # 裁剪只影响传给模型的内容，持久化状态不应丢消息
    assert len(result["messages"]) == 5


async def test_use_history_false_hides_previous_turns_from_model() -> None:
    """关闭历史时模型只看本轮，但状态仍保留完整历史供落库与后续轮次使用。"""
    model = RecordingModel("收到")
    agent = build_agent(
        model=model,
        tools=[],
        checkpointer=MemorySaver(),
        context_max_tokens=1000,
    )
    config = {"configurable": {"thread_id": "history-off"}}

    await agent.ainvoke(
        {"messages": [HumanMessage("第一句")], "use_history": True}, config
    )
    model.received.clear()
    result = await agent.ainvoke(
        {"messages": [HumanMessage("第二句")], "use_history": False}, config
    )

    # 索引 0 是系统提示词；其后只应出现本轮用户消息
    assert [message.content for message in model.received[-1][1:]] == ["第二句"]
    # 持久化状态不裁剪：两轮共 4 条消息
    assert len(result["messages"]) == 4


async def test_preference_prompt_is_appended_to_system_prompt() -> None:
    """偏好片段追加在基础提示词之后，且不影响本轮消息顺序。"""
    model = RecordingModel("收到")
    agent = build_agent(
        model=model,
        tools=[],
        checkpointer=MemorySaver(),
        context_max_tokens=1000,
    )
    config = {"configurable": {"thread_id": "preference-prompt"}}
    preference_prompt = "## 用户偏好\n- 请使用英文回答。"

    await agent.ainvoke(
        {
            "messages": [HumanMessage("你好")],
            "preference_prompt": preference_prompt,
            "use_history": True,
        },
        config,
    )

    system = model.received[-1][0]
    assert isinstance(system, SystemMessage)
    assert system.content.endswith(preference_prompt)
    assert model.received[-1][1].content == "你好"


async def test_openui_disabled_keeps_system_prompt_unchanged() -> None:
    """关闭时系统提示词与基础提示词逐字节一致，保证无行为差异。"""
    model = RecordingModel("收到")
    agent = build_agent(
        model=model,
        tools=[],
        checkpointer=MemorySaver(),
        context_max_tokens=1000,
        openui_enabled=False,
    )
    config = {"configurable": {"thread_id": "openui-off"}}

    await agent.ainvoke({"messages": [HumanMessage("你好")]}, config)

    system = model.received[-1][0]
    assert isinstance(system, SystemMessage)
    assert system.content == load_system_prompt()


async def test_openui_enabled_injects_contract_after_base_prompt() -> None:
    """开启时追加契约，基础人格仍是提示词开头。"""
    model = RecordingModel("收到")
    agent = build_agent(
        model=model,
        tools=[],
        checkpointer=MemorySaver(),
        context_max_tokens=2000,
        openui_enabled=True,
    )
    config = {"configurable": {"thread_id": "openui-on"}}

    await agent.ainvoke({"messages": [HumanMessage("你好")]}, config)

    system = model.received[-1][0]
    assert isinstance(system, SystemMessage)
    assert system.content.startswith(load_system_prompt())
    assert "root = Stack" in system.content


def test_default_tools_expose_schema() -> None:
    """工具的 docstring 与参数会转成模型可见的 schema。"""
    time_tool = next(tool for tool in get_default_tools() if tool.name == "get_current_time")

    assert time_tool.name == "get_current_time"
    assert "当前时间" in (time_tool.description or "")
    assert "timezone" in time_tool.args


def _usage_collector(records: list[dict[str, Any]]) -> Any:
    """`record_usage` 已是异步函数（写入 outbox），测试用异步收集器替换它。"""

    async def collect(record: dict[str, Any]) -> None:
        records.append(record)

    return collect


def _runtime(model_key: str = "openai:gpt-4o-mini", task_id: str = "task-1") -> ResolvedRuntime:
    return ResolvedRuntime(
        task_id=task_id,
        provider="openai",
        model_key=model_key,
        credential_source="MANAGED",
    )


def _runtime_config(thread_id: str, runtime: ResolvedRuntime) -> dict[str, Any]:
    """运行时只放在 configurable，不能进入 AgentState 被 checkpointer 持久化。"""
    return {"configurable": {"thread_id": thread_id, "model_runtime": runtime}}


async def test_tool_loop_records_one_invocation_per_model_call(monkeypatch: Any) -> None:
    """工具循环里每次真实模型调用都要独立生成 invocation_id，便于按次计费。"""
    records: list[dict[str, Any]] = []
    monkeypatch.setattr(graph_module, "record_usage", _usage_collector(records))

    agent = build_agent(
        model=ScriptedModel([_tool_call_message(), AIMessage(content="现在时间已获取")])
    )

    await agent.ainvoke(
        {"messages": [HumanMessage("现在几点？")]},
        _runtime_config("usage-tool-loop", _runtime()),
    )

    assert len(records) == 2
    assert records[0]["invocation_id"] != records[1]["invocation_id"]
    assert all(record["task_id"] == "task-1" for record in records)
    assert all(record["status"] == STATUS_SUCCESS for record in records)


async def test_missing_token_usage_is_recorded_as_null(monkeypatch: Any) -> None:
    """Provider 未返回用量时必须是 null，禁止填 0 或估算值。"""
    records: list[dict[str, Any]] = []
    monkeypatch.setattr(graph_module, "record_usage", _usage_collector(records))

    agent = build_agent(model=ScriptedModel([AIMessage(content="你好")]))

    await agent.ainvoke(
        {"messages": [HumanMessage("你好")]},
        _runtime_config("usage-missing-tokens", _runtime()),
    )

    assert records[0]["prompt_tokens"] is None
    assert records[0]["completion_tokens"] is None
    # 成本由 Java 依据定价表计算，Agent 上报中不应出现费用字段
    assert "estimated_cost" not in records[0]
    assert records[0]["latency_ms"] >= 0


async def test_present_token_usage_is_captured(monkeypatch: Any) -> None:
    """Provider 返回用量时原样采集，不做二次计算。"""
    records: list[dict[str, Any]] = []
    monkeypatch.setattr(graph_module, "record_usage", _usage_collector(records))

    message = AIMessage(
        content="收到",
        usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
    )
    agent = build_agent(model=ScriptedModel([message]))

    await agent.ainvoke(
        {"messages": [HumanMessage("你好")]},
        _runtime_config("usage-tokens", _runtime()),
    )

    assert records[0]["prompt_tokens"] == 5
    assert records[0]["completion_tokens"] == 7


class ExplodingModel:
    """调用即抛异常，用于验证失败路径的用量记录。"""

    def bind_tools(self, tools: Any) -> "ExplodingModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        raise RuntimeError("upstream boom")


async def test_failed_call_records_failure_without_leaking_message(monkeypatch: Any) -> None:
    """失败也要记录用量；只保留异常类型，异常文本可能含上游细节。"""
    records: list[dict[str, Any]] = []
    monkeypatch.setattr(graph_module, "record_usage", _usage_collector(records))

    agent = build_agent(model=ExplodingModel())

    with pytest.raises(RuntimeError):
        await agent.ainvoke(
            {"messages": [HumanMessage("你好")]},
            _runtime_config("usage-failure", _runtime()),
        )

    assert len(records) == 1
    assert records[0]["status"] == STATUS_FAILURE
    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["prompt_tokens"] is None
    assert "boom" not in str(records[0])


async def test_runtime_is_not_persisted_into_agent_state(monkeypatch: Any) -> None:
    """运行时信息不进状态，历史接口与 checkpointer 都不应看到任务元数据。"""
    records: list[dict[str, Any]] = []
    monkeypatch.setattr(graph_module, "record_usage", _usage_collector(records))

    agent = build_agent(model=ScriptedModel([AIMessage(content="好的")]))

    result = await agent.ainvoke(
        {"messages": [HumanMessage("你好")]},
        _runtime_config("usage-state", _runtime()),
    )

    assert "model_runtime" not in result
    assert "task_id" not in result
    # 记录里也不允许出现任何凭据字段
    assert "user_token" not in records[0]
    assert "api_key" not in records[0]


class NamedModel:
    """带名字的假模型，用于断言「切换模型必须换实例」。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def bind_tools(self, tools: Any) -> "NamedModel":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=f"来自 {self.name}")


def test_profile_controls_prompt_tools_and_model_params(monkeypatch: Any) -> None:
    """请求级 agent_id 必须切换提示词、工具集与模型参数，且与 default 独立缓存。"""
    clear_agent_cache()
    prompts: list[str] = []
    captured: dict[str, Any] = {}

    def fake_load_prompt(name: str = "default") -> str:
        prompts.append(name)
        return f"prompt:{name}"

    def fake_get_chat_model(
        provider: str | None = None,
        model_key: str | None = None,
        credential_id: str | None = None,
        *,
        agent_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> NamedModel:
        captured.update(
            agent_id=agent_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return NamedModel(agent_id or "")

    monkeypatch.setattr(graph_module, "load_system_prompt", fake_load_prompt)
    monkeypatch.setattr(graph_module, "get_chat_model", fake_get_chat_model)

    writer_graph = get_agent_for_runtime(None, agent_id="writer")

    assert prompts == ["writer"]
    assert captured == {"agent_id": "writer", "temperature": 0.8, "max_tokens": 3000}

    # 同一运行时模型下，不同 agent_id 也必须各自缓存一张图
    runtime = _runtime("openai:gpt-4o-mini")
    assert get_agent_for_runtime(runtime, agent_id="writer") is not get_agent_for_runtime(
        runtime, agent_id="default"
    )
    assert writer_graph is not get_agent()
    clear_agent_cache()


def test_get_agent_for_runtime_switches_model_instance(monkeypatch: Any) -> None:
    """不同模型不复用同一张编译图；同一模型才复用缓存。"""
    clear_agent_cache()
    created: list[tuple[str, str, str | None]] = []

    def fake_get_chat_model(
        provider: str | None = None,
        model_key: str | None = None,
        credential_id: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **_profile_kwargs: Any,
    ) -> NamedModel:
        created.append((provider or "", model_key or "", credential_id))
        return NamedModel(model_key or "")

    monkeypatch.setattr(graph_module, "get_chat_model", fake_get_chat_model)

    runtime_a = _runtime("openai:gpt-4o-mini")
    runtime_b = _runtime("openai:gpt-4o")

    first = get_agent_for_runtime(runtime_a)
    again = get_agent_for_runtime(runtime_a)
    other = get_agent_for_runtime(runtime_b)

    assert first is again
    assert other is not first
    assert created == [
        ("openai", "openai:gpt-4o-mini", None),
        ("openai", "openai:gpt-4o", None),
    ]
    # runtime 为 None 时沿用进程默认图
    assert get_agent_for_runtime(None) is get_agent()
    clear_agent_cache()


def test_get_agent_for_runtime_passes_byok_credential(monkeypatch: Any) -> None:
    """BYOK 首次构图必须带上兑换到的密钥与接入地址。"""
    clear_agent_cache()
    created: list[tuple[str | None, str | None, str | None, str | None]] = []

    def fake_get_chat_model(
        provider: str | None = None,
        model_key: str | None = None,
        credential_id: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **_profile_kwargs: Any,
    ) -> NamedModel:
        created.append((provider, model_key, api_key, base_url))
        return NamedModel(model_key or "")

    monkeypatch.setattr(graph_module, "get_chat_model", fake_get_chat_model)

    runtime = ResolvedRuntime(
        task_id="task-byok",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="BYOK",
        credential_id="cred-1",
        base_url="https://byok.example.com/v1",
    )
    first = get_agent_for_runtime(runtime, api_key="sk-byok-secret")

    assert created == [
        ("openai", "openai:gpt-4o-mini", "sk-byok-secret", "https://byok.example.com/v1")
    ]
    # 同凭证再次请求复用同一张图，不需要重复兑换
    assert get_agent_for_runtime(runtime) is first
    clear_agent_cache()


def test_invalidate_credential_drops_cached_byok_graph(monkeypatch: Any) -> None:
    """凭证撤销后必须丢弃缓存图，避免残留明文密钥被继续使用。"""
    clear_agent_cache()
    counter = {"value": 0}

    def fake_get_chat_model(
        provider: str | None = None,
        model_key: str | None = None,
        credential_id: str | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **_profile_kwargs: Any,
    ) -> NamedModel:
        counter["value"] += 1
        return NamedModel(f"{model_key}-{counter['value']}")

    monkeypatch.setattr(graph_module, "get_chat_model", fake_get_chat_model)
    runtime = ResolvedRuntime(
        task_id="task-byok",
        provider="openai",
        model_key="openai:gpt-4o-mini",
        credential_source="BYOK",
        credential_id="cred-1",
        base_url="https://byok.example.com/v1",
    )

    first = get_agent_for_runtime(runtime, api_key="sk-byok-1")
    graph_module.invalidate_credential("cred-1")
    second = get_agent_for_runtime(runtime, api_key="sk-byok-2")

    assert first is not second
    clear_agent_cache()
