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
# LLM 选型在候选校验、Java 组装或修正上限后仍无有效方案
STATUS_ARCHITECT_FAILED = "architect_failed"
# 用户在 HITL 确认环节主动终止；属于终态，不再继续生成方案
STATUS_ABORTED = "aborted"

# 选型模式：solver 保持原确定性求解器；llm 由 Build Architect 结构化选型
SELECTION_MODE_SOLVER = "solver"
SELECTION_MODE_LLM = "llm"

# 策略来源：MODEL 是模型产物；DEFAULT 是模型不可用/非法时的确定性兜底，不得混用
STRATEGY_SOURCE_MODEL = "MODEL"
STRATEGY_SOURCE_DEFAULT = "DEFAULT"

# 结构化失败类型：工具层与节点层共用，避免字符串漂移
FAILURE_USER_TOKEN_MISSING = "USER_TOKEN_MISSING"
FAILURE_CANDIDATE_NOT_IN_POOL = "CANDIDATE_NOT_IN_POOL"
FAILURE_OFFER_UNAVAILABLE = "OFFER_UNAVAILABLE"
FAILURE_COMPATIBILITY_CONFLICT = "COMPATIBILITY_CONFLICT"
FAILURE_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
FAILURE_TOOL_ERROR = "TOOL_ERROR"
FAILURE_MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
FAILURE_OUTPUT_TRUNCATED = "OUTPUT_TRUNCATED"
# 质量评审发现「搭得不合理」但可通过换件修正；与兼容性、预算失败区分开
FAILURE_QUALITY_CONSTRAINT = "QUALITY_CONSTRAINT"

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
        STATUS_ARCHITECT_FAILED,
        STATUS_ABORTED,
    }
)


def current_status(state: dict[str, Any]) -> str:
    """读取当前状态；缺失时视为需要澄清，避免静默继续。"""
    value = state.get("workflow_status")
    return value if isinstance(value, str) else STATUS_CLARIFICATION


def needs_clarification(state: dict[str, Any]) -> bool:
    return current_status(state) in {STATUS_CLARIFICATION, STATUS_INVALID}
