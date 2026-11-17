"""RAG 离线评测：指标口径、单条异常隔离与 skip 语义。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rag.base import Citation, RagConfigError, RetrievalRequest, Retriever
from evals import rag_eval
from evals.rag_eval import (
    RagCase,
    RagCaseLoadError,
    RagEvalReport,
    evaluate_cases,
    load_rag_cases,
)

CASES_WITH_TWO_QUERIES = """
- id: q1
  query: 问题一
  expected_source_ids: [kb-a]
- id: q2
  query: 问题二
  expected_source_ids: [kb-b]
"""


class _FakeRetriever:
    """测试替身：按 query 返回引用或抛异常，不依赖 embedding 与网络。"""

    def __init__(
        self, responses: dict[str, list[Citation] | Exception]
    ) -> None:
        self.responses = responses
        self.queries: list[str] = []

    async def retrieve(self, request: RetrievalRequest) -> list[Citation]:
        self.queries.append(request.query)
        response = self.responses.get(request.query, [])
        if isinstance(response, Exception):
            raise response
        return response


def _citation(source_id: str) -> Citation:
    """生产里的 source_id 是 chunk_id，形如 document_id#hash。"""
    return Citation(source_id=source_id, snippet="片段")


def _settings(enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        rag=SimpleNamespace(enabled=enabled),
        evals=SimpleNamespace(user_id="eval-user"),
    )


def _write_cases(directory: Path, content: str = CASES_WITH_TWO_QUERIES) -> Path:
    path = directory / "cases.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def _unexpected_retriever() -> Retriever:
    raise AssertionError("RAG 未启用时不得构造检索器")


def test_baseline_cases_are_loadable() -> None:
    """仓库自带的基线查询集必须可直接运行。"""
    cases = load_rag_cases(rag_eval.DEFAULT_CASES_PATH)

    assert len(cases) == 10
    assert all(case.expected_source_ids for case in cases)


def test_load_rag_cases_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RagCaseLoadError, match="不存在"):
        load_rag_cases(tmp_path / "missing.yaml")


def test_load_rag_cases_rejects_invalid_query(tmp_path: Path) -> None:
    path = _write_cases(
        tmp_path,
        "- id: empty_query\n  query: ''\n  expected_source_ids: [kb-a]\n",
    )

    with pytest.raises(RagCaseLoadError, match="校验失败"):
        load_rag_cases(path)


async def test_recall_and_mrr_use_first_matching_rank() -> None:
    """rank=3 的命中只贡献 1/3 MRR；未命中不贡献。"""
    cases = [
        RagCase(id="q1", query="问题一", expected_source_ids=("kb-a",)),
        RagCase(id="q2", query="问题二", expected_source_ids=("kb-b",)),
        RagCase(id="q3", query="问题三", expected_source_ids=("kb-c",)),
    ]
    retriever = _FakeRetriever(
        {
            "问题一": [_citation("kb-a#hash"), _citation("kb-x#hash")],
            "问题二": [
                _citation("kb-x#hash"),
                _citation("kb-y#hash"),
                _citation("kb-b#hash"),
            ],
            "问题三": [_citation("kb-x#hash")],
        }
    )

    results = await evaluate_cases(cases, retriever, user_id="eval-user")
    report = RagEvalReport(results=tuple(results))

    assert [result.rank for result in results] == [1, 3, None]
    # source_id 是 chunk_id，命中判定必须按 document_id 段比较
    assert results[0].matched_source_id == "kb-a#hash"
    assert report.recall_at_5 == pytest.approx(2 / 3)
    assert report.mrr_at_5 == pytest.approx((1 + 1 / 3) / 3)
    assert report.is_below_threshold


async def test_single_query_error_is_recorded_as_miss() -> None:
    """一条查询抛异常只记该条未命中，后续查询继续执行。"""
    cases = [
        RagCase(id="bad", query="坏查询", expected_source_ids=("kb-a",)),
        RagCase(id="good", query="好的查询", expected_source_ids=("kb-a",)),
    ]
    retriever = _FakeRetriever(
        {
            "坏查询": RuntimeError("向量库超时"),
            "好的查询": [_citation("kb-a#hash")],
        }
    )

    results = await evaluate_cases(cases, retriever, user_id="eval-user")
    report = RagEvalReport(results=tuple(results))

    assert retriever.queries == ["坏查询", "好的查询"]
    assert not results[0].is_hit
    assert results[0].error is not None
    assert "RuntimeError" in results[0].error
    assert results[1].is_hit
    assert report.recall_at_5 == 0.5
    assert "检索失败" in report.render_text()


def test_main_skips_when_rag_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """RAG 关闭时整组 skipped，退出码 0，且不构造检索器。"""
    cases_path = _write_cases(tmp_path)
    monkeypatch.setattr(rag_eval, "get_settings", lambda: _settings(False))
    monkeypatch.setattr(rag_eval, "ensure_retriever_loaded", _unexpected_retriever)

    exit_code = rag_eval.main(["--cases", str(cases_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "已跳过" in output
    assert "RAG__ENABLED=false" in output

    exit_code = rag_eval.main(["--cases", str(cases_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "skipped"


def test_main_skips_when_retriever_construction_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """检索器构造失败属于环境未就绪，按 skipped 处理而不是判失败。"""
    cases_path = _write_cases(tmp_path)

    def broken_retriever() -> Retriever:
        raise RagConfigError("embedding 模型未配置")

    monkeypatch.setattr(rag_eval, "get_settings", lambda: _settings(True))
    monkeypatch.setattr(rag_eval, "ensure_retriever_loaded", broken_retriever)

    exit_code = rag_eval.main(["--cases", str(cases_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "检索器构造失败" in output


def test_main_returns_one_when_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cases_path = _write_cases(tmp_path)
    retriever = _FakeRetriever({})
    monkeypatch.setattr(rag_eval, "get_settings", lambda: _settings(True))
    monkeypatch.setattr(rag_eval, "ensure_retriever_loaded", lambda: retriever)

    exit_code = rag_eval.main(["--cases", str(cases_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "未达标" in output
    assert retriever.queries == ["问题一", "问题二"]


def test_main_returns_zero_and_reports_metrics_when_threshold_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cases_path = _write_cases(tmp_path)
    retriever = _FakeRetriever(
        {
            "问题一": [_citation("kb-a#hash")],
            "问题二": [_citation("kb-b#hash")],
        }
    )
    monkeypatch.setattr(rag_eval, "get_settings", lambda: _settings(True))
    monkeypatch.setattr(rag_eval, "ensure_retriever_loaded", lambda: retriever)

    exit_code = rag_eval.main(["--cases", str(cases_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "completed"
    assert payload["summary"]["recall_at_5"] == 1.0
    assert payload["summary"]["mrr_at_5"] == 1.0
    assert payload["summary"]["passed"] is True
