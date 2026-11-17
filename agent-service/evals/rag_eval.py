"""RAG 离线检索评测：recall@5 与 MRR@5。

检索器经 `app.rag.registry` 获取，与生产同源，不另写一套装配。
RAG 未启用或检索器构造失败时整组跳过并以 0 退出——此时没有任何检索证据，
不能把「没跑」伪装成「通过」。单条查询异常只记为该条未命中，不中断整组。

    python -m evals.rag_eval --cases evals/rag_cases/rag-baseline.yaml
    python -m evals.rag_eval --cases evals/rag_cases/rag-baseline.yaml --json

退出码：0 达标或跳过；1 指标未达阈值；2 查询集缺失或非法。
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.agent.registry import redact_sensitive_text
from app.core.config import get_settings
from app.rag.base import Citation, RetrievalRequest, Retriever
from app.rag.registry import ensure_retriever_loaded
from evals.schema import CASE_ID_PATTERN

DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "rag_cases" / "rag-baseline.yaml"

RECALL_K = 5
# 评测只读公共知识卡；权限过滤仍由检索器按角色执行，这里给普通用户最小权限
EVAL_USER_ROLES = ("USER",)
# 生产检索器的 `Citation.source_id` 存的是 chunk_id（document_id#hash）
CHUNK_ID_SEPARATOR = "#"
ERROR_PREVIEW_CHARS = 200

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

CaseId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
QueryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
SourceId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
]


class RagCaseLoadError(RuntimeError):
    """查询集缺失或非法；消息必须能定位到文件与条目。"""


class RagCase(BaseModel):
    """一条检索查询及其期望来源（知识卡 document_id）。"""

    model_config = ConfigDict(extra="forbid")

    id: CaseId
    query: QueryText
    expected_source_ids: tuple[SourceId, ...] = Field(min_length=1, max_length=2)
    note: str = Field(default="", max_length=200)


@dataclass(frozen=True)
class RagCaseResult:
    """一条查询的结果；`rank` 为空表示未命中（含检索异常）。"""

    case_id: str
    expected_source_ids: tuple[str, ...]
    rank: int | None = None
    matched_source_id: str | None = None
    top_source_ids: tuple[str, ...] = ()
    error: str | None = None

    @property
    def is_hit(self) -> bool:
        return self.rank is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "status": "hit" if self.is_hit else "miss",
            "expected_source_ids": list(self.expected_source_ids),
            "rank": self.rank,
            "matched_source_id": self.matched_source_id,
            "top_source_ids": list(self.top_source_ids),
            "error": self.error,
        }


@dataclass(frozen=True)
class RagEvalReport:
    """一次评测的汇总；缺样本时指标按 0 计，不编造分母。"""

    results: tuple[RagCaseResult, ...]
    duration_ms: int = 0
    min_recall: float = 0.8
    min_mrr: float = 0.6

    @property
    def hits(self) -> int:
        return sum(1 for result in self.results if result.is_hit)

    @property
    def recall_at_5(self) -> float:
        return self.hits / len(self.results) if self.results else 0.0

    @property
    def mrr_at_5(self) -> float:
        if not self.results:
            return 0.0
        total = sum(
            1 / result.rank
            for result in self.results
            if result.rank is not None
        )
        return total / len(self.results)

    @property
    def is_below_threshold(self) -> bool:
        return self.recall_at_5 < self.min_recall or self.mrr_at_5 < self.min_mrr

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "completed",
            "duration_ms": self.duration_ms,
            "summary": {
                "total": len(self.results),
                "hits": self.hits,
                "recall_at_5": round(self.recall_at_5, 4),
                "mrr_at_5": round(self.mrr_at_5, 4),
                "min_recall": self.min_recall,
                "min_mrr": self.min_mrr,
                "passed": not self.is_below_threshold,
            },
            "cases": [result.to_dict() for result in self.results],
        }

    def render_text(self) -> str:
        verdict = "未达标" if self.is_below_threshold else "达标"
        lines = [
            "RAG 检索评测（recall@5 / MRR@5）",
            (
                f"用例 {len(self.results)} 条：命中 {self.hits}"
                f" ｜ recall@5 {self.recall_at_5:.4f}"
                f" ｜ MRR@5 {self.mrr_at_5:.4f}"
                f" ｜ 阈值 recall≥{self.min_recall:.2f}、MRR≥{self.min_mrr:.2f}"
                f" ｜ {verdict} ｜ 耗时 {self.duration_ms}ms"
            ),
            "",
        ]
        for result in self.results:
            lines.append(_render_case(result))
        return "\n".join(lines)


def _render_case(result: RagCaseResult) -> str:
    if result.is_hit:
        return (
            f"[命中] {result.case_id} rank={result.rank}"
            f" source={result.matched_source_id}"
        )
    if result.error is not None:
        detail = f"检索失败：{result.error}"
    else:
        top_ids = ", ".join(result.top_source_ids) or "无结果"
        detail = f"实际 top5：{top_ids}"
    expected = " / ".join(result.expected_source_ids)
    return f"[未命中] {result.case_id} 期望 {expected}；{detail}"


def _format_validation_error(exc: ValidationError) -> str:
    """压成「字段: 原因」，便于直接改 YAML。"""
    details = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        details.append(f"{location}: {error['msg']}")
    return "；".join(details)


def load_rag_cases(path: Path) -> list[RagCase]:
    """加载单份 YAML 查询集；路径、YAML 与字段错误都抛 `RagCaseLoadError`。"""
    if not path.is_file():
        raise RagCaseLoadError(f"查询集不存在：{path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RagCaseLoadError(f"查询集 {path.name} 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, list):
        raise RagCaseLoadError(f"查询集 {path.name} 必须是 YAML 列表（每条一个查询）")

    cases: list[RagCase] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        try:
            case = RagCase.model_validate(item)
        except ValidationError as exc:
            raise RagCaseLoadError(
                f"查询集 {path.name} 第 {index} 条校验失败：{_format_validation_error(exc)}"
            ) from exc
        if not CASE_ID_PATTERN.fullmatch(case.id):
            raise RagCaseLoadError(
                f"查询集 {path.name} 第 {index} 条的 id 非法：{case.id}"
            )
        if case.id in seen:
            raise RagCaseLoadError(f"查询集 {path.name} 的 id 重复：{case.id}")
        seen.add(case.id)
        cases.append(case)

    if not cases:
        raise RagCaseLoadError(f"查询集为空：{path}")
    return cases


def _preview(text: str) -> str:
    """异常文本可能带上游地址：限长并脱敏后再进报告。"""
    cleaned = redact_sensitive_text(text).replace("\n", " ")
    if len(cleaned) <= ERROR_PREVIEW_CHARS:
        return cleaned
    return f"{cleaned[:ERROR_PREVIEW_CHARS]}…"


def resolve_retriever() -> tuple[Retriever | None, str | None]:
    """返回 (检索器, 跳过原因)；未启用或构造失败时检索器为 None。"""
    if not get_settings().rag.enabled:
        return None, "RAG 未启用（RAG__ENABLED=false），检索指标无法计算"
    try:
        return ensure_retriever_loaded(), None
    except Exception as exc:  # 构造失败属于环境未就绪，与检索质量不达标区分
        return None, f"检索器构造失败（{type(exc).__name__}）：{_preview(str(exc))}"


def _document_id(source_id: str) -> str:
    """取 source_id 的文档段；生产 chunk_id 形如 `document_id#hash`。"""
    return source_id.split(CHUNK_ID_SEPARATOR, 1)[0]


def _build_result(
    case: RagCase, citations: Sequence[Citation], limit: int
) -> RagCaseResult:
    """按 top-k 内首个命中的期望来源记 rank；同卡多切片只算一次命中。"""
    expected = set(case.expected_source_ids)
    top_sources = [
        (citation.source_id, _document_id(citation.source_id))
        for citation in citations[:limit]
    ]
    top_ids = tuple(document_id for _, document_id in top_sources)
    for rank, (raw_source_id, document_id) in enumerate(top_sources, start=1):
        if document_id in expected:
            return RagCaseResult(
                case_id=case.id,
                expected_source_ids=case.expected_source_ids,
                rank=rank,
                matched_source_id=raw_source_id,
                top_source_ids=top_ids,
            )
    return RagCaseResult(
        case_id=case.id,
        expected_source_ids=case.expected_source_ids,
        top_source_ids=top_ids,
    )


async def _evaluate_case(
    case: RagCase,
    retriever: Retriever,
    *,
    user_id: str,
    roles: tuple[str, ...],
    limit: int,
) -> RagCaseResult:
    request = RetrievalRequest(
        query=case.query, user_id=user_id, roles=roles, limit=limit
    )
    try:
        citations = await retriever.retrieve(request)
    except Exception as exc:  # 单条失败只记该条未命中，不能拖垮整组
        return RagCaseResult(
            case_id=case.id,
            expected_source_ids=case.expected_source_ids,
            error=f"{type(exc).__name__}: {_preview(str(exc))}",
        )
    return _build_result(case, citations, limit)


async def evaluate_cases(
    cases: Sequence[RagCase],
    retriever: Retriever,
    *,
    user_id: str,
    roles: tuple[str, ...] = EVAL_USER_ROLES,
    limit: int = RECALL_K,
) -> list[RagCaseResult]:
    """顺序执行；检索器是外部服务，串行便于定位单条异常。"""
    return [
        await _evaluate_case(
            case, retriever, user_id=user_id, roles=roles, limit=limit
        )
        for case in cases
    ]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.rag_eval",
        description="用查询集验证 RAG 检索质量；未启用检索器时整组跳过。",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="查询集 YAML，默认 evals/rag_cases/rag-baseline.yaml",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 结构化结果，便于 CI 归档或二次处理",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.8,
        help="recall@5 阈值，默认 0.8",
    )
    parser.add_argument(
        "--min-mrr",
        type=float,
        default=0.6,
        help="MRR@5 阈值，默认 0.6",
    )
    return parser


def _emit_skipped(reason: str, as_json: bool) -> None:
    if as_json:
        payload = {"status": "skipped", "reason": reason}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"RAG 评测已跳过：{reason}")


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        # psycopg 异步驱动不支持 Windows 默认的 ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = _build_parser().parse_args(argv)

    try:
        cases = load_rag_cases(args.cases)
    except RagCaseLoadError as exc:
        print(f"查询集加载失败：{exc}", file=sys.stderr)
        return EXIT_USAGE

    retriever, skip_reason = resolve_retriever()
    if retriever is None:
        _emit_skipped(skip_reason or "检索器不可用", args.json)
        return EXIT_OK

    started_at = perf_counter()
    results = asyncio.run(
        evaluate_cases(cases, retriever, user_id=get_settings().evals.user_id)
    )
    report = RagEvalReport(
        results=tuple(results),
        duration_ms=int((perf_counter() - started_at) * 1000),
        min_recall=args.min_recall,
        min_mrr=args.min_mrr,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.render_text())

    return EXIT_FAILED if report.is_below_threshold else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
