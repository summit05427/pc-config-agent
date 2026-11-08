"""异步任务接口：默认内联实现、注册表与实现替换。"""

from collections.abc import Iterator
from typing import Any

import pytest

from app.services.task_runner import (
    TASK_STATUS_FAILED,
    TASK_STATUS_SUCCEEDED,
    InlineTaskRunner,
    TaskConfigError,
    TaskRecord,
    TaskRunner,
    TaskSpec,
    get_task_runner,
    list_task_kinds,
    register_task_handler,
    reset_task_handlers,
    reset_task_runner,
    set_task_runner,
)

KIND = "demo"


@pytest.fixture(autouse=True)
def _reset_task_state() -> Iterator[None]:
    """处理器与默认执行器都是进程级状态，用例前后清空。"""
    reset_task_handlers()
    reset_task_runner()
    yield
    reset_task_handlers()
    reset_task_runner()


def _register_recording_handler(
    calls: list[TaskSpec],
    result: dict[str, Any] | None = None,
) -> None:
    async def handler(spec: TaskSpec) -> dict[str, Any] | None:
        calls.append(spec)
        return result

    register_task_handler(KIND, handler)


async def test_submit_runs_inline_and_returns_terminal_record() -> None:
    calls: list[TaskSpec] = []
    _register_recording_handler(calls, {"ok": True})
    runner = InlineTaskRunner()

    record = await runner.submit(TaskSpec(kind=KIND, user_id="user-1", payload={"n": 1}))

    assert record.status == TASK_STATUS_SUCCEEDED
    assert record.result == {"ok": True}
    assert record.error is None
    assert len(record.task_id) == 32
    assert calls[0].payload == {"n": 1}


async def test_submit_with_same_task_id_is_idempotent() -> None:
    """同一用户重复提交同一 ID 只执行一次，避免重复调用外部服务。"""
    calls: list[TaskSpec] = []
    _register_recording_handler(calls)
    runner = InlineTaskRunner()
    spec = TaskSpec(kind=KIND, user_id="user-1", task_id="job-1")

    first = await runner.submit(spec)
    second = await runner.submit(spec)

    assert first is second
    assert len(calls) == 1


async def test_submit_without_result_stores_none() -> None:
    calls: list[TaskSpec] = []
    _register_recording_handler(calls)
    runner = InlineTaskRunner()

    record = await runner.submit(TaskSpec(kind=KIND, user_id="user-1"))

    assert record.result is None


async def test_submit_unknown_kind_is_config_error() -> None:
    runner = InlineTaskRunner()

    with pytest.raises(TaskConfigError, match="未注册的任务类型"):
        await runner.submit(TaskSpec(kind="missing", user_id="user-1"))


async def test_submit_failure_records_truncated_error() -> None:
    async def handler(_: TaskSpec) -> dict[str, Any]:
        raise RuntimeError("x" * 500)

    register_task_handler(KIND, handler)
    runner = InlineTaskRunner()

    record = await runner.submit(TaskSpec(kind=KIND, user_id="user-1"))

    assert record.status == TASK_STATUS_FAILED
    assert record.result is None
    assert record.error is not None
    assert len(record.error) == 200


async def test_get_respects_user_scope() -> None:
    calls: list[TaskSpec] = []
    _register_recording_handler(calls)
    runner = InlineTaskRunner()
    record = await runner.submit(TaskSpec(kind=KIND, user_id="user-1", task_id="job-1"))

    assert await runner.get("job-1", user_id="user-1") == record
    assert await runner.get("job-1", user_id="user-2") is None
    assert await runner.get("missing", user_id="user-1") is None


async def test_cancel_returns_false_for_inline_runner() -> None:
    """内联执行返回时已是终态，不存在可取消的进行中任务。"""
    calls: list[TaskSpec] = []
    _register_recording_handler(calls)
    runner = InlineTaskRunner()
    await runner.submit(TaskSpec(kind=KIND, user_id="user-1", task_id="job-1"))

    assert await runner.cancel("job-1", user_id="user-1") is False
    assert await runner.cancel("job-1", user_id="user-2") is False


async def test_record_store_is_bounded() -> None:
    """进程内记录必须有上限，否则长运行进程会持续增长。"""
    calls: list[TaskSpec] = []
    _register_recording_handler(calls)
    runner = InlineTaskRunner(max_records=2)

    for index in range(3):
        await runner.submit(TaskSpec(kind=KIND, user_id="user-1", task_id=f"job-{index}"))

    assert await runner.get("job-0", user_id="user-1") is None
    assert await runner.get("job-2", user_id="user-1") is not None


def test_inline_runner_rejects_invalid_max_records() -> None:
    with pytest.raises(ValueError, match="max_records"):
        InlineTaskRunner(max_records=0)


def test_task_spec_rejects_blank_fields() -> None:
    with pytest.raises(ValueError, match="kind"):
        TaskSpec(kind="  ", user_id="user-1")
    with pytest.raises(ValueError, match="user_id"):
        TaskSpec(kind=KIND, user_id="")
    with pytest.raises(ValueError, match="task_id"):
        TaskSpec(kind=KIND, user_id="user-1", task_id="t" * 65)


def test_registry_lists_and_resets_handlers() -> None:
    async def handler(_: TaskSpec) -> None:
        return None

    register_task_handler(KIND, handler)

    assert list_task_kinds() == (KIND,)
    reset_task_handlers()
    assert list_task_kinds() == ()


def test_register_rejects_invalid_kind_and_handler() -> None:
    async def handler(_: TaskSpec) -> None:
        return None

    with pytest.raises(TaskConfigError, match="任务类型非法"):
        register_task_handler("", handler)
    with pytest.raises(TaskConfigError, match="不可调用"):
        register_task_handler(KIND, "not-callable")  # type: ignore[arg-type]


async def test_set_task_runner_replaces_implementation() -> None:
    """替换实现后调用方仍走 `get_task_runner()`，路由与业务代码无需改动。"""

    class _StubRunner:
        def __init__(self) -> None:
            self.submitted: list[TaskSpec] = []

        async def submit(self, spec: TaskSpec) -> TaskRecord:
            self.submitted.append(spec)
            return TaskRecord(
                task_id=spec.task_id or "stub-1",
                kind=spec.kind,
                user_id=spec.user_id,
                status=TASK_STATUS_SUCCEEDED,
            )

        async def get(self, task_id: str, *, user_id: str) -> TaskRecord | None:
            return None

        async def cancel(self, task_id: str, *, user_id: str) -> bool:
            return True

    stub = _StubRunner()
    set_task_runner(stub)

    assert get_task_runner() is stub
    record = await get_task_runner().submit(TaskSpec(kind=KIND, user_id="user-1"))
    assert record.status == TASK_STATUS_SUCCEEDED
    assert await get_task_runner().cancel("stub-1", user_id="user-1") is True

    reset_task_runner()
    assert isinstance(get_task_runner(), InlineTaskRunner)


def test_default_runner_is_inline() -> None:
    runner: TaskRunner = get_task_runner()

    assert isinstance(runner, InlineTaskRunner)
