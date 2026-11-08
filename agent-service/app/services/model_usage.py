"""使用明细上报：持久化 outbox + 后台批量投递。

为什么不在 Agent 建持久化台账：
使用明细的唯一事实源在 Java（`model_usage` 表）；Agent 只做「采集 + 投递」。
`usage_outbox` 只保存待投递事件，投递成功即标记 dispatched，不构成第二套台账（D7）。

可靠性约束：
- 记录在模型调用结束时就落库（或降级到内存），进程崩溃后重启会续传；
- 单批最多 20 条；可重试失败按退避重排，4xx 或超过尝试上限标记 dead；
- 上报失败不改变 SSE 结果、不回滚对话、不向用户报错（D11）。
"""

from __future__ import annotations

import asyncio
import time
from typing import TypedDict

import structlog

from app.services import usage_outbox
from app.services.control_plane import (
    ControlPlaneClient,
    ControlPlaneError,
    get_control_plane_client,
)

logger = structlog.get_logger(__name__)

MAX_BATCH_SIZE = 20
# 后台轮询间隔：既负责重试到期记录，也负责启动后补发上个进程遗留的记录
POLL_INTERVAL_SECONDS = 1.0
# 指标与清理是旁路工作，按固定间隔执行，避免每次轮询都做聚合查询
METRICS_REFRESH_SECONDS = 30.0
PURGE_INTERVAL_SECONDS = 3600.0

STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"

# 关闭上报时的等待上限：上报是旁路能力，不能拖住应用退出
STOP_TIMEOUT_SECONDS = 10.0


class UsageRecord(TypedDict):
    """一次真实模型调用的明细；Token 与延迟拿不到时为 `None`，不填 0。"""

    invocation_id: str
    task_id: str
    model_role: str
    provider: str
    model_key: str
    credential_source: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    status: str
    error_type: str | None
    occurred_at: str


