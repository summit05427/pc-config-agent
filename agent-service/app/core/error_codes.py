"""错误码注册表：所有对外错误码集中登记，新增必须在此登记。

为什么集中：
1. 前端按 `code` 分支处理，码值散落时同一语义容易出现多种写法；
2. `tests/test_error_codes.py` 扫描源码里的 `code="..."` 字面量，
   未登记的码会让测试失败，避免"先加码再补文档"；
3. 控制面（Java）透传的码也登记在这里，只做追溯，Agent 不改写。

命名约定：`http_<状态码>` 由框架级错误（404 / 405 等）自动生成，按模式匹配。
"""

import re

# --- 通用 ---
CODE_APP_ERROR = "app_error"
CODE_VALIDATION_ERROR = "validation_error"
CODE_INTERNAL_ERROR = "internal_error"

# --- 鉴权 ---
CODE_UNAUTHORIZED = "unauthorized"
CODE_TOKEN_INVALID = "token_invalid"
CODE_TOKEN_EXPIRED = "token_expired"
CODE_FORBIDDEN = "forbidden"
CODE_DEV_TOKEN_UNAVAILABLE = "dev_token_unavailable"

# --- 会话与请求 ---
CODE_DUPLICATE_REQUEST = "duplicate_request"
CODE_REQUEST_IN_PROGRESS = "request_in_progress"
CODE_LOCK_NOT_ACQUIRED = "lock_not_acquired"
CODE_SESSION_NOT_FOUND = "session_not_found"
CODE_INVALID_PAGINATION = "invalid_pagination"

# --- Agent ---
CODE_AGENT_NOT_FOUND = "agent_not_found"
CODE_MODEL_RUNTIME_DISABLED = "model_runtime_disabled"
# 流内错误（SSE error 事件，HTTP 状态码已是 200）
CODE_REQUEST_TIMEOUT = "request_timeout"
CODE_AGENT_ERROR = "agent_error"

# --- 人机协同（HITL） ---
CODE_HITL_UNAVAILABLE = "hitl_unavailable"
CODE_INTERRUPT_NOT_FOUND = "interrupt_not_found"
CODE_INTERRUPT_EXPIRED = "interrupt_expired"
CODE_INTERRUPT_MISMATCH = "interrupt_mismatch"
CODE_HITL_RESUME_INVALID = "hitl_resume_invalid"

# --- 模型与凭证 ---
CODE_CREDENTIAL_UNAVAILABLE = "credential_unavailable"
CODE_LLM_NOT_CONFIGURED = "llm_not_configured"
CODE_LLM_PROVIDER_UNSUPPORTED = "llm_provider_unsupported"

# --- 可观测 ---
CODE_METRICS_DISABLED = "metrics_disabled"
CODE_METRICS_FORBIDDEN = "metrics_forbidden"

# --- 基础设施 ---
CODE_REDIS_UNAVAILABLE = "redis_unavailable"

# --- 输入护栏与限流 ---
CODE_INPUT_REJECTED = "input_rejected"
CODE_RATE_LIMITED = "rate_limited"

# --- 控制面透传（Java 定义，Agent 原样返回） ---
CODE_QUOTA_EXCEEDED = "quota_exceeded"
CODE_MODEL_NOT_AVAILABLE = "model_not_available"
CODE_CAPABILITY_UNSUPPORTED = "capability_unsupported"
CODE_CONTROL_PLANE_UNAVAILABLE = "control_plane_unavailable"
CODE_UPSTREAM_ERROR = "upstream_error"
CODE_CREDENTIAL_REVOKED = "credential_revoked"
CODE_CREDENTIAL_LEASE_CONSUMED = "credential_lease_consumed"
CODE_LEASE_NOT_BYOK = "lease_not_byok"
CODE_CREDENTIAL_REJECTED = "credential_rejected"
CODE_IDEMPOTENCY_CONFLICT = "idempotency_conflict"

