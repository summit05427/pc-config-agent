"""Stage 8.5：PassMark 跑分映射。

复用 match_benchmarks.py 的 CPU / GPU 匹配函数，把全量主数据映射到跑分，并显式区分
CPU Mark、单线程分、GPU 芯片级 G3D Mark 与磁盘 Disk Mark。无法可靠匹配的记录保留为
UNMATCHED，不删除硬件（Stage 8 方案 §8.5）。

用法：
    python scripts/pc-config/map_benchmarks.py \
        --master data/pc-config/master/hardware-master.jsonl \
        --output data/pc-config/master/hardware-benchmarks.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from match_benchmarks import SOURCE_NAME, SOURCE_SNAPSHOT, _similarity, match_cpu, match_gpu
from pc_config_data import normalize_name_for_match, parse_number, read_csv_rows

STORAGE_SIMILARITY_THRESHOLD = 0.8
STORAGE_AMBIGUITY_MARGIN = 0.02
# 容量单独比较，型号名里再出现容量会稀释相似度（1 TB 与 1TB 写法不同）
CAPACITY_TEXT = re.compile(r"\d+(?:\.\d+)?\s*(?:tb|gb|t|g)\b", re.IGNORECASE)
CAPACITY_RELATIVE_TOLERANCE = 0.06
MATCH_SCOPE_PRODUCT = "PRODUCT"
MATCH_SCOPE_CHIPSET = "CHIPSET"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def as_match_input(record: dict[str, Any]) -> dict[str, Any]:
    """match_cpu 需要 display_name；主数据把它规范化进了 aliases。"""

    aliases = record.get("aliases") or []
    return {**record, "display_name": aliases[0] if aliases else record["model_name"]}


def unmatched_entry(record: dict[str, Any], benchmark_type: str, scope: str) -> dict[str, Any]:
    return {
        "hardware_id": record["hardware_id"],
        "category": record["category"],
        "benchmark_type": benchmark_type,
        "score": None,
        "secondary_score": None,
        "rank_no": None,
        "samples": None,
        "source": {"name": SOURCE_NAME, "snapshot_date": SOURCE_SNAPSHOT},
        "match_method": "NONE",
        "match_confidence": 0.0,
        "match_scope": scope,
        "match_status": "UNMATCHED",
    }


def _capacity_gb(value: Any) -> int | None:
    """PassMark 的 capacity_gb 是纯数值（可能带小数），不能走带单位的解析器。"""

    try:
        return int(round(float(value))) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _same_capacity(left: int, right: int) -> bool:
    """1 TB 在不同来源里写作 1000 或 1024，按相对误差容忍。"""

    if left == right:
        return True
    return abs(left - right) / max(left, right, 1) <= CAPACITY_RELATIVE_TOLERANCE


def _name_without_capacity(value: str) -> str:
    return normalize_name_for_match(CAPACITY_TEXT.sub(" ", value))


def _model_tokens(name: str, brand: str | None) -> set[str]:
    """去掉品牌与容量后的型号令牌；PassMark 存储名有大量通用名，必须靠型号数字区分。"""

    tokens = set(_name_without_capacity(name).split())
    if brand:
        tokens -= set(normalize_name_for_match(brand).split())
    return {token for token in tokens if token}


def _overlap_score(target: set[str], candidate: set[str]) -> float:
    """重叠系数：候选令牌全部落在目标里即视为同名，不受通用后缀稀释。"""

    if not target or not candidate:
        return 0.0
    return len(target & candidate) / min(len(target), len(candidate))


def match_storage(
    record: dict[str, Any], rows: list[dict[str, str]]
) -> dict[str, Any] | None:
    """按容量近似匹配 + 型号重叠系数；差距过小视为歧义，不猜。"""

    capacity = (record.get("specifications") or {}).get("capacity_gb")
    if capacity is None:
        return None
    target_tokens = _model_tokens(record.get("model_name") or "", record.get("brand"))
    if not target_tokens:
        return None
    scored: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        row_capacity = _capacity_gb(row.get("capacity_gb"))
        if row_capacity is None or not _same_capacity(capacity, row_capacity):
            continue
        candidate_tokens = _model_tokens(row.get("name") or "", row.get("brand"))
        shared = target_tokens & candidate_tokens
        # 至少共享两个令牌且包含型号数字，避免只靠通用词命中
        if len(shared) < 2 or not any(re.search(r"\d", token) for token in shared):
            continue
        scored.append((_overlap_score(target_tokens, candidate_tokens), row))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_row = scored[0]
    if best_score < STORAGE_SIMILARITY_THRESHOLD:
        return None
    ambiguous = len(scored) > 1 and best_score - scored[1][0] < STORAGE_AMBIGUITY_MARGIN
    return {
        "hardware_id": record["hardware_id"],
        "category": "STORAGE",
        "benchmark_type": "DISK_MARK",
        "score": None if ambiguous else parse_number(best_row.get("disk_mark")),
        "secondary_score": None,
        "rank_no": int(parse_number(best_row.get("rank_no")) or 0),
        "samples": int(parse_number(best_row.get("samples")) or 0),
        "source": {
            "name": SOURCE_NAME,
            "source_id": best_row.get("id"),
            "source_name": best_row.get("name"),
            "snapshot_date": SOURCE_SNAPSHOT,
        },
        "match_method": "FUZZY_TOKEN_OVERLAP",
        "match_confidence": round(best_score, 4),
        "match_scope": MATCH_SCOPE_PRODUCT,
        "match_status": "AMBIGUOUS" if ambiguous else "MATCHED",
    }


def build_mappings(records: list[dict[str, Any]], data_dir: Path) -> list[dict[str, Any]]:
    cpu_rows = read_csv_rows(data_dir, "passmark_cpu")
    gpu_rows = read_csv_rows(data_dir, "passmark_gpu")
    disk_rows = read_csv_rows(data_dir, "passmark_disk")

    chipset_boards: dict[str, int] = {}
    for record in records:
        if record["category"] != "GPU":
            continue
        specs = record["specifications"]
        key = f"{specs.get('chipset')}|{specs.get('vram_gb')}"
        chipset_boards[key] = chipset_boards.get(key, 0) + 1

    entries: list[dict[str, Any]] = []
    for record in records:
        category = record["category"]
        if category == "CPU":
            entry = match_cpu(as_match_input(record), cpu_rows)
            if entry is None:
                entries.append(unmatched_entry(record, "CPUMARK", MATCH_SCOPE_PRODUCT))
                continue
            base = {
                "hardware_id": entry["hardware_id"],
                "category": "CPU",
                "rank_no": entry["rank_no"],
                "samples": entry["samples"],
                "source": entry["source"],
                "match_method": entry["match_method"],
                "match_confidence": entry["match_confidence"],
                "match_scope": MATCH_SCOPE_PRODUCT,
                "match_status": "MATCHED",
            }
            entries.append(
                {
                    **base,
                    "benchmark_type": "CPUMARK",
                    "score": entry["score"],
                    "secondary_score": entry["secondary_score"],
                }
            )
            entries.append(
                {
                    **base,
                    "benchmark_type": "SINGLE_THREAD",
                    "score": entry["secondary_score"],
                    "secondary_score": None,
                }
            )
        elif category == "GPU":
            entry = match_gpu(record, gpu_rows)
            if entry is None:
                entries.append(unmatched_entry(record, "G3D_MARK", MATCH_SCOPE_CHIPSET))
                continue
            specs = record["specifications"]
            key = f"{specs.get('chipset')}|{specs.get('vram_gb')}"
            entries.append(
                {
                    **entry,
                    "category": "GPU",
                    "match_scope": MATCH_SCOPE_CHIPSET,
                    "match_status": "MATCHED",
                    "board_variant_count": chipset_boards.get(key, 1),
                }
            )
        elif category == "STORAGE":
            entry = match_storage(record, disk_rows)
            entries.append(
                entry
                if entry is not None
                else unmatched_entry(record, "DISK_MARK", MATCH_SCOPE_PRODUCT)
            )

    entries.sort(key=lambda item: (item["hardware_id"], item["benchmark_type"]))
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 8.5 PassMark 跑分映射")
    parser.add_argument("--master", default="data/pc-config/master/hardware-master.jsonl")
    parser.add_argument(
        "--output", default="data/pc-config/master/hardware-benchmarks.jsonl"
    )
    parser.add_argument("--data-dir", help="Hardware data 根目录，也可用 PC_DATA_DIR")
    args = parser.parse_args(argv)

    raw_dir = args.data_dir or os.environ.get("PC_DATA_DIR")
    if not raw_dir:
        raise SystemExit("请通过 --data-dir 或 PC_DATA_DIR 指定硬件数据目录")
    data_dir = Path(raw_dir)

    records = read_jsonl(Path(args.master))
    entries = build_mappings(records, data_dir)
    write_jsonl(entries, Path(args.output))

    status: dict[str, int] = {}
    for entry in entries:
        status[entry["match_status"]] = status.get(entry["match_status"], 0) + 1
    print(f"[ok] 跑分映射 {len(entries)} 条，状态：{dict(sorted(status.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
