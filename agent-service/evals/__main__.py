"""评测入口。

    python -m evals --fake   # CI：零 API 费用，只校验图结构与工具绑定
    python -m evals --real   # 手动：真实调用模型，产生 token 费用

退出码：0 全部校验通过；1 存在失败用例；2 用例文件缺失或非法。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

from app.core.config import get_settings
from evals.report import MODE_FAKE, MODE_REAL, EvalReport
from evals.runners.fake_model import run_cases as run_fake_cases
from evals.schema import CaseLoadError, EvalCase, load_cases

DEFAULT_CASES_DIRECTORY = Path(__file__).resolve().parent / "cases"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals",
        description="按 YAML 用例验证 Agent；默认假模型模式，零 API 费用。",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fake",
        action="store_true",
        help="只校验 Profile、工具绑定与图结构（默认）",
    )
    mode.add_argument(
        "--real",
        action="store_true",
        help="真实调用模型并校验回答内容，会产生 token 费用",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_DIRECTORY,
        help="用例目录，默认 evals/cases",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        metavar="ID",
        help="只运行指定用例，可重复；未知 id 直接按用法错误退出",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 结构化报告，便于 CI 归档或二次处理",
    )
    return parser


def _select_cases(
    cases: list[EvalCase], case_ids: list[str]
) -> tuple[list[EvalCase], list[str]]:
    """按 id 过滤并保持原有顺序；返回未命中的 id，便于调用方按用法错误处理。"""
    wanted = set(case_ids)
    selected = [case for case in cases if case.id in wanted]
    found = {case.id for case in selected}
    missing = [case_id for case_id in dict.fromkeys(case_ids) if case_id not in found]
    return selected, missing


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        cases = load_cases(args.cases)
    except CaseLoadError as exc:
        print(f"用例加载失败：{exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.case_id:
        cases, missing = _select_cases(cases, args.case_id)
        if missing:
            print(f"未知用例 id：{'、'.join(missing)}", file=sys.stderr)
            return EXIT_USAGE

    started_at = perf_counter()
    if args.real:
        # psycopg 异步驱动只支持 SelectorEventLoop；真实评测里的 search_knowledge 会连库，
        # Windows 默认 Proactor 会让工具连续超时，必须与 run.py / rag_eval 保持一致。
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        # 延迟导入：假模型模式不需要装配真实模型与 Provider 适配器
        from evals.runners.real_model import run_cases as run_real_cases

        mode = MODE_REAL
        results = asyncio.run(run_real_cases(cases))
    else:
        mode = MODE_FAKE
        results = run_fake_cases(cases)

    report = EvalReport(
        mode=mode,
        results=results,
        duration_ms=int((perf_counter() - started_at) * 1000),
        currency=get_settings().evals.price_currency,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.render_text())

    return EXIT_FAILED if report.has_failures else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
