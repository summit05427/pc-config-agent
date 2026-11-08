"""异步任务接口：提交 / 查询 / 取消。

模板只定义协议与默认实现，不引入任务表、消息队列或状态机：

1. 默认 `InlineTaskRunner` 在 `submit()` 内同步执行并立即返回终态，
   调用方看到的结果与直接调用处理器一致，行为不变；
2. 接入方可用 `set_task_runner()` 换成队列 / Worker 实现，
   调用方统一走 `get_task_runner()`，不需要改任何路由或业务代码；
3. 任务处理器按 `kind` 注册，模板不内置任何 `kind`，也不负责调度与重试。

约束：`TaskRecord.error` 只保存截断后的异常信息，日志只记录异常类型，
避免把底层连接串、Token 等敏感内容带进任务记录。
"""

from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)

TaskStatus = Literal["running", "succeeded", "failed", "cancelled"]
TASK_STATUS_RUNNING: TaskStatus = "running"
TASK_STATUS_SUCCEEDED: TaskStatus = "succeeded"
TASK_STATUS_FAILED: TaskStatus = "failed"
TASK_STATUS_CANCELLED: TaskStatus = "cancelled"

MAX_KIND_LENGTH = 64
MAX_TASK_ID_LENGTH = 64
MAX_ERROR_LENGTH = 200
DEFAULT_MAX_RECORDS = 200

TaskHandler = Callable[["TaskSpec"], Awaitable[Mapping[str, Any] | None]]


class TaskConfigError(RuntimeError):
    """任务类型未注册或注册信息非法，属于接入配置错误。"""


@dataclass(frozen=True)
class TaskSpec:
    """一次任务提交。

    `task_id` 由调用方提供时用于幂等：同一用户重复提交同一 ID 直接复用已有记录，
    不会再次执行处理器。
    """

    kind: str
    user_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    task_id: str | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("kind 不能为空白")
        if len(self.kind) > MAX_KIND_LENGTH:
            raise ValueError(f"kind 不能超过 {MAX_KIND_LENGTH} 个字符")
        if not self.user_id:
            raise ValueError("user_id 不能为空")
        if self.task_id is not None and len(self.task_id) > MAX_TASK_ID_LENGTH:
            raise ValueError(f"task_id 不能超过 {MAX_TASK_ID_LENGTH} 个字符")


@dataclass(frozen=True)
class TaskRecord:
    """任务快照；`result` 与 `error` 互斥，`running` 时两者都为空。"""

    task_id: str
    kind: str
    user_id: str
    status: TaskStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TaskRunner(Protocol):
    """任务执行接口；实现可同步也可以是队列，调用方只依赖这三个方法。"""

    async def submit(self, spec: TaskSpec) -> TaskRecord:
        """提交任务并返回当前快照；异步实现可以返回 `running`。"""
        ...

    async def get(self, task_id: str, *, user_id: str) -> TaskRecord | None:
        """按任务 ID 查询；必须校验归属，其他用户一律视为不存在。"""
        ...

    async def cancel(self, task_id: str, *, user_id: str) -> bool:
        """尝试取消；已进入终态或不属于该用户时返回 False。"""
        ...


_HANDLERS: dict[str, TaskHandler] = {}


def register_task_handler(kind: str, handler: TaskHandler) -> None:
    """注册任务处理器；重复注册覆盖旧值，便于接入方热替换。"""
    if not kind.strip() or len(kind) > MAX_KIND_LENGTH:
        raise TaskConfigError(f"任务类型非法：{kind!r}")
    if not callable(handler):
        raise TaskConfigError(f"任务处理器不可调用：{kind}")
    _HANDLERS[kind] = handler


def get_task_handler(kind: str) -> TaskHandler | None:
    return _HANDLERS.get(kind)


def list_task_kinds() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


def reset_task_handlers() -> None:
    """清空注册表；测试与进程内重建使用。"""
    _HANDLERS.clear()


class InlineTaskRunner:
    """默认实现：在 `submit()` 内同步执行，立即返回终态。

    记录保存在进程内并限制上限，避免无界增长；进程重启即丢失，
    仅用于「接口存在、行为不变」的默认场景，不承担可靠投递。
    """

    def __init__(self, max_records: int = DEFAULT_MAX_RECORDS) -> None:
        if max_records < 1:
            raise ValueError("max_records 必须大于 0")
        self._max_records = max_records
        self._records: OrderedDict[tuple[str, str], TaskRecord] = OrderedDict()

    async def submit(self, spec: TaskSpec) -> TaskRecord:
        if spec.task_id is not None:
            existing = self._records.get((spec.user_id, spec.task_id))
            if existing is not None:
                return existing

        handler = get_task_handler(spec.kind)
        if handler is None:
            raise TaskConfigError(f"未注册的任务类型：{spec.kind}")

        task_id = spec.task_id or uuid4().hex
        logger.info("task.start", task_id=task_id, kind=spec.kind)
        try:
            result = await handler(spec)
        except Exception as exc:
            # 只记录类型，错误原文由处理器自行决定是否可安全返回
            logger.warning(
                "task.failed",
                task_id=task_id,
                kind=spec.kind,
                error_type=type(exc).__name__,
            )
            record = TaskRecord(
                task_id=task_id,
                kind=spec.kind,
                user_id=spec.user_id,
                status=TASK_STATUS_FAILED,
                error=str(exc)[:MAX_ERROR_LENGTH],
            )
        else:
            logger.info("task.finish", task_id=task_id, kind=spec.kind)
            record = TaskRecord(
                task_id=task_id,
                kind=spec.kind,
                user_id=spec.user_id,
                status=TASK_STATUS_SUCCEEDED,
                result=dict(result) if result else None,
            )

        self._store(record)
        return record

    async def get(self, task_id: str, *, user_id: str) -> TaskRecord | None:
        return self._records.get((user_id, task_id))

    async def cancel(self, task_id: str, *, user_id: str) -> bool:
        """内联执行在 `submit()` 返回时已是终态，没有可取消的进行中任务。"""
        return False

    def _store(self, record: TaskRecord) -> None:
        key = (record.user_id, record.task_id)
        self._records[key] = record
        self._records.move_to_end(key)
        while len(self._records) > self._max_records:
            self._records.popitem(last=False)


_RUNNER: TaskRunner = InlineTaskRunner()


def get_task_runner() -> TaskRunner:
    """调用方唯一入口；替换实现后无需改调用代码。"""
    return _RUNNER


def set_task_runner(runner: TaskRunner) -> None:
    """在应用启动前替换实现（例如在 hooks 模块中接入队列）。"""
    global _RUNNER
    _RUNNER = runner


def reset_task_runner() -> None:
    """恢复默认内联实现；测试与进程内重建使用。"""
    global _RUNNER
    _RUNNER = InlineTaskRunner()