class UsageReporter:
    """单消费者投递循环：入队写 outbox，发送交给后台任务。"""

    def __init__(
        self,
        client: ControlPlaneClient | None = None,
        *,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._client = client
        self._poll_interval = poll_interval_seconds
        # 唤醒事件在 start() 里创建：进程内单例可能被多个事件循环复用，
        # 跨循环复用 asyncio.Event 会触发 "bound to a different event loop"
        self._wakeup: asyncio.Event | None = None
        self._worker: asyncio.Task[None] | None = None
        self._is_stopping = False
        self._forwarded_count = 0
        self._failed_attempt_count = 0
        now = time.monotonic()
        self._last_metrics_at = now - METRICS_REFRESH_SECONDS
        self._last_purge_at = now - PURGE_INTERVAL_SECONDS

    @property
    def forwarded_count(self) -> int:
        """成功投递（不含部分被 Java 拒绝）的记录数，供测试与运行期自检。"""
        return self._forwarded_count

    @property
    def failed_attempt_count(self) -> int:
        """失败尝试的累计记录数（同一条记录重试会多次计数）。"""
        return self._failed_attempt_count

    @property
    def overflow_count(self) -> int:
        return usage_outbox.memory_overflow_count()

    async def enqueue(self, record: UsageRecord) -> None:
        """写入 outbox；降级与否由 outbox 决定，本方法不抛异常。"""
        await usage_outbox.add(dict(record))
        if self._wakeup is not None:
            self._wakeup.set()

    async def start(self) -> None:
        """启动后台消费者；重复调用是幂等的。"""
        if self._worker is not None and not self._worker.done():
            return
        self._is_stopping = False
        self._wakeup = asyncio.Event()
        # 启动即唤醒：既要发完刚入队的记录，也要补发上个进程遗留的 outbox 记录
        self._wakeup.set()
        self._worker = asyncio.create_task(self._run(self._wakeup), name="model-usage-reporter")

    async def stop(self) -> None:
        """停止消费者：先尽力发完已到期记录，超时则直接取消。"""
        self._is_stopping = True
        if self._wakeup is not None:
            self._wakeup.set()
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        try:
            await asyncio.wait_for(worker, timeout=STOP_TIMEOUT_SECONDS)
        except TimeoutError:
            worker.cancel()
            # 取消后必须等任务真正退出：否则关闭阶段仍可能残留协程持有队列
            await asyncio.gather(worker, return_exceptions=True)
        except asyncio.CancelledError:
            # 调用方被取消时也要把消费者收干净，再把取消继续抛出去
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            raise

    async def _run(self, wakeup: asyncio.Event) -> None:
        while True:
            await self._drain()
            await self._run_periodic_tasks()
            if self._is_stopping:
                return
            try:
                await asyncio.wait_for(wakeup.wait(), timeout=self._poll_interval)
            except TimeoutError:
                # 到点轮询：负责重试到期记录与其它副本遗留的 pending
                continue
            wakeup.clear()

    async def _drain(self) -> None:
        """循环领取直到没有到期记录；失败记录会被 outbox 延后，不会立即再领。"""
        while True:
            claimed = await usage_outbox.claim(MAX_BATCH_SIZE)
            if not claimed:
                return
            await self._send_batch(claimed)

    async def _run_periodic_tasks(self) -> None:
        now = time.monotonic()
        if now - self._last_metrics_at >= METRICS_REFRESH_SECONDS:
            self._last_metrics_at = now
            await usage_outbox.update_metrics()
        if now - self._last_purge_at >= PURGE_INTERVAL_SECONDS:
            self._last_purge_at = now
            await usage_outbox.purge_dispatched()

    async def _send_batch(self, claimed: list[usage_outbox.ClaimedRecord]) -> None:
        """按批次上报；任何失败都只记日志并更新 outbox 状态，不向调用方抛出。"""
        client = self._client or get_control_plane_client()
        records = [dict(item.payload) for item in claimed]

        try:
            result = await client.report_usage(records)
        except ControlPlaneError as error:
            # 4xx 重试只会放大错误；错误文本只保留码与状态，避免把上游细节带进日志
            await self._on_failure(
                claimed,
                is_retryable=error.is_retryable,
                error=f"{error.code}:{error.status_code}",
            )
            return
        except Exception as error:
            # 未预期异常（如序列化错误）同样不得影响主链路
            await self._on_failure(claimed, is_retryable=False, error=type(error).__name__)
            return

        await usage_outbox.mark_dispatched(claimed)
        self._forwarded_count += len(claimed)

        rejected = result.get("rejected")
        if isinstance(rejected, int) and rejected > 0:
            # 部分被拒说明记录本身有问题（如任务不存在），重发不会改变结果
            logger.warning(
                "model_usage.report_partially_rejected",
                rejected=rejected,
                batch_size=len(claimed),
            )

    async def _on_failure(
        self, claimed: list[usage_outbox.ClaimedRecord], *, is_retryable: bool, error: str
    ) -> None:
        self._failed_attempt_count += len(claimed)
        logger.warning(
            "model_usage.report_failed",
            error=error,
            retryable=is_retryable,
            attempts=max(item.attempts for item in claimed) + 1,
            batch_size=len(claimed),
        )
        await usage_outbox.mark_failed(claimed, is_retryable=is_retryable, error=error)


_reporter: UsageReporter | None = None


def get_usage_reporter() -> UsageReporter:
    """进程内单例，供图节点入队与 lifespan 启动/停止共用。"""
    global _reporter
    if _reporter is None:
        _reporter = UsageReporter()
    return _reporter


async def record_usage(record: UsageRecord) -> None:
    """模型调用结束后写入 outbox；DB 不可用时降级为内存入队，绝不阻塞主链路。"""
    await get_usage_reporter().enqueue(record)


async def start_usage_reporter() -> None:
    await get_usage_reporter().start()


async def stop_usage_reporter() -> None:
    await get_usage_reporter().stop()


def reset_usage_reporter() -> None:
    """丢弃单例并清空 outbox 进程内状态，仅供测试使用。"""
    global _reporter
    _reporter = None
    usage_outbox.reset_usage_outbox()