ERROR_CODES: dict[str, str] = {
    CODE_APP_ERROR: "未分类的业务错误",
    CODE_VALIDATION_ERROR: "请求参数校验失败",
    CODE_INTERNAL_ERROR: "未捕获的服务器错误",
    CODE_UNAUTHORIZED: "缺少或无效的访问令牌",
    CODE_TOKEN_INVALID: "访问令牌无法验证",
    CODE_TOKEN_EXPIRED: "访问令牌已过期",
    CODE_FORBIDDEN: "当前身份无权访问",
    CODE_DEV_TOKEN_UNAVAILABLE: "开发令牌签发不可用",
    CODE_DUPLICATE_REQUEST: "相同幂等键的请求已处理完成",
    CODE_REQUEST_IN_PROGRESS: "相同幂等键的请求正在处理",
    CODE_LOCK_NOT_ACQUIRED: "等待窗口内未拿到会话锁",
    CODE_SESSION_NOT_FOUND: "会话不存在",
    CODE_INVALID_PAGINATION: "分页参数非法",
    CODE_AGENT_NOT_FOUND: "指定的 Agent Profile 不存在",
    CODE_MODEL_RUNTIME_DISABLED: "模型运行时未启用",
    CODE_REQUEST_TIMEOUT: "整轮流式响应超时（流内）",
    CODE_AGENT_ERROR: "图执行异常（流内）",
    CODE_HITL_UNAVAILABLE: "HITL 未启用或存储后端不支持中断",
    CODE_INTERRUPT_NOT_FOUND: "当前会话没有待恢复的中断",
    CODE_INTERRUPT_EXPIRED: "待恢复的中断已过期",
    CODE_INTERRUPT_MISMATCH: "恢复请求与待处理的中断不匹配",
    CODE_HITL_RESUME_INVALID: "中断恢复内容无效",
    CODE_CREDENTIAL_UNAVAILABLE: "BYOK 凭证未就绪",
    CODE_LLM_NOT_CONFIGURED: "LLM 未配置密钥",
    CODE_LLM_PROVIDER_UNSUPPORTED: "Provider 无法映射到网关",
    CODE_METRICS_DISABLED: "指标端点未启用",
    CODE_METRICS_FORBIDDEN: "指标访问被拒绝",
    CODE_REDIS_UNAVAILABLE: "Redis 不可用",
    CODE_INPUT_REJECTED: "输入被护栏拒绝",
    CODE_RATE_LIMITED: "请求过于频繁",
    CODE_QUOTA_EXCEEDED: "今日请求额度用尽（控制面透传）",
    CODE_MODEL_NOT_AVAILABLE: "模型不存在或用户不可用（控制面透传）",
    CODE_CAPABILITY_UNSUPPORTED: "模型不支持所需能力（控制面透传）",
    CODE_CONTROL_PLANE_UNAVAILABLE: "控制面不可达（控制面透传）",
    CODE_UPSTREAM_ERROR: "上游返回未知错误（控制面透传）",
    CODE_CREDENTIAL_REVOKED: "BYOK 凭证已撤销（控制面透传）",
    CODE_CREDENTIAL_LEASE_CONSUMED: "凭证租约已被占用（控制面透传）",
    CODE_LEASE_NOT_BYOK: "租约不是 BYOK 模式（控制面透传）",
    CODE_CREDENTIAL_REJECTED: "凭证校验失败（控制面透传）",
    CODE_IDEMPOTENCY_CONFLICT: "幂等键冲突（控制面透传）",
}

HTTP_ERROR_CODE_PATTERN = re.compile(r"^http_[0-9]{3}$")


def build_http_error_code(status_code: int) -> str:
    """框架级错误统一编码为 `http_<状态码>`，不单独占登记项。"""
    return f"http_{status_code}"


def is_registered(code: str) -> bool:
    """码是否已登记；`http_<状态码>` 由模式匹配放行。"""
    return code in ERROR_CODES or bool(HTTP_ERROR_CODE_PATTERN.fullmatch(code))
