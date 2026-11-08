"""一次性回填 `session_meta`（PR 7）。

背景：会话列表此前来自 Redis 有序集合，没有标题；切换为 Postgres 后，
历史会话在 `session_messages` 里存在但 `session_meta` 里没有对应行，
列表会看不到这些会话。本脚本按 `session_messages` 反推元数据并回填。

用法（容器内或本地，需能访问 agent 的 Postgres）：

    python scripts/backfill_session_meta.py --dry-run   # 先看影响行数
    python scripts/backfill_session_meta.py             # 实际写入

脚本幂等：已存在的 (user_id, thread_id) 不会被覆盖，可重复执行。
"""

from __future__ import annotations

import argparse

import psycopg

from app.core.config import get_settings
from app.services.session_store.postgres import CREATE_META_INDEX_SQL, CREATE_META_TABLE_SQL

# 每个会话的首条用户消息；DISTINCT ON 保证每个会话只取一行
TITLE_SQL = """
SELECT DISTINCT ON (user_id, thread_id) user_id, thread_id, content
FROM session_messages
WHERE role = 'user'
ORDER BY user_id, thread_id, seq
"""

SPAN_SQL = """
SELECT user_id, thread_id, MIN(created_at), MAX(created_at)
FROM session_messages
GROUP BY user_id, thread_id
"""

INSERT_SQL = """
INSERT INTO session_meta (user_id, thread_id, title, created_at, updated_at, last_active_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (user_id, thread_id) DO NOTHING
"""

AUTO_TITLE_LENGTH = 40


def _derive_title(content: str) -> str | None:
    title = content.strip()
    return title[:AUTO_TITLE_LENGTH] or None


def main() -> None:
    parser = argparse.ArgumentParser(description="回填 session_meta")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    settings = get_settings()
    if settings.storage.backend != "postgres" or settings.storage.postgres_url is None:
        raise RuntimeError("需要 STORAGE__BACKEND=postgres 且配置 STORAGE__POSTGRES_URL")

    with psycopg.connect(settings.storage.postgres_url.get_secret_value()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CREATE_META_TABLE_SQL)
            cursor.execute(CREATE_META_INDEX_SQL)
            cursor.execute(SPAN_SQL)
            spans = {
                (user_id, thread_id): (first_at, last_at)
                for user_id, thread_id, first_at, last_at in cursor.fetchall()
            }
            cursor.execute(TITLE_SQL)
            titles = {
                (user_id, thread_id): _derive_title(content)
                for user_id, thread_id, content in cursor.fetchall()
            }

            rows = [
                (
                    user_id,
                    thread_id,
                    titles.get((user_id, thread_id)),
                    first_at,
                    last_at,
                    last_at,
                )
                for (user_id, thread_id), (first_at, last_at) in spans.items()
            ]

            if args.dry_run:
                print(f"待回填会话数：{len(rows)}")
                return

            cursor.executemany(INSERT_SQL, rows)
        connection.commit()
    print(f"已回填会话数：{len(rows)}")


if __name__ == "__main__":
    main()
