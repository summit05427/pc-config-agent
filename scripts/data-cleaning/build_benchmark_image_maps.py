"""把 Hardware data 里的 PassMark 跑分与产品图映射到当前运行时目录。

输入（只读）：
- Hardware data/csv/passmark_cpu.csv / passmark_gpu.csv / passmark_disk.csv
- Hardware data/csv/pcpp_hardware_all.csv（pcpp_id → image_url）
- stage3e-products.jsonl（product_id → identifiers.pcpp_ids）

输出：
- data/pc-config/cleaning/benchmark-map.json：hardware_id → PassMark 跑分
- data/pc-config/cleaning/image-map.json：hardware_id → 产品图 URL

匹配失败一律进 unmatched，绝不猜分数：跑分只影响评分与展示。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / "scripts" / "pc-config"))

from match_benchmarks import match_cpu, match_gpu  # noqa: E402
from pc_config_data import parse_number, read_csv_rows  # noqa: E402

CLEANING_DIR = BASE_DIR / "data" / "pc-config" / "cleaning"
CATALOG = BASE_DIR / "data" / "pc-config" / "export" / "runtime-full" / "catalog.json"
PRODUCTS = CLEANING_DIR / "stage3e-products.jsonl"
BENCHMARK_MAP = CLEANING_DIR / "benchmark-map.json"
IMAGE_MAP = CLEANING_DIR / "image-map.json"

DEFAULT_DATA_DIR = Path("F:/LLM_PC_Agent/Hardware data")
SOURCE_NAME = "PassMark"
SOURCE_SNAPSHOT = "2026-10-05"
GPU_EXCLUDE_TOKENS = ("laptop", "mobile", "max-q", "max q")

IDENTITY = re.compile(r"[a-z]{1,}\d+[a-z0-9]*|\d{3,}")
CAPACITY = re.compile(r"\d+(?:tb|gb|t|g)")
CAPACITY_UNITS = {"tb", "gb", "t", "g"}
DISK_SPEC_TOKENS = {
    "2230", "2242", "2260", "2280", "22110",
    "5400", "5640", "5700", "5900", "7200", "10000", "15000",
}
VARIANT_TOKENS = {"ti", "super", "pro", "max", "xt", "xtx", "ultra"}
# 强变体词：同一串型号数字下 PRO/MAX/PLUS 是不同的 SKU，两侧必须同时出现
STRICT_VARIANTS = {"pro", "max", "plus"}
# 平台词不是型号词（SN850P for PS5 的 ps5），拿它当身份 token 会把两个型号混在一起
PLATFORM_TOKENS = {"ps5", "ps4", "xbox"}


def tokenize(text: str | None) -> list[str]:
    """小写 + 非字母数字折成空格，并把「2 TB」合并为 2tb（对齐 PassMark 连写口径）。"""

    if not text:
        return []
    raw = re.split(r"[^a-z0-9]+", text.lower().strip())
    tokens: list[str] = []
    index = 0
    while index < len(raw):
        token = raw[index]
        if token:
            if index + 1 < len(raw) and token.isdigit() and raw[index + 1] in CAPACITY_UNITS:
                tokens.append(normalize_capacity(token + raw[index + 1]))
                index += 2
                continue
            tokens.append(token)
        index += 1
    return tokens


def normalize_capacity(token: str) -> str:
    return re.sub(r"g$", "gb", re.sub(r"t$", "tb", token))


def first_capacity(tokens: list[str]) -> str | None:
    return next((token for token in tokens if CAPACITY.fullmatch(token)), None)


def capacity_consistent(name_tokens: list[str], candidate_tokens: list[str]) -> bool:
    """容量一致性按 GB 数值比较：PassMark 写 1000GB、目录写 1TB，512GB/500GB 也视为同档。"""

    left, right = first_capacity(name_tokens), first_capacity(candidate_tokens)
    if left is None or right is None:
        return True
    left_gb, right_gb = capacity_gb(left), capacity_gb(right)
    return abs(left_gb - right_gb) <= max(left_gb, right_gb) * 0.06


def capacity_gb(token: str) -> float:
    value = float(re.match(r"[\d.]+", token).group())
    return value * 1024 if token.endswith("tb") else value


def disk_entry(hardware_id: str, row: dict[str, str], method: str, confidence: float) -> dict[str, Any]:
    return {
        "hardware_id": hardware_id,
        "benchmark_type": "DISKMARK",
        "score": parse_number(row.get("disk_mark")),
        "secondary_score": None,
        "rank_no": int(parse_number(row.get("rank_no")) or 0),
        "samples": int(parse_number(row.get("samples")) or 0),
        "source": {
            "name": SOURCE_NAME,
            "source_id": row.get("id"),
            "source_name": row.get("name"),
            "snapshot_date": SOURCE_SNAPSHOT,
        },
        "match_method": method,
        "match_confidence": confidence,
    }


def match_disk(hardware: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any] | None:
    """沿用 Java BenchmarkMatcher 的思路：身份 token 粗筛 + 共词打分 + 变体/容量闸门。

    身份 token 命中失败时退到「型号词全包含」：PassMark 的硬盘名常缺品牌词或容量写法不同
    （`KINGSTON NV3 1TB SSD` vs `Kingston NV3 1 TB`），只靠数字 token 会大面积漏配。
    """

    name_tokens = tokenize(hardware["display_name"])
    name_set = set(name_tokens)
    name_capacity = first_capacity(name_tokens)
    identities = [
        token
        for token in name_tokens
        if IDENTITY.fullmatch(token)
        and token not in DISK_SPEC_TOKENS
        and token not in PLATFORM_TOKENS
        and not CAPACITY.fullmatch(token)
    ]
    for identity in identities:
        candidates = [row for row in rows if identity in tokenize(row.get("model_key"))]
        method, confidence = "DISK_MODEL_TOKENS", 0.9
        # 族内存在带容量的行时优先精确容量，其次退回容量未知的族内行（同型号不同容量写法）
        capacity_rows = [row for row in candidates if first_capacity(tokenize(row.get("model_key"))) is not None]
        if name_capacity and capacity_rows:
            exact = [row for row in capacity_rows if capacity_consistent(name_tokens, tokenize(row.get("model_key")))]
            if exact:
                candidates = exact
            else:
                candidates = [row for row in candidates if first_capacity(tokenize(row.get("model_key"))) is None]
                method, confidence = "DISK_MODEL_NO_CAPACITY", 0.7
        scored: list[tuple[int, int, dict[str, str]]] = []
        for row in candidates:
            candidate_tokens = tokenize(row.get("model_key"))
            candidate_set = set(candidate_tokens)
            common = len(candidate_set & name_set)
            if common < 2:
                continue
            if any(token in VARIANT_TOKENS and token not in name_set for token in candidate_set):
                continue
            if any(token in STRICT_VARIANTS and token not in candidate_set for token in name_set):
                continue
            if not capacity_consistent(name_tokens, candidate_tokens):
                continue
            score = common * 3 - len(candidate_set - name_set)
            rank = int(parse_number(row.get("rank_no")) or 999999)
            scored.append((score, -rank, row))
        if scored:
            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return disk_entry(hardware["hardware_id"], scored[0][2], method, confidence)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="生成跑分映射与产品图映射")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    if not (data_dir / "csv").is_dir():
        raise SystemExit(f"硬件数据目录缺少 csv/：{data_dir}")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    products = {
        row["product_id"]: row
        for row in (
            json.loads(line) for line in PRODUCTS.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    }
    images = {
        row["pcpp_id"]: row["image_url"].strip()
        for row in read_csv_rows(data_dir, "pcpp_hardware_all")
        if row.get("pcpp_id") and row.get("image_url", "").strip()
    }
    cpu_rows = read_csv_rows(data_dir, "passmark_cpu")
    gpu_rows = [
        row for row in read_csv_rows(data_dir, "passmark_gpu")
        if not any(token in row["name"].lower() for token in GPU_EXCLUDE_TOKENS)
    ]
    # PassMark 显卡名带厂商前缀（`Intel Arc B570`），目录里只有芯片型号（`Arc B570`）：
    # 保留一份去前缀的副本用于兜底匹配，命中后再把展示名还原成原始名
    gpu_original_names = {row["id"]: row["name"] for row in gpu_rows}
    gpu_rows_without_vendor = [
        {**row, "name": row["name"].split(" ", 1)[1]}
        for row in gpu_rows
        if row["name"].split(" ", 1)[0].lower() in {"intel", "amd", "nvidia"}
    ]
    disk_rows = read_csv_rows(data_dir, "passmark_disk")

    entries: list[dict[str, Any]] = []
    unmatched: list[dict[str, str]] = []
    image_map: dict[str, str] = {}
    image_missing: list[str] = []

    for hardware in catalog["hardware"]:
        hardware_id = hardware["hardware_id"]
        image_url = (hardware.get("source") or {}).get("image_url")
        if not image_url:
            identifiers = (products.get(hardware_id) or {}).get("identifiers") or {}
            for pcpp_id in identifiers.get("pcpp_ids") or []:
                if images.get(str(pcpp_id)):
                    image_map[hardware_id] = images[str(pcpp_id)]
                    break
            else:
                image_missing.append(hardware_id)
        if hardware["category"] == "CPU":
            entry = match_cpu(hardware, cpu_rows)
        elif hardware["category"] == "GPU":
            entry = match_gpu(hardware, gpu_rows)
            if entry is None:
                entry = match_gpu(hardware, gpu_rows_without_vendor)
                if entry is not None:
                    original = gpu_original_names.get(entry["source"]["source_id"])
                    if original:
                        entry["source"]["source_name"] = original
        elif hardware["category"] == "STORAGE":
            entry = match_disk(hardware, disk_rows)
        else:
            continue
        if entry is None or entry.get("score") is None:
            unmatched.append({"hardware_id": hardware_id, "model_name": hardware["model_name"]})
            continue
        entries.append(entry)

    # 用数据快照日期而不是当前时间，保证重复执行产物字节一致、diff 可审
    generated_at = f"{SOURCE_SNAPSHOT}T00:00:00Z"
    BENCHMARK_MAP.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "generated_at": generated_at,
                "source": {"name": SOURCE_NAME, "snapshot_date": SOURCE_SNAPSHOT},
                "entries": entries,
                "unmatched": unmatched,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    IMAGE_MAP.write_text(
        json.dumps(
            {
                "source": "pcpp_hardware_all",
                # catalog 导出时已直接回填 source.image_url，此处 entries 为空是预期结果，
                # 不再代表「图片映射任务未执行」。
                "note": "catalog.source.image_url 已回填时不产生条目；本文件只补 catalog 缺失的图片",
                "entries": image_map,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "benchmark_entries": len(entries),
                "benchmark_unmatched": len(unmatched),
                "by_type": dict(Counter(entry["benchmark_type"] for entry in entries)),
                "unmatched_by_category": dict(Counter(item["hardware_id"].split("-")[0] for item in unmatched)),
                "image_backfilled": len(image_map),
                "image_still_missing": len(image_missing),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
