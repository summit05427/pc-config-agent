"""输入侧护栏。

目标：在进入模型之前拦下有明确风险或明显异常的输入，避免提示词注入把系统规则带偏，
也避免零宽字符、控制字符这类肉眼不可见的内容混入对话与日志。

设计取舍：
1. 命中即拒绝，因此注入特征只收高置信度模式（宁可漏检，不误杀正常提问）；
2. 纯函数 + 指标，不做 I/O，便于在路由入口同步执行；
3. 日志只记录规则名与输入长度，禁止打印用户原文。
"""

import re
import unicodedata

import structlog

from app.core.config import GuardSettings, get_settings
from app.core.exceptions import InputRejectedError
from app.core.metrics import INPUT_GUARD_VIOLATIONS

logger = structlog.get_logger(__name__)

RULE_TOO_LONG = "too_long"
RULE_CONTROL_CHARS = "control_chars"
RULE_ZERO_WIDTH = "zero_width"
RULE_INJECTION = "injection"

# 换行、回车、制表符是正常排版字符，其余 C0/C1 控制字符一律视为异常
ALLOWED_CONTROL_CHARS = frozenset({"\n", "\r", "\t"})

# 零宽与 Bidi 控制符：用户不可见，却可以改变词序或隐藏指令
ZERO_WIDTH_CHARS = frozenset(
    "\u200b\u200c\u200d\u200e\u200f"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2060\u2061\u2062\u2063\u2064"
    "\ufeff"
)

# 只保留高置信度特征：普通提问很少同时出现「动词 + 系统提示词」这类组合
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_previous",
        re.compile(
            r"(?i)\b(ignore|disregard|forget)\s+(all\s+|the\s+)?"
            r"(previous|prior|above)\s+(instructions?|prompts?|rules?)"
        ),
    ),
    ("system_prompt", re.compile(r"(?i)\b(system|developer)\s*(prompt|message)\b")),
    ("role_override", re.compile(r"(?i)\byou\s+are\s+now\s+(a|an|the)\b")),
    ("jailbreak", re.compile(r"(?i)\b(jailbreak|do\s+anything\s+now|dan\s+mode)\b")),
    (
        "cn_ignore_rules",
        re.compile(r"忽略(之前|以上|前面|先前)(的)?(所有)?(指令|规则|提示词?|要求)"),
    ),
    (
        "cn_prompt_leak",
        re.compile(r"(输出|告诉|展示|打印|复述)(一下)?(你的)?(系统提示词|system\s*prompt)", re.I),
    ),
    ("cn_role_override", re.compile(r"(现在|从现在开始)(你|您)(是|扮演)")),
)


def inspect_input(text: str, settings: GuardSettings) -> list[str]:
    """返回命中的规则名列表，按「长度 → 字符 → 注入」顺序排列。

    纯函数，不读配置也不写指标，便于单测直接构造各种输入。
    """
    violations: list[str] = []
    if len(text) > settings.max_input_chars:
        violations.append(RULE_TOO_LONG)

    has_control_chars = False
    has_zero_width = False
    for char in text:
        if char in ALLOWED_CONTROL_CHARS:
            continue
        if char in ZERO_WIDTH_CHARS:
            has_zero_width = True
        elif unicodedata.category(char) in {"Cc", "Cf"}:
            has_control_chars = True
    if has_control_chars:
        violations.append(RULE_CONTROL_CHARS)
    if has_zero_width:
        violations.append(RULE_ZERO_WIDTH)

    if settings.block_on_injection and _matches_injection(text):
        violations.append(RULE_INJECTION)
    return violations


def enforce_input_guard(text: str) -> None:
    """在路由入口执行校验；命中时抛 422 `input_rejected`。

    在幂等抢占与线程锁之前调用：被拒绝的请求不应占用幂等记录，也不应等待锁。
    """
    settings = get_settings().guard
    if not settings.enabled:
        return

    violations = inspect_input(text, settings)
    if not violations:
        return

    for rule in violations:
        INPUT_GUARD_VIOLATIONS.labels(rule=rule).inc()
    logger.warning(
        "input_guard.rejected",
        rules=violations,
        input_length=len(text),
        request_id=structlog.contextvars.get_contextvars().get("request_id", ""),
    )
    raise InputRejectedError()


def _matches_injection(text: str) -> bool:
    return any(pattern.search(text) for _, pattern in INJECTION_PATTERNS)
