"""把管理端导出的反馈 CSV 转成评测用例草稿。

用法（仓库根执行）：

    uv --directory agent-service run python scripts/feedback/export_eval_cases.py feedback-20261110.csv

设计取舍：

* 只处理「踩」。点赞不构成需要修复的期望，自动转成用例只会稀释评测集。
* 草稿写入 ``agent-service/evals/cases-pending/``，**不直接写 cases/**：
  自动补 ``expect`` 等于编造期望，必须由人补上真实断言后手动移入 ``cases/``。
* 用户输入从 Agent 自己的 ``session_messages`` 取「该助手消息之前最近的一条用户消息」，
  连不上数据库或消息已被删除时跳过并在终端汇总，不生成半成品用例。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

DOWN_LABEL = "踩"
MAX_EVAL_INPUT_CHARS = 4000

# CSV 表头由 MessageFeedbackService.CSV_HEADER 固定，改名会导致这里直接报错而不是静默丢列
COLUMN_USER = "用户"
COLUMN_USER_ID = "用户ID"
COLUMN_THREAD = "会话"
COLUMN_MESSAGE = "消息ID"
COLUMN_RATING = "评分"
COLUMN_REASON = "原因"
COLUMN_COMMENT = "备注"
REQUIRED_COLUMNS = (
    COLUMN_USER,
    COLUMN_USER_ID,
    COLUMN_THREAD,
    COLUMN_MESSAGE,
    COLUMN_RATING,
    COLUMN_REASON,
    COLUMN_COMMENT,
)

REASON_BY_LABEL: dict[str, str] = {
    "信息不准确": "INACCURATE",
    "答非所问": "OFF_TOPIC",
    "回答不完整": "INCOMPLETE",
    "格式混乱": "FORMAT",
    "内容不当": "UNSAFE",
    "其他": "OTHER",
}
"""CSV 里存的是中文标签，草稿注释保持中文；保留枚举映射便于人工核对分类。"""

PREVIOUS_USER_SQL = """
SELECT content
FROM session_messages
WHERE user_id = %s AND thread_id = %s AND seq < %s AND role = 'user'
ORDER BY seq DESC
LIMIT 1
"""


@dataclass(frozen=True)
class FeedbackRow:
    """CSV 中一条「踩」反馈；只保留生成用例需要的字段。"""

    username: str
    user_id: str
    thread_id: str
    message_id: str
    reason_label: str
    comment: str


@dataclass(frozen=True)
class DraftCase:
    """一条待人工补全的用例草稿。"""

    case_id: str
    input_text: str
    reason_label: str
    comment: str
    thread_id: str
    message_id: str
    username: str


def parse_argsv(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="反馈 CSV → 评测用例草稿")
    parser.add_argument("csv_path", type=Path, help="管理端导出的 feedback-*.csv")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="草稿目录，默认 agent-service/evals/cases-pending",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Agent 库连接串；默认读 AGENT_EVAL_POSTGRES_URL / STORAGE__POSTGRES_URL",
    )
    return parser.parse_args(argv)


def read_feedback(csv_path: Path) -> list[FeedbackRow]:
    """读取 CSV，只保留评分是「踩」的行。"""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"CSV 缺少列：{'、'.join(missing)}；请使用管理端「导出 CSV」原文件")

        rows: list[FeedbackRow] = []
        for record in reader:
            if (record.get(COLUMN_RATING) or "").strip() != DOWN_LABEL:
                continue
            rows.append(
                FeedbackRow(
                    username=(record.get(COLUMN_USER) or "").strip(),
                    user_id=(record.get(COLUMN_USER_ID) or "").strip(),
                    thread_id=(record.get(COLUMN_THREAD) or "").strip(),
                    message_id=(record.get(COLUMN_MESSAGE) or "").strip(),
                    reason_label=(record.get(COLUMN_REASON) or "").strip(),
                    comment=(record.get(COLUMN_COMMENT) or "").strip(),
                )
            )
        return rows


def split_message_id(message_id: str) -> tuple[str, int] | None:
    """`{thread_id}:{seq}` → (thread_id, seq)；格式不符返回 None。"""
    thread_id, separator, raw_seq = message_id.rpartition(":")
    if not separator or not thread_id.isascii():
        return None
    try:
        return thread_id, int(raw_seq)
    except ValueError:
        return None


def load_previous_inputs(dsn: str, rows: list[FeedbackRow]) -> dict[str, str]:
    """批量取每条反馈对应的用户输入，键为 message_id。"""
    try:
        import psycopg
    except ImportError:  # pragma: no cover - 依赖缺失时给出可操作提示
        print("未安装 psycopg，无法关联会话正文；请使用 uv --directory agent-service run 执行", file=sys.stderr)
        return {}

    inputs: dict[str, str] = {}
    try:
        with psycopg.connect(dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                for row in rows:
                    parsed = split_message_id(row.message_id)
                    if parsed is None:
                        continue
                    thread_id, seq = parsed
                    cursor.execute(PREVIOUS_USER_SQL, (row.user_id, thread_id, seq))
                    found = cursor.fetchone()
                    if found and found[0].strip():
                        inputs[row.message_id] = found[0]
    except Exception as exc:  # noqa: BLE001 - 连不上库只需降级为「无正文」并提示原因
        print(f"关联会话正文失败：{exc}", file=sys.stderr)
        return {}
    return inputs


def build_drafts(
    rows: list[FeedbackRow], inputs: dict[str, str]
) -> tuple[list[DraftCase], dict[str, int]]:
    """按 message_id 去重（同一消息可能被覆盖多次），生成草稿与跳过统计。"""
    skipped = {"无会话正文": 0, "输入过长": 0, "消息ID非法": 0}
    drafts: list[DraftCase] = []
    seen: set[str] = set()

    for row in rows:
        if row.message_id in seen:
            continue
        seen.add(row.message_id)

        if split_message_id(row.message_id) is None:
            skipped["消息ID非法"] += 1
            continue
        input_text = inputs.get(row.message_id)
        if input_text is None:
            skipped["无会话正文"] += 1
            continue
        if len(input_text) > MAX_EVAL_INPUT_CHARS:
            skipped["输入过长"] += 1
            continue

        drafts.append(
            DraftCase(
                case_id=f"fb_{len(drafts) + 1:03d}",
                input_text=input_text,
                reason_label=row.reason_label,
                comment=row.comment,
                thread_id=row.thread_id,
                message_id=row.message_id,
                username=row.username,
            )
        )
    return drafts, skipped


def render_yaml(drafts: list[DraftCase], source_name: str) -> str:
    """手写 YAML，保留元信息注释；`expect` 留空并标注 TODO。"""
    lines = [
        "# 由 scripts/feedback/export_eval_cases.py 生成的反馈草稿。",
        f"# 来源：{source_name}",
        "# 使用方式：补全 expect（至少一项断言）后移动到 agent-service/evals/cases/。",
        "# 注意：这里刻意不预填断言，自动编造的期望会让评测失去意义。",
        "",
    ]
    for draft in drafts:
        reason = draft.reason_label or "未选择原因"
        lines.append(f"- id: {draft.case_id}")
        lines.append(f"  # 反馈：踩 / {reason}（{REASON_BY_LABEL.get(reason, 'UNKNOWN')}）" + (f"：{draft.comment}" if draft.comment else ""))
        lines.append(f"  # 来源：用户={draft.username or '未知'} 会话={draft.thread_id} 消息={draft.message_id}")
        lines.append(f"  input: {json.dumps(draft.input_text, ensure_ascii=False)}")
        lines.append("  expect: {}  # TODO: 至少补一项断言，如 must_not_contain / workflow_status")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_argsv(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = args.output_dir or repo_root / "agent-service" / "evals" / "cases-pending"
    dsn = args.dsn or os.environ.get("AGENT_EVAL_POSTGRES_URL") or os.environ.get("STORAGE__POSTGRES_URL")

    rows = read_feedback(args.csv_path)
    if not rows:
        print("CSV 中没有「踩」记录，无需生成草稿。")
        return 0

    inputs = load_previous_inputs(dsn, rows) if dsn else {}
    if not dsn:
        print("未提供数据库连接串（--dsn 或 AGENT_EVAL_POSTGRES_URL），草稿将缺少用户输入。", file=sys.stderr)

    drafts, skipped = build_drafts(rows, inputs)
    if not drafts:
        print(f"没有可生成的草稿：{skipped}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    # 沿用 CSV 文件名（feedback-<时间戳>），批次与来源一一对应，重复执行会覆盖同一批草稿
    target = output_dir / f"{args.csv_path.stem}.yaml"
    target.write_text(render_yaml(drafts, args.csv_path.name), encoding="utf-8")

    print(f"已生成 {len(drafts)} 条草稿：{target}")
    print(f"跳过：{skipped}")
    print("下一步：人工补全 expect 后移动到 agent-service/evals/cases/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
