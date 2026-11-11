"""流水线状态常量与路由判断。

状态值同时用于图内路由和失败文案分支，集中定义避免字符串漂移。
"""

from typing import Any

STATUS_PARSED = "parsed"
STATUS_CLARIFICATION = "clarification"
STATUS_INVALID = "invalid"
STATUS_VALIDATED = "validated"
STATUS_RETRIEVED = "retrieved"
STATUS_NO_CANDIDATES = "no_candidates"
STATUS_NO_SOLUTION = "no_solution"
STATUS_SOLVED = "solved"
STATUS_RETRY = "retry"
STATUS_COMPATIBILITY_FAILED = "compatibility_failed"
STATUS_UPSTREAM_ERROR = "upstream_error"
STATUS_SUCCESS = "success"
# 用户在 HITL 确认环节主动终止；属于终态，不再继续生成方案
STATUS_ABORTED = "aborted"

# 上游不可用的统一安全文案，不把内部地址与异常堆栈暴露给用户
UPSTREAM_ERROR_MESSAGE = "配置服务暂时不可用，请稍后重试。"
EMPTY_CANDIDATES_MESSAGE = "当前硬件目录中没有找到可用于组装的候选硬件。"

TERMINAL_FAILURE_STATUSES = frozenset(
    {
        STATUS_CLARIFICATION,
        STATUS_INVALID,
        STATUS_NO_CANDIDATES,
        STATUS_NO_SOLUTION,
        STATUS_UPSTREAM_ERROR,
        STATUS_COMPATIBILITY_FAILED,
        STATUS_ABORTED,
    }
)


def current_status(state: dict[str, Any]) -> str:
    """读取当前状态；缺失时视为需要澄清，避免静默继续。"""
    value = state.get("workflow_status")
    return value if isinstance(value, str) else STATUS_CLARIFICATION


def needs_clarification(state: dict[str, Any]) -> bool:
    return current_status(state) in {STATUS_CLARIFICATION, STATUS_INVALID}
