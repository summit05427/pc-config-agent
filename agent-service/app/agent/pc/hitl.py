"""人机协同（HITL）门控节点：在关键决策前暂停图执行，等待用户补充或确认。

设计约束：
1. 门控节点只读写图状态，不发 HTTP、不调用工具，因此 `interrupt` 恢复时重跑无副作用；
2. 写操作节点（build_architect）始终位于门控之前，恢复不会重复落快照；
3. 中断载荷只暴露用户可见信息，禁止带出内部图状态、令牌或服务地址。

为什么把门控单独成节点而不是在业务节点里直接 `interrupt`：
业务节点一旦在写操作中途中断，恢复时整段逻辑会重跑；独立门控把「暂停」与
「业务计算」分开，恢复只重放门控本身。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from app.agent.pc.renderer import (
    COMPATIBILITY_LABELS,
    as_list,
    as_mapping,
    as_text,
    overall_compatibility,
)
from app.agent.pc.state import PCConfigState
from app.agent.pc.status import (
    STATUS_ABORTED,
    STATUS_CLARIFICATION,
    STATUS_SUCCESS,
)
from app.core.config import get_settings
from app.core.error_codes import CODE_HITL_UNAVAILABLE
from app.core.exceptions import AppError, HitlResumeInvalidError

logger = structlog.get_logger(__name__)


def interrupt_payload(item: Any) -> dict[str, Any] | None:
    """把 LangGraph 的 Interrupt 翻译成公开载荷。

    `interrupt_id` 以 LangGraph 为准，避免门控载荷伪造 id；载荷非法时返回 None，
    调用方跳过而不是编造字段。SSE 与历史消息共用同一结构。
    """
    value = getattr(item, "value", None)
    interrupt_id = getattr(item, "id", None)
    if not isinstance(value, dict) or not isinstance(interrupt_id, str):
        return None
    return {**value, "interrupt_id": interrupt_id}


def is_interrupt_expired(created_at: Any, ttl_seconds: int) -> bool:
    """checkpoint 时间是 ISO 字符串；无法解析时按未过期处理，避免误拒。"""
    if not isinstance(created_at, str):
        return False
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created).total_seconds() > ttl_seconds


INTERACTION_CLARIFY = "clarify_requirements"
INTERACTION_CONFIRM_COMPATIBILITY = "confirm_compatibility"

DECISION_CONTINUE = "continue"
DECISION_ABORT = "abort"

SCHEMA_VERSION = "1"

# 用途选项值必须与 `BuildScenario` 一致，label 必须能被确定性解析器识别
SCENARIO_CHOICES: tuple[tuple[str, str], ...] = (
    ("GAMING", "游戏"),
    ("VIDEO_EDITING", "视频剪辑"),
    ("PROGRAMMING", "编程开发"),
    ("RENDERING", "渲染"),
    ("AI_INFERENCE", "本地 AI 推理"),
    ("CREATIVE", "创作"),
    ("OFFICE", "办公"),
    ("BALANCED", "综合均衡"),
)

RENDER_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    ("CPU", "CPU 渲染"),
    ("GPU", "GPU 渲染"),
    ("BOTH", "CPU 与 GPU 都要"),
)

_FIELD_BUDGET = {
    "name": "budget_yuan",
    "label": "预算上限（元）",
    "type": "number",
    "required": True,
    "min": 1,
}
_FIELD_SCENARIO = {
    "name": "scenario",
    "label": "主要用途",
    "type": "select",
    "required": False,
    "options": [{"value": value, "label": label} for value, label in SCENARIO_CHOICES],
}
_FIELD_RENDER_MODE = {
    "name": "render_mode",
    "label": "渲染方式",
    "type": "select",
    "required": False,
    "options": [{"value": value, "label": label} for value, label in RENDER_MODE_CHOICES],
}

_COMPATIBILITY_FIELD = {
    "name": "decision",
    "label": "是否继续查看方案",
    "type": "radio",
    "required": True,
    "options": [
        {"value": DECISION_CONTINUE, "label": "继续查看"},
        {"value": DECISION_ABORT, "label": "终止本轮"},
    ],
}

_SCENARIO_LABELS = dict(SCENARIO_CHOICES)
_RENDER_MODE_LABELS = dict(RENDER_MODE_CHOICES)


def _ensure_hitl_available() -> None:
    """运行期兜底：配置层已保证 enabled 必须是 postgres，这里防止热更新绕过。"""
    settings = get_settings()
    if not settings.hitl.enabled:
        raise HitlResumeInvalidError("当前未启用 HITL，无法恢复中断")
    if settings.storage.backend != "postgres":
        raise AppError(
            "HITL 需要 postgres 会话存储，memory 后端不支持中断恢复",
            code=CODE_HITL_UNAVAILABLE,
            status_code=409,
        )


def _clarification_fields(missing_slots: list[str]) -> list[dict[str, Any]]:
    """按缺失槽位生成表单；缺省时同时收集预算与用途。"""
    fields: list[dict[str, Any]] = []
    if "budget_max_fen" in missing_slots:
        fields.append(_FIELD_BUDGET)
    if "scenario" in missing_slots:
        fields.append(_FIELD_SCENARIO)
    if "render_mode" in missing_slots:
        fields.append(_FIELD_RENDER_MODE)
    return fields or [_FIELD_BUDGET, _FIELD_SCENARIO]


def _clarification_payload(validation: dict[str, Any]) -> dict[str, Any]:
    missing_slots = [as_text(item) for item in as_list(validation.get("missing_fields"))]
    missing_slots = [item for item in missing_slots if item]
    question = as_text(validation.get("message")) or (
        "请补充预算和主要用途，我再为你推荐具体配置。"
    )
    return {
        "interaction_type": INTERACTION_CLARIFY,
        "question": question,
        "input_schema": {
            "fields": _clarification_fields(missing_slots),
            "submit_label": "继续生成配置",
        },
        "context": {"missing_slots": missing_slots},
        "schema_version": SCHEMA_VERSION,
    }


def _unverified_rules(report: dict[str, Any]) -> list[str]:
    rules: list[str] = []
    for item in as_list(report.get("checks")):
        check = as_mapping(item)
        if as_text(check.get("status")) != "UNKNOWN":
            continue
        rule = as_text(check.get("ruleName"), as_text(check.get("ruleId"), "未命名规则"))
        rules.append(rule)
    return rules


def _check_status_counts(report: dict[str, Any]) -> tuple[int, int, int]:
    """统计通过/失败/未验证的规则条数，用于给用户一个有比例感的结论。"""
    passed = failed = unknown = 0
    for item in as_list(report.get("checks")):
        status = as_text(as_mapping(item).get("status"))
        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        elif status == "UNKNOWN":
            unknown += 1
    return passed, failed, unknown


def build_compatibility_question(state: Mapping[str, Any]) -> str:
    """兼容性未验证时的固定提问；节点写历史消息与中断载荷共用同一文案。

    只说「未验证」会让用户无法判断风险大小，因此补上已通过条数，
    并指出未验证的具体规则，让确认动作有明确依据。
    """
    report = as_mapping(state.get("compatibility_report"))
    rules = _unverified_rules(report)
    passed, _, unknown = _check_status_counts(report)
    subject = "、".join(rules) if rules else "部分兼容性规则"
    if passed:
        return (
            f"已有 {passed} 项兼容性检查通过，但 {unknown} 项因数据缺失无法确认"
            f"（{subject}）。是否继续查看这份方案？"
        )
    return (
        f"本方案的兼容性仍有未验证项（{subject}），"
        "不能视为已确认兼容。是否继续查看这份方案？"
    )


def _compatibility_payload(state: PCConfigState) -> dict[str, Any]:
    report = as_mapping(state.get("compatibility_report"))
    return {
        "interaction_type": INTERACTION_CONFIRM_COMPATIBILITY,
        "question": build_compatibility_question(state),
        "input_schema": {
            "fields": [_COMPATIBILITY_FIELD],
            "submit_label": "确认",
        },
        "context": {
            "overall_status": overall_compatibility(report),
            "unverified_rules": _unverified_rules(report),
            "status_label": COMPATIBILITY_LABELS.get("UNKNOWN", "未验证"),
        },
        "schema_version": SCHEMA_VERSION,
    }


def _resume_parts(value: Any) -> tuple[dict[str, Any], str]:
    """拆出结构化答案与用户可读文本；两者都缺失时由调用方判为无效。"""
    if isinstance(value, dict):
        raw_answer = value.get("answer")
        answer = raw_answer if isinstance(raw_answer, dict) else {}
        raw_message = value.get("message")
        return answer, raw_message.strip() if isinstance(raw_message, str) else ""
    if isinstance(value, str):
        return {}, value.strip()
    return {}, ""


def _format_scalar(name: str, value: Any) -> str | None:
    """只接受受限类型与取值，避免把任意字符串拼进解析提示。"""
    if name == "budget_yuan":
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value > 0:
            return f"预算上限 {value} 元"
        if isinstance(value, str) and value.strip().isdigit() and int(value) > 0:
            return f"预算上限 {int(value)} 元"
        return None
    key = str(value)
    if name == "scenario":
        label = _SCENARIO_LABELS.get(key)
        return f"主要用途：{label}" if label else None
    if name == "render_mode":
        label = _RENDER_MODE_LABELS.get(key)
        return f"渲染方式：{label}" if label else None
    return None


def _format_clarification_answer(
    fields: list[dict[str, Any]], answer: dict[str, Any], message: str
) -> str:
    parts: list[str] = []
    for field in fields:
        name = as_text(field.get("name"))
        if not name:
            continue
        text = _format_scalar(name, answer.get(name))
        if text:
            parts.append(text)
    if parts:
        return "；".join(parts)
    return message


def _merge_clarification_answer(state: PCConfigState, supplement: str) -> dict[str, Any]:
    """把补充信息并入最后一条用户消息，解析器无需理解多轮合并规则。"""
    messages = list(state.get("messages") or [])
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, HumanMessage):
            continue
        original = message.content if isinstance(message.content, str) else ""
        merged = f"{original.strip()}\n补充：{supplement}" if original.strip() else supplement
        # 复用原消息 id 触发 add_messages 的替换语义，历史里不会多出一条重复提问
        if message.id:
            return {
                "messages": [HumanMessage(id=message.id, content=merged)],
                "workflow_status": "",
            }
        return {"messages": [HumanMessage(content=merged)], "workflow_status": ""}
    return {"messages": [HumanMessage(content=supplement)], "workflow_status": ""}


async def clarification_gate(state: PCConfigState) -> dict[str, Any]:
    """缺关键槽位时暂停并收集补充信息；未启用 HITL 时原样放行。"""
    if as_text(state.get("workflow_status")) != STATUS_CLARIFICATION:
        return {}
    if not get_settings().hitl.enabled:
        return {}

    _ensure_hitl_available()
    validation = as_mapping(state.get("validation_result"))
    payload = _clarification_payload(validation)
    resumed = interrupt(payload)
    answer, message = _resume_parts(resumed)
    fields = payload["input_schema"]["fields"]
    supplement = _format_clarification_answer(fields, answer, message)
    if not supplement:
        raise HitlResumeInvalidError()
    logger.info("pc.hitl.resumed", interaction_type=INTERACTION_CLARIFY)
    return _merge_clarification_answer(state, supplement)


async def compatibility_gate(state: PCConfigState) -> dict[str, Any]:
    """兼容性未验证时请求确认；用户终止则记录 aborted 终态。"""
    if as_text(state.get("workflow_status")) != STATUS_SUCCESS:
        return {}
    if not get_settings().hitl.enabled:
        return {}
    if overall_compatibility(as_mapping(state.get("compatibility_report"))) != "UNKNOWN":
        return {}

    _ensure_hitl_available()
    resumed = interrupt(_compatibility_payload(state))
    answer, message = _resume_parts(resumed)
    decision = as_text(answer.get("decision")) or message
    if decision not in {DECISION_CONTINUE, DECISION_ABORT}:
        raise HitlResumeInvalidError("请选择继续查看或终止本轮")
    logger.info("pc.hitl.resumed", interaction_type=INTERACTION_CONFIRM_COMPATIBILITY)
    if decision == DECISION_ABORT:
        return {"workflow_status": STATUS_ABORTED}
    return {}
