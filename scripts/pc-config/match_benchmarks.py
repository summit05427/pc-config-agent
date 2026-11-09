"""Stage 1.3 / 1.5：把候选硬件映射到 PassMark 跑分，生成 benchmarks.json。

匹配策略按置信度降序：
1. 归一化全名完全一致；
2. PassMark model_key 是候选全名的后缀（处理品牌前缀差异）；
3. 显卡按 chipset（必要时叠加显存）匹配。

不匹配的条目不猜测分数，写入 unmatched 供人工复核。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pc_config_data import (
    DEFAULT_OUTPUT_DIR,
    normalize_cpu_name,
    normalize_gpu_name,
    normalize_name_for_match,
    parse_number,
    read_csv_rows,
)
from select_candidates import resolve_data_dir

SOURCE_NAME = "PassMark"
SOURCE_SNAPSHOT = "2026-10-05"
GPU_EXCLUDE_TOKENS = ("laptop", "mobile", "max-q", "max q")
# PassMark 型号键会带描述性后缀（如 `fx 8350 eight`、`a10 6700 apu`），比较时必须剔除
DESCRIPTOR_TOKENS = {
    "apu",
    "eight",
    "six",
    "four",
    "quad",
    "dual",
    "hexa",
    "octa",
    "core",
    "oem",
    "tray",
    "processor",
    "edition",
    "black",
    "unlocked",
}


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_name_for_match(value).split() if token}


def _model_key_tokens(row: dict[str, str]) -> set[str]:
    """型号键的区分性令牌，剔除描述词、核心数与时钟频率后缀。"""

    raw = row.get("model_key") or ""
    # PassMark 会把频率写进型号键（如 `430 1 80ghz`、`i5 10400 2 90ghz`），必须剥离
    raw = re.sub(r"\s*@.*$", "", raw)
    raw = re.sub(r"\s*\d+\s+\d+\s*ghz\s*$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*\d+(?:\.\d+)?\s*ghz\s*$", "", raw, flags=re.IGNORECASE)
    tokens = _tokens(raw) - DESCRIPTOR_TOKENS
    # 1-2 位纯数字多为核心数或代数，没有区分度
    tokens = {token for token in tokens if not re.fullmatch(r"\d{1,2}", token)}
    return tokens if any(re.search(r"\d", token) for token in tokens) else set()


def _similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def match_cpu(hardware: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any] | None:
    target_name = normalize_cpu_name(hardware["display_name"])
    target_norm = normalize_name_for_match(target_name)

    exact = [row for row in rows if normalize_name_for_match(row["name"]) == target_norm]
    if exact:
        return _cpu_entry(hardware["hardware_id"], _pick_best(exact), "EXACT_NAME", 1.0)

    suffix = [
        row
        for row in rows
        if row.get("model_key")
        and target_norm.endswith(normalize_name_for_match(row["model_key"]))
    ]
    if suffix:
        return _cpu_entry(hardware["hardware_id"], _pick_best(suffix), "MODEL_KEY_SUFFIX", 0.95)

    # 型号键去掉描述性后缀后做令牌包含匹配，覆盖 `FX-8350` / `A10-6700 APU` 这类命名差异
    target_tokens = set(target_norm.split())
    token_matches = [
        row
        for row in rows
        if _model_key_tokens(row) and _model_key_tokens(row) <= target_tokens
    ]
    if token_matches:
        return _cpu_entry(
            hardware["hardware_id"], _pick_best(token_matches), "MODEL_KEY_TOKENS", 0.92
        )

    # 只按相似度排序：同名相似度并列时不能比较 dict，否则会抛 TypeError
    fuzzy = sorted(
        ((_similarity(target_name, row["name"]), row) for row in rows),
        key=lambda item: item[0],
        reverse=True,
    )
    if fuzzy and fuzzy[0][0] >= 0.9:
        return _cpu_entry(hardware["hardware_id"], fuzzy[0][1], "FUZZY_TOKEN_OVERLAP", 0.9)
    return None


def _pick_best(rows: list[dict[str, str]]) -> dict[str, str]:
    """同名记录可能多条，优先样本数多的，其次跑分高的。"""

    return max(
        rows,
        key=lambda row: (
            parse_number(row.get("samples")) or 0,
            parse_number(row.get("cpu_mark") or row.get("g3d_mark")) or 0,
        ),
    )


def _cpu_entry(
    hardware_id: str, row: dict[str, str], method: str, confidence: float
) -> dict[str, Any]:
    return {
        "hardware_id": hardware_id,
        "benchmark_type": "CPUMARK",
        "score": parse_number(row.get("cpu_mark")),
        "secondary_score": parse_number(row.get("single_thread_mark")),
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


def match_gpu(hardware: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any] | None:
    specifications = hardware["specifications"]
    chipset = specifications.get("chipset") or ""
    vram_gb = specifications.get("vram_gb")
    candidates = [
        row
        for row in rows
        if not any(token in row["name"].lower() for token in GPU_EXCLUDE_TOKENS)
    ]

    target_with_vram = normalize_name_for_match(normalize_gpu_name(chipset, vram_gb))
    exact = [row for row in candidates if normalize_name_for_match(row["name"]) == target_with_vram]
    if exact:
        return _gpu_entry(hardware["hardware_id"], _pick_best(exact), "EXACT_CHIPSET_VRAM", 1.0)

    chipset_norm = normalize_name_for_match(chipset)
    by_chipset = [
        row
        for row in candidates
        if normalize_name_for_match(row["name"]).startswith(chipset_norm)
    ]
    if by_chipset and vram_gb:
        same_vram = [
            row for row in by_chipset if f"{vram_gb}gb" in normalize_name_for_match(row["name"])
        ]
        if same_vram:
            return _gpu_entry(
                hardware["hardware_id"], _pick_best(same_vram), "CHIPSET_AND_VRAM", 0.98
            )
    if by_chipset:
        # 同 chipset 若有多档显存，取样本数最高的一条，并在报告中保留置信度提示。
        return _gpu_entry(
            hardware["hardware_id"], _pick_best(by_chipset), "EXACT_CHIPSET", 0.95
        )
    return None


def _gpu_entry(
    hardware_id: str, row: dict[str, str], method: str, confidence: float
) -> dict[str, Any]:
    return {
        "hardware_id": hardware_id,
        "benchmark_type": "G3D_MARK",
        "score": parse_number(row.get("g3d_mark")),
        "secondary_score": parse_number(row.get("g2d_mark")),
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


def build_benchmarks(catalog: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    cpu_rows = read_csv_rows(data_dir, "passmark_cpu")
    gpu_rows = read_csv_rows(data_dir, "passmark_gpu")
    entries: list[dict[str, Any]] = []
    unmatched: list[dict[str, str]] = []

    for hardware in catalog["hardware"]:
        category = hardware["category"]
        if category == "CPU":
            entry = match_cpu(hardware, cpu_rows)
        elif category == "GPU":
            entry = match_gpu(hardware, gpu_rows)
        else:
            continue
        if entry is None:
            unmatched.append(
                {"hardware_id": hardware["hardware_id"], "model_name": hardware["model_name"]}
            )
            continue
        if entry["score"] is None:
            unmatched.append(
                {"hardware_id": hardware["hardware_id"], "model_name": hardware["model_name"]}
            )
            continue
        entries.append(entry)

    return {
        "schema_version": "1.0.0",
        "generated_at": catalog["generated_at"],
        "source": {"name": SOURCE_NAME, "snapshot_date": SOURCE_SNAPSHOT},
        "entries": entries,
        "unmatched": unmatched,
    }


def write_json(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 PassMark 跑分映射 benchmarks.json")
    parser.add_argument("--data-dir", help="Hardware data 根目录，也可用 PC_DATA_DIR")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    data_dir = resolve_data_dir(args.data_dir)
    output_dir = Path(args.output_dir)
    catalog_path = output_dir / "catalog.json"
    if not catalog_path.is_file():
        raise SystemExit(f"缺少 {catalog_path}，请先运行 normalize_specs.py")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    benchmarks = build_benchmarks(catalog, data_dir)
    output_path = output_dir / "benchmarks.json"
    write_json(benchmarks, output_path)

    print(
        f"[ok] benchmarks.json 已写入 {output_path}，命中 {len(benchmarks['entries'])} 条，"
        f"未匹配 {len(benchmarks['unmatched'])} 条"
    )
    if benchmarks["unmatched"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
