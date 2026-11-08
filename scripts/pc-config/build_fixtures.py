"""Stage 1.5：一次性生成 PC 配置所需的三份 fixture。

顺序：候选校验 → catalog.json → benchmarks.json → offers.json（缺失时创建占位）。
offers.json 一旦存在就不会被覆盖，避免把负责人提供的报价冲掉。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from match_benchmarks import build_benchmarks
from normalize_specs import build_catalog, write_json
from pc_config_data import (
    CATEGORY_ORDER,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SHORTLIST_DOC,
    REPO_ROOT,
)
from select_candidates import (
    DEFAULT_SELECTION,
    load_selection,
    resolve_data_dir,
    write_shortlist_markdown,
)

SCHEMA_VERSION = "1.0.0"


def write_offers_placeholder(output_dir: Path, catalog_version: str, generated_at: str) -> Path:
    """没有报价数据时写入显式占位，保证 Java 侧加载路径稳定且可 fail-closed。"""

    offers_path = output_dir / "offers.json"
    if offers_path.is_file():
        print(f"[skip] offers.json 已存在，保留现有内容：{offers_path}")
        return offers_path
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "data_status": "PENDING_OWNER_QUOTES",
        "catalog_version": catalog_version,
        "notes": "等待负责人提供中国区人工核验报价；空集合意味着任何方案都无法生成报价，求解必须返回无解。",
        "offers": [],
    }
    write_json(payload, offers_path)
    return offers_path


def validate(catalog: dict, benchmarks: dict) -> None:
    hardware = catalog["hardware"]
    blocked = [
        entry["hardware_id"] for entry in hardware if entry["recommendation_status"] == "BLOCKED"
    ]
    if blocked:
        raise SystemExit(f"存在缺少必需字段的硬件：{blocked}")

    benchmark_ids = {entry["hardware_id"] for entry in benchmarks["entries"]}
    expected = {entry["hardware_id"] for entry in hardware if entry["category"] in {"CPU", "GPU"}}
    missing = sorted(expected - benchmark_ids)
    if missing:
        raise SystemExit(f"CPU/GPU 缺少跑分映射：{missing}")

    duplicate_ids = len(benchmark_ids) != len(benchmarks["entries"])
    if duplicate_ids:
        raise SystemExit("benchmarks.json 存在重复 hardware_id")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 PC 配置 Java fixture")
    parser.add_argument("--data-dir", help="Hardware data 根目录，也可用 PC_DATA_DIR")
    parser.add_argument("--selection", default=str(DEFAULT_SELECTION))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--shortlist-doc", default=str(DEFAULT_SHORTLIST_DOC))
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    data_dir = resolve_data_dir(args.data_dir)
    output_dir = Path(args.output_dir)
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    config, selected = load_selection(Path(args.selection), data_dir)
    catalog = build_catalog(config, selected, generated_at)
    benchmarks = build_benchmarks(catalog, data_dir)
    validate(catalog, benchmarks)

    write_json(catalog, output_dir / "catalog.json")
    write_json(benchmarks, output_dir / "benchmarks.json")
    offers_path = write_offers_placeholder(output_dir, catalog["catalog_version"], generated_at)
    write_shortlist_markdown(config, selected, Path(args.shortlist_doc))

    counts = {category: 0 for category in CATEGORY_ORDER}
    for entry in catalog["hardware"]:
        counts[entry["category"]] += 1
    summary = "，".join(f"{category} {count}" for category, count in counts.items())
    print(f"[ok] 候选：{summary}，合计 {len(catalog['hardware'])}")
    print(f"[ok] 跑分：{len(benchmarks['entries'])} 条，未匹配 {len(benchmarks['unmatched'])} 条")
    print(f"[ok] 报价：{offers_path.relative_to(REPO_ROOT)}（空占位）")
    print(f"[ok] 评审清单：{Path(args.shortlist_doc).relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
