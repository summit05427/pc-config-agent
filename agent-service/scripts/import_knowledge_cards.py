"""导入知识卡片到 agent_service 的 RAG 表。

用法（需能访问 agent_service 的 Postgres，且已配置 embedding 模型）：
    uv run python scripts/import_knowledge_cards.py --dry-run
    uv run python scripts/import_knowledge_cards.py
    uv run python scripts/import_knowledge_cards.py knowledge/cards

脚本幂等：卡片指纹未变化的文档会跳过；正文或元数据变化时替换该文档的全部切片。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
# 直接执行 scripts/xxx.py 时 sys.path[0] 是 scripts/，补上服务根目录才能 import app
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.rag.knowledge.chunking import MAX_CHUNK_CHARS, chunk_card  # noqa: E402
from app.rag.knowledge.embedding import build_embedder  # noqa: E402
from app.rag.knowledge.importing import import_cards, load_cards  # noqa: E402
from app.rag.knowledge.repository import create_repository  # noqa: E402

DEFAULT_CARD_DIR = SERVICE_ROOT / "knowledge" / "cards"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 RAG 知识卡片")
    parser.add_argument(
        "paths",
        nargs="*",
        help=f"Markdown/JSON 卡片文件或目录；默认 {DEFAULT_CARD_DIR}",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计切片，不写库")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=MAX_CHUNK_CHARS,
        help=f"单切片最大字符数（默认 {MAX_CHUNK_CHARS}）",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    paths = [Path(item) for item in args.paths] or [DEFAULT_CARD_DIR]
    cards = load_cards(paths)
    if args.dry_run:
        chunk_count = sum(
            len(chunk_card(card, max_chars=args.max_chars)) for card in cards
        )
        print(f"卡片 {len(cards)} 张，切片 {chunk_count} 条（dry-run，未写库）")
        return

    settings = get_settings()
    embedder = build_embedder(settings)
    repository = create_repository(settings)
    try:
        await repository.setup()
        report = await import_cards(
            repository,
            cards,
            embedder,
            max_chars=args.max_chars,
        )
        print(
            f"导入完成：新增 {report.imported}，更新 {report.updated}，"
            f"跳过 {report.skipped}，写入切片 {report.chunks_written}"
        )
    finally:
        await repository.aclose()


def main() -> None:
    if sys.platform == "win32":
        # psycopg 异步驱动不支持 Windows 默认的 ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()
