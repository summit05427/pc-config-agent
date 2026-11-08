"""会话删除墓碑的状态、重试与调度常量。

状态机：
- `pending`：等待后台删除检查点；
- `completed`：检查点已删除（或当前 checkpointer 不支持删除，数据本就不持久）；
- `failed`：达到重试上限仍失败，保留记录供人工排查；
- `cancelled`：删除后同一会话被重新使用（新一轮对话），取消删除，避免误删新检查点。

调用方必须通过 `constants.X` 读取这些值，便于测试用 monkeypatch 调整退避与保留期。
"""

from __future__ import annotations

from typing import Literal

STATUS_PENDING: Literal["pending"] = "pending"
STATUS_COMPLETED: Literal["completed"] = "completed"
STATUS_FAILED: Literal["failed"] = "failed"
STATUS_CANCELLED: Literal["cancelled"] = "cancelled"

STATUS_VALUES = (STATUS_PENDING, STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED)

MAX_ATTEMPTS = 8
BATCH_SIZE = 20
MAX_ERROR_LENGTH = 200
# 连接池为 autocommit，领取时无法持锁，用推进 next_retry_at 形成租约
CLAIM_LEASE_SECONDS = 60.0
# 按已失败次数取退避；超出列表长度时复用最后一档
RETRY_BACKOFF_SECONDS = (30.0, 60.0, 300.0, 900.0, 1800.0, 3600.0, 3600.0)
COMPLETED_RETENTION_SECONDS = 7 * 24 * 3600
FAILED_RETENTION_SECONDS = 30 * 24 * 3600
POLL_INTERVAL_SECONDS = 5.0
METRICS_REFRESH_SECONDS = 30.0
PURGE_INTERVAL_SECONDS = 3600.0
