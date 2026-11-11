"""按型号批量搜索淘宝，落盘原始商品列表；可断点续跑。

只调用 `taobao_search`，不读详情：一次搜索拿回 10 条商品，供离线匹配使用。
本轮用途：补齐 GPU 芯片级目录（现有 80 次搜索只覆盖了少数芯片）。

用法：
    python scripts/pc-config/harvest.py --plan gpu-extra
    python scripts/pc-config/harvest.py --plan default   # 复跑历史 80 次搜索
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pc_config_data import REPO_ROOT

OUT = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace" / "raw"
LOG_PATH = OUT.parent / "harvest.log"
MCP_CALL = Path(__file__).with_name("mcp_call.js")

NODE = os.environ.get("TAOBAO_NODE", r"E:\Nodejs\nodejs\node.exe")
LAUNCH = os.environ.get("TAOBAO_LAUNCH", r"F:\tools\chengkit-taobao\tools\opencli-launch.cjs")
LIMIT = 10
# 与 chengkit-taobao browser-guard 的 NORMAL_COOLDOWN_MS 保持一致（10 秒）。
COOLDOWN = 10

# 编号从 101 起，避免覆盖历史 01-80 的原始结果。
GPU_EXTRA_PLAN: list[tuple[str, str]] = [
    ("GPU", "RTX 5090 32G"),
    ("GPU", "RTX 5080 16G"),
    ("GPU", "RTX 5070 Ti 16G"),
    ("GPU", "RTX 5070 12G"),
    ("GPU", "RTX 5060 Ti 16G"),
    ("GPU", "RTX 5060 Ti 8G"),
    ("GPU", "RTX 5060 8G"),
    ("GPU", "RTX 5050 8G"),
    ("GPU", "RTX 4090 24G"),
    ("GPU", "RTX 4080 SUPER 16G"),
    ("GPU", "RTX 4080 16G"),
    ("GPU", "RTX 4070 Ti SUPER 16G"),
    ("GPU", "RTX 4070 Ti 12G"),
    ("GPU", "RTX 4070 SUPER 12G"),
    ("GPU", "RTX 4070 12G"),
    ("GPU", "RTX 4060 Ti 16G"),
    ("GPU", "RTX 4060 Ti 8G"),
    ("GPU", "RTX 4060 8G"),
    ("GPU", "RX 7900 XT 20G"),
    ("GPU", "RX 7800 XT 16G"),
    ("GPU", "RX 7700 XT 12G"),
    ("GPU", "RX 7600 XT 16G"),
    ("GPU", "RX 7600 8G"),
    ("GPU", "RX 9060 XT 16G"),
    ("GPU", "RX 9070 XT 16G"),
    ("GPU", "Arc B580 12G"),
    ("GPU", "Arc B570 10G"),
    ("GPU", "Arc A750 8G"),
]

LAST = [0.0]

# 补齐「多场景 × 多预算」缺口：入门主板/内存/显卡为主，避免只有高端件能拼整机。
ENTRY_PLAN: list[tuple[str, str]] = [
    ("MOTHERBOARD", "华硕 B760M-K 主板"),
    ("MOTHERBOARD", "微星 B760M 主板"),
    ("MOTHERBOARD", "技嘉 B760M 主板"),
    ("MOTHERBOARD", "华硕 Z790 主板"),
    ("MOTHERBOARD", "华硕 A620M 主板"),
    ("MEMORY", "金士顿 DDR5 16G 6000"),
    ("MEMORY", "威刚 DDR5 16G 6000"),
    ("GPU", "RTX 4060 8G"),
    ("GPU", "RX 7600 8G"),
    ("STORAGE", "三星 990 EVO 1TB"),
]

PLAN_START = {"gpu-extra": 101, "entry": 201}


def log(message: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def text_of(response: dict) -> str:
    return "\n".join(
        item.get("text") or ""
        for item in (response.get("result") or {}).get("content") or []
        if item.get("type") == "text"
    )


def payload(response: dict) -> dict | None:
    structured = (response.get("result") or {}).get("structuredContent")
    if isinstance(structured, dict):
        return structured
    raw = text_of(response)
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def wait_ready() -> None:
    subprocess.run([NODE, LAUNCH, "daemon", "restart"], timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(3)
        probe = subprocess.run([NODE, LAUNCH, "doctor"], capture_output=True,
                               text=True, timeout=60)
        if '"extensionConnected":true' in probe.stdout.replace(" ", ""):
            log("扩展已连接")
            return
    log("扩展未连接，仍尝试继续")


def call_search(query: str, out_path: Path) -> dict | None:
    args_path = OUT / "_args.json"
    args_path.write_text(
        json.dumps({"query": query, "limit": LIMIT, "include_images": False}, ensure_ascii=False),
        encoding="utf-8")
    wait = COOLDOWN - (time.time() - LAST[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(1, 4):
        try:
            subprocess.run([NODE, str(MCP_CALL), "taobao_search", str(args_path), str(out_path)],
                           timeout=300)
        except subprocess.TimeoutExpired:
            log(f"{query}: 超时")
        LAST[0] = time.time()
        try:
            response = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            response = {}
        data = payload(response)
        if data:
            return data
        raw = text_of(response)
        rate_limit = re.search(r"还需约 (\d+) 秒", raw)
        if rate_limit:
            pause = int(rate_limit.group(1)) + 2
            log(f"{query}: 冷却中，等待 {pause} 秒")
            time.sleep(pause)
            continue
        if "验证" in raw or "登录" in raw:
            log(f"{query}: 触发风控，停止 —— {raw[:100]}")
            sys.exit(2)
        log(f"{query}: 第 {attempt} 次无结果 —— {raw[:80]}")
        time.sleep(COOLDOWN)
    return None


def build_plan(name: str) -> list[tuple[str, str]]:
    if name == "gpu-extra":
        return GPU_EXTRA_PLAN
    if name == "entry":
        return ENTRY_PLAN
    raise SystemExit(f"未知 plan：{name}，可选 gpu-extra / entry")


def main() -> int:
    parser = argparse.ArgumentParser(description="淘宝型号搜索采集")
    parser.add_argument("--plan", default="gpu-extra", choices=("gpu-extra", "entry"))
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    wait_ready()
    plan = build_plan(args.plan)
    start_index = PLAN_START[args.plan]
    done = 0
    for offset, (category, query) in enumerate(plan):
        index = start_index + offset
        safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "-", query).strip("-")
        out_path = OUT / f"{index:03d}-{category}-{safe}.json"
        if out_path.is_file():
            try:
                if payload(json.loads(out_path.read_text(encoding="utf-8"))):
                    done += 1
                    continue
            except (OSError, json.JSONDecodeError):
                pass
        log(f"({offset + 1}/{len(plan)}) 搜索 {category} :: {query}")
        data = call_search(query, out_path)
        if data:
            done += 1
            items = data.get("items") or data.get("results") or []
            log(f"({offset + 1}/{len(plan)}) {query}: {len(items)} 条")
        else:
            log(f"({offset + 1}/{len(plan)}) {query}: 无结果")
    log(f"完成 {done}/{len(plan)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
