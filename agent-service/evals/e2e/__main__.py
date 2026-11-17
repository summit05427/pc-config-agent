"""E2E 评测入口。

    python -m evals.e2e --mode local    # CI：进程内 ASGI + 确定性假图，零费用
    python -m evals.e2e --mode service  # 人工：真实登录 + HTTP/SSE，产生 token 费用

退出码：0 全部通过；1 存在失败用例或环境不可用；2 用例/用法错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

from evals.e2e.schema import E2ECase, E2ECaseLoadError, load_e2e_cases
from evals.report import (
    MODE_E2E_LOCAL,
    MODE_E2E_SERVICE,
    EvalReport,
)

DEFAULT_CASES_DIRECTORY = Path(__file__).resolve().parent / "cases"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

MODE_LOCAL = "local"
MODE_SERVICE = "service"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.e2e",
        description="HTTP/SSE 端到端评测；默认本地契约模式，不调用真实模型。",
    )
    parser.add_argument(
        "--mode",
        choices=(MODE_LOCAL, MODE_SERVICE),
        default=MODE_LOCAL,
        help="local=进程内契约（默认，零费用）；service=真实服务（登录 + 真实模型）",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_DIRECTORY,
        help="用例目录，默认 evals/e2e/cases",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        metavar="ID",
        help="只运行指定用例，可重复；未知 id 按用法错误退出",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 结构化报告，便于 CI 归档",
    )
    return parser


def _select_cases(
    cases: list[E2ECase], case_ids: list[str]
) -> tuple[list[E2ECase], list[str]]:
    wanted = set(case_ids)
    selected = [case for case in cases if case.id in wanted]
    found = {case.id for case in selected}
    missing = [case_id for case_id in dict.fromkeys(case_ids) if case_id not in found]
    return selected, missing


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        cases = load_e2e_cases(args.cases)
    except E2ECaseLoadError as exc:
        print(f"用例加载失败：{exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.case_id:
        cases, missing = _select_cases(cases, args.case_id)
        if missing:
            print(f"未知用例 id：{'、'.join(missing)}", file=sys.stderr)
            return EXIT_USAGE

    started_at = perf_counter()
    if args.mode == MODE_SERVICE:
        from evals.e2e.client import E2EClientError, E2EUsageError
        from evals.e2e.runner import run_service_cases

        try:
            results = run_service_cases(cases)
        except E2EUsageError as exc:
            print(f"配置缺失：{exc}", file=sys.stderr)
            return EXIT_USAGE
        except E2EClientError as exc:
            # 登录或网络不可达属于环境问题，不能伪装成用例失败
            print(f"环境不可用：{exc}", file=sys.stderr)
            return EXIT_FAILED
        mode = MODE_E2E_SERVICE
    else:
        # 延迟导入：local 模块会先覆盖环境变量再导入 app，顺序不能提前
        from evals.e2e.local import run_local_cases

        results = run_local_cases(cases)
        mode = MODE_E2E_LOCAL

    report = EvalReport(
        mode=mode,
        results=results,
        duration_ms=int((perf_counter() - started_at) * 1000),
        currency=_currency(),
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.render_text())
    return EXIT_FAILED if report.has_failures else EXIT_OK


def _currency() -> str:
    """成本币种随评测配置走；local 模式也在覆盖环境后读取，保持口径一致。"""
    from app.core.config import get_settings

    return get_settings().evals.price_currency


if __name__ == "__main__":
    raise SystemExit(main())
