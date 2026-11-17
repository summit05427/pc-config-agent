"""E2E 评测骨架的单测：SSE 解析、契约断言与用例加载。

只测纯函数，不启动服务、不调用模型；真实链路由 `python -m evals.e2e` 执行。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agent.pc.schemas import REQUIRED_CATEGORIES
from app.api.v1.sse import SSE_SCHEMA_VERSION
from evals.e2e.contract import check_stream, interrupt_id
from evals.e2e.schema import (
    E2ECase,
    E2ECaseLoadError,
    E2EExpectation,
    load_e2e_cases,
)
from evals.e2e.sse import SseParseError, parse_events, parse_frames
from evals.report import STATUS_FAILED, STATUS_PASSED

CASES_DIRECTORY = Path(__file__).resolve().parents[1] / "evals" / "e2e" / "cases"


def _frame_text(event: str, data: dict[str, Any], event_id: int) -> str:
    payload = {**data, "schema_version": SSE_SCHEMA_VERSION}
    return f"id: {event_id}\nevent: {event}\ndata: {json.dumps(payload)}\n\n"


def _valid_stream(*, build_result: dict[str, Any] | None = None) -> list[str]:
    blocks = [
        _frame_text("token", {"text": "你好"}, 1),
        _frame_text(
            "done",
            {"thread_id": "t-1", "message_id": "t-1:1", "build_result": build_result}
            if build_result is not None
            else {"thread_id": "t-1", "message_id": "t-1:1"},
            2,
        ),
    ]
    return blocks


def _fake_build() -> dict[str, Any]:
    return {
        "components": [
            {"category": category.value, "price_fen": 100}
            for category in REQUIRED_CATEGORIES
        ],
        "total_price_fen": 100 * len(REQUIRED_CATEGORIES),
        "budget_max_fen": 0,
        "overall_status": "PASS",
    }


def _run_checks(case: E2ECase, blocks: list[str], latency_ms: int = 10) -> list[Any]:
    frames = list(parse_frames("".join(blocks).splitlines()))
    checks, _ = check_stream(case, frames, latency_ms)
    return checks


def _status(checks: list[Any], name: str) -> str:
    return next(check.status for check in checks if check.name == name)


def test_parse_frames_ignores_heartbeat_and_keeps_event_id() -> None:
    text = (
        ": ping - 2026-11-17T09:00:00Z\n\n"
        "id: 7\nevent: token\ndata: {\"text\":\"你好\"}\n\n"
    )
    frames = list(parse_frames(text.splitlines()))

    assert frames[0].is_comment is True
    assert frames[1].event_id == "7"
    events, errors = parse_events(frames)
    assert errors == []
    assert events[0].event == "token"
    assert events[0].data["text"] == "你好"


def test_parse_frames_joins_multiline_data_and_crlf() -> None:
    text = "id: 1\revent: token\r\ndata: {\"text\":\r\ndata: \"分片\"}\r\n\r\n"
    frames = list(parse_frames(text.splitlines()))
    event = frames[0].to_event()

    assert event.data == {"text": "分片"}


def test_frame_without_data_is_rejected() -> None:
    frames = list(parse_frames(["id: 1", "event: token", ""]))

    with pytest.raises(SseParseError):
        frames[0].to_event()


def test_valid_stream_passes_contract_checks() -> None:
    checks = _run_checks(E2ECase(id="smoke", message="hi"), _valid_stream())

    assert _status(checks, "sse_event_ids") == STATUS_PASSED
    assert _status(checks, "sse_terminal") == STATUS_PASSED
    assert _status(checks, "sse_schema_version") == STATUS_PASSED


def test_unknown_event_type_fails() -> None:
    blocks = [
        _frame_text("token", {"text": "你好"}, 1),
        "id: 2\nevent: debug\ndata: {\"schema_version\":\"1\"}\n\n",
        _frame_text("done", {"thread_id": "t-1"}, 3),
    ]

    checks = _run_checks(E2ECase(id="unknown", message="hi"), blocks)

    assert _status(checks, "sse_event_types") == STATUS_FAILED


def test_missing_done_fails_terminal_check() -> None:
    checks = _run_checks(
        E2ECase(id="incomplete", message="hi"),
        [_frame_text("token", {"text": "你好"}, 1)],
    )

    assert _status(checks, "sse_terminal") == STATUS_FAILED


def test_event_ids_must_start_at_one() -> None:
    blocks = [
        _frame_text("token", {"text": "你好"}, 2),
        _frame_text("done", {"thread_id": "t-1"}, 3),
    ]

    checks = _run_checks(E2ECase(id="ids", message="hi"), blocks)

    assert _status(checks, "sse_event_ids") == STATUS_FAILED


def test_build_result_price_mismatch_fails() -> None:
    build = _fake_build()
    build["total_price_fen"] = 1

    checks = _run_checks(
        E2ECase(id="price", message="hi"), _valid_stream(build_result=build)
    )

    assert _status(checks, "build_categories") == STATUS_PASSED
    assert _status(checks, "price_consistency") == STATUS_FAILED


def test_unknown_compatibility_must_not_be_claimed_as_pass() -> None:
    build = _fake_build()
    build["overall_status"] = "UNKNOWN"
    blocks = [
        _frame_text("token", {"text": "兼容性通过，可以放心下单。"}, 1),
        _frame_text("done", {"thread_id": "t-1", "build_result": build}, 2),
    ]

    checks = _run_checks(E2ECase(id="unknown-status", message="hi"), blocks)

    assert _status(checks, "compatibility_claims") == STATUS_FAILED


def test_baseline_cases_load() -> None:
    cases = load_e2e_cases(CASES_DIRECTORY)

    assert {case.id for case in cases} >= {
        "e2e_contract_smoke",
        "e2e_pc_build_contract",
        "e2e_hitl_clarify",
    }
    hitl = next(case for case in cases if case.id == "e2e_hitl_clarify")
    assert hitl.expect.terminal == "interrupt"
    assert hitl.resume is not None
    assert hitl.resume.answer["budget_yuan"] == 8000


def test_interrupt_id_is_extracted_from_event() -> None:
    blocks = [
        _frame_text(
            "interrupt",
            {
                "interrupt_id": "int-1",
                "interaction_type": "clarify_requirements",
                "question": "还缺预算",
                "input_schema": {"fields": []},
            },
            1,
        )
    ]
    events, errors = parse_events(parse_frames("".join(blocks).splitlines()))
    assert errors == []

    assert interrupt_id(events) == "int-1"


def test_interrupt_terminal_passes_order_check_without_tokens() -> None:
    case = E2ECase(
        id="hitl", message="hi", expect=E2EExpectation(terminal="interrupt")
    )
    blocks = [
        _frame_text(
            "interrupt",
            {
                "interrupt_id": "int-1",
                "interaction_type": "clarify_requirements",
                "question": "还缺预算",
                "input_schema": {"fields": []},
            },
            1,
        )
    ]

    checks = _run_checks(case, blocks)

    assert _status(checks, "sse_terminal") == STATUS_PASSED
    assert _status(checks, "sse_event_order") == STATUS_PASSED


def test_empty_case_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(E2ECaseLoadError):
        load_e2e_cases(tmp_path)
