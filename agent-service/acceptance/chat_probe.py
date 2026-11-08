"""联调探针：签发开发令牌并输出一次真实 SSE 对话的结构化摘要。

输出为单行 JSON（UTF-8），避免 PowerShell 对中文请求体/响应的编码干扰：

- `event_types`：按出现顺序的事件名；
- `text`：拼接后的正文；
- `citations`：`citations` 事件的引用列表；
- `schema_versions`：出现过的事件版本号；
- `error`：流内 `error` 事件负载。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
MAX_TIMEOUT_SECONDS = 300.0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="阶段 3 联调探针")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--user-id", default="acceptance-user")
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--message", default="")
    parser.add_argument("--message-file", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=180.0)
    return parser.parse_args()


def _read_message(args: argparse.Namespace) -> str:
    if args.message_file is not None:
        return args.message_file.read_text(encoding="utf-8")
    return args.message


async def _run(args: argparse.Namespace) -> int:
    message = _read_message(args)
    result: dict[str, Any] = {"thread_id": args.thread_id, "message_chars": len(message)}
    timeout = min(args.timeout, MAX_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        token_response = await client.post(
            f"{args.base_url}/api/v1/auth/dev-token",
            json={"user_id": args.user_id},
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]

        event_types: list[str] = []
        text = ""
        citations: list[dict[str, Any]] = []
        schema_versions: set[str] = set()
        stream_error: dict[str, Any] | None = None
        current_event: str | None = None

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
        }
        async with client.stream(
            "POST",
            f"{args.base_url}/api/v1/chat/stream",
            json={"message": message, "thread_id": args.thread_id},
            headers=headers,
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace")
                result["http_status"] = response.status_code
                result["body"] = body
                print(json.dumps(result, ensure_ascii=False))
                return 1

            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    current_event = line.removeprefix("event:").strip()
                    continue
                if not line.startswith("data:") or current_event is None:
                    continue

                payload = json.loads(line.removeprefix("data:").strip())
                event_types.append(current_event)
                if "schema_version" in payload:
                    schema_versions.add(str(payload["schema_version"]))
                if current_event == "token":
                    text += str(payload.get("text", ""))
                elif current_event == "citations":
                    citations = list(payload.get("citations", []))
                elif current_event == "error":
                    stream_error = payload
                current_event = None

    result.update(
        {
            "event_types": event_types,
            "text": text,
            "citations": citations,
            "schema_versions": sorted(schema_versions),
            "error": stream_error,
        }
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    return asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
