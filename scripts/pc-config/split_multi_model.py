"""用 LLM 拆解「一个链接混卖多型号」的 CPU / GPU 商品，并做代码层二次校验。

背景：淘宝搜索卡片只给一个展示价（通常对应最便宜那款），无法据此给单个型号定价；
但商品详情页的 SKU 面板会逐项列出规格与价格。本脚本分三步：

1. collect：调用本地 chengkit-taobao MCP，读取每个混卖链接的详情与 SKU，落盘原文。
2. split：把「标题 + 页面文本 + SKU 价格矩阵」交给 LLM，只让它输出
   `[{brand, model, price_cny}]`；拆不出来就输出 null。
3. emit：代码层重新校验，价格必须落在类别区间、型号必须能在硬件主库里唯一命中，
   通过后才产出可交给 `ingest_offers.py --market` 的观测价文件。

LLM 只能提建议，入库口径由本脚本的规则决定，避免模型幻觉直接污染报价。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pc_config_data import REPO_ROOT

MARKET_DIR = REPO_ROOT / "data" / "pc-config" / "export" / "marketplace"
MATCHES_PATH = MARKET_DIR / "matches.jsonl"
DETAIL_DIR = MARKET_DIR / "detail"
SPLIT_PATH = MARKET_DIR / "llm_splits.jsonl"
OUTPUT_PATH = MARKET_DIR / "llm_offers.json"
MASTER_PATH = REPO_ROOT / "data" / "pc-config" / "master" / "hardware-master.jsonl"

TARGET_CATEGORIES = ("CPU", "GPU")
PRICE_RANGE_FEN = {
    "CPU": (10_000, 2_000_000),      # ¥100 – ¥20,000
    "GPU": (50_000, 3_000_000),      # ¥500 – ¥30,000
}
# 官方 MCP 的 read_item 在未绑定标签页时会等满 25 秒并报“本地服务未响应”，
# 因此详情采集直接复用同一条 Chrome 扩展通道的 opencli CLI。
OPENCLI_LAUNCH = Path(
    os.environ.get("TAOBAO_OPENCLI_LAUNCH", r"F:\tools\chengkit-taobao\tools\opencli-launch.cjs")
)
NODE_EXE = os.environ.get("TAOBAO_MCP_NODE", r"E:\Nodejs\nodejs\node.exe")
BROWSER_SESSION = os.environ.get("TAOBAO_BROWSER_SESSION", "main")
PAGE_WAIT_SECONDS = 8
TEXT_LIMIT = 6000

# 归一化时先替换组合写法，再删除品牌词，避免 "Ryzen 7" 被拆成孤立的 "7"。
MODEL_REPLACEMENTS = (
    (re.compile(r"ryzen\s*([579])\b"), r"r\1"),
    (re.compile(r"锐龙\s*r?\s*([579])\b"), r"r\1"),
    (re.compile(r"core\s*ultra\s*([579])\b"), r"ultra\1"),
    (re.compile(r"core\s*(i[3579])\b"), r"\1"),
)
MODEL_NOISE = re.compile(
    r"amd|intel|nvidia|geforce|radeon|英伟达|英特尔|锐龙|酷睿|处理器|显卡|散片|原盒|盒装"
    r"|全新|台式机|电脑|cpu|gpu",
    re.IGNORECASE,
)
GPU_MEMORY_SUFFIX = re.compile(r"^\d+g(b)?$")
# 淘宝标题常用中文品牌，主库使用英文；只收录常见显卡/CPU 品牌，未收录按歧义拒绝。
BRAND_ALIASES = {
    "索泰": "zotac", "华硕": "asus", "微星": "msi", "技嘉": "gigabyte", "七彩虹": "colorful",
    "影驰": "galax", "耕升": "gainward", "铭瑄": "maxsun", "盈通": "yeston", "昂达": "onda",
    "翔升": "asl", "万丽": "manli", "丽台": "leadtek", "映众": "inno3d", "蓝宝石": "sapphire",
    "撼讯": "powercolor", "讯景": "xfx", "迪兰": "dataland", "瀚铠": "hannstar",
    "英伟达": "nvidia", "英特尔": "intel", "amd": "amd",
}

SYSTEM_PROMPT = (
    "你是电商商品结构化解析器。只做一件事：从给定的标题、页面文本和 SKU 价格矩阵中，"
    "拆解出页面明确在售的 CPU 或 GPU 型号及其对应价格。"
    "规则：1) 只输出页面中真实出现且能对应到单一价格的型号；"
    "2) 价格必须来自 SKU 面板或页面中与该型号明确绑定的数字，禁止推测、禁止用起价代替；"
    "3) 型号写标准名称（如 AMD R7 9800X3D、Intel i5-14600KF、RTX 5060 Ti 8GB），"
    "不要写店铺名、促销词、主板套装；"
    "4) 只要有一个型号无法确定价格，overall_confidence 设为 low；完全无法拆分时 models 输出 null。"
    "只输出 JSON。"
)

OUTPUT_SCHEMA = (
    '{"models": [{"brand": "AMD", "model": "R7 9800X3D", "price_cny": 2499}] '
    '或 {"models": null, "reason": "页面未给出可归属的单型号价格"}}'
)


class SplitError(ValueError):
    """LLM 输出或校验失败。"""


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_multi_items() -> list[dict[str, Any]]:
    """从匹配结果里挑出被 MULTI 标记排除的 CPU / GPU 链接，按 item_id 去重。"""

    if not MATCHES_PATH.is_file():
        raise SplitError(f"缺少匹配结果：{MATCHES_PATH}")
    seen: dict[str, dict[str, Any]] = {}
    for line in MATCHES_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("category") not in TARGET_CATEGORIES:
            continue
        # 匹配阶段把混卖链接的置信度置为 MULTI_MODEL，flags 只记录二手/套装等排除项。
        if row.get("confidence") != "MULTI_MODEL":
            continue
        seen.setdefault(row["item_id"], row)
    return list(seen.values())


def tail_text(payload: dict[str, Any]) -> str:
    content = (payload.get("result") or {}).get("content") or []
    return "\n".join(item.get("text", "") for item in content if item.get("type") == "text")


def run_browser(arguments: list[str]) -> Any:
    """调用 opencli 浏览器命令，返回其 JSON 结果中的 data 字段。"""

    if not OPENCLI_LAUNCH.is_file():
        raise SplitError(f"缺少 opencli 启动器：{OPENCLI_LAUNCH}")
    completed = subprocess.run(
        [NODE_EXE, str(OPENCLI_LAUNCH), "browser", *arguments, "--session", BROWSER_SESSION],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise SplitError(f"浏览器命令无输出：{arguments[0]} {completed.stderr[:200]}")
    payload = json.loads(lines[0])
    if not payload.get("ok"):
        raise SplitError(f"浏览器命令失败：{arguments[0]} {payload.get('error')}")
    return payload.get("data")


# 淘宝 SSR 页把整页数据挂在 __ICE_APP_CONTEXT__，SKU 价格与规格名可直接读取，
# 不必逐个点击规格按钮。
SKU_SCRIPT = (
    "(function(){var r=window.__ICE_APP_CONTEXT__.loaderData.home.data.res;"
    "var pv={};(r.skuBase.props||[]).forEach(function(p){(p.values||[]).forEach(function(v){pv[v.vid]=v.name})});"
    "var info=(r.skuCore||{}).sku2info||{};"
    "return (r.skuBase.skus||[]).map(function(s){"
    "var n=(s.propPath||'').split(';').map(function(x){return pv[x.split(':')[1]]||x});"
    "var pr=(info[s.skuId]||{}).price||{};"
    "return {spec:n.join(' '),price:pr.priceText||'',fen:Number(pr.priceMoney||0)}})"
    "})()"
)


def collect_details(limit: int | None) -> int:
    """逐个打开混卖商品页，抓取正文与 SKU 价格矩阵；已有可用结果则跳过。"""

    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    items = load_multi_items()
    if limit:
        items = items[:limit]
    done = 0
    for index, item in enumerate(items, start=1):
        target = DETAIL_DIR / f"{item['item_id']}.json"
        if target.is_file() and _detail_usable(_read_json(target)):
            done += 1
            continue
        log(f"({index}/{len(items)}) 读取 {item['category']} {item['item_id']}")
        page: dict[str, Any] = {}
        skus: list[dict[str, Any]] = []
        tab: str | None = None
        try:
            opened = run_browser(["open", item["url"]])
            tab = (opened or {}).get("page")
            time.sleep(PAGE_WAIT_SECONDS)
            page = run_browser(["extract", "--chunk-size", "40000", *(["--tab", tab] if tab else [])])
            skus = run_browser(["eval", SKU_SCRIPT, *(["--tab", tab] if tab else [])])
        except (SplitError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            log(f"{item['item_id']} 采集失败：{error}")
        finally:
            if tab:
                try:
                    run_browser(["tab", "close", tab])
                except (SplitError, subprocess.TimeoutExpired, json.JSONDecodeError):
                    pass
        payload = {"item": item, "page": page, "skus": skus}
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if _detail_usable(payload):
            done += 1
        else:
            log(f"{item['item_id']} 未取得页面文本，稍后可重跑")
    log(f"详情采集完成 {done}/{len(items)}")
    return 0 if done else 2


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _detail_usable(payload: dict[str, Any]) -> bool:
    content = (payload.get("page") or {}).get("content") or ""
    return len(content) > 200


def split_text(payload: dict[str, Any]) -> str:
    """把页面正文与 SKU 价格矩阵拼成 LLM 输入。"""

    item = payload.get("item") or {}
    page = payload.get("page") or {}
    parts = [
        f"标题：{item.get('title', '')}",
        f"搜索展示价：{item.get('price_fen', 0) / 100:.2f} 元",
    ]
    content = page.get("content") or ""
    if content:
        parts.append("页面文本：\n" + content[:TEXT_LIMIT])
    skus = [s for s in payload.get("skus") or [] if s.get("price")]
    if skus:
        lines = [f"- {s['spec']}：¥{s['price']}" for s in skus]
        parts.append("SKU 价格矩阵：\n" + "\n".join(lines))
    return "\n\n".join(parts)


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def call_llm(user_content: str, config: dict[str, str]) -> Any:
    """调用 OpenAI 兼容的 chat/completions 接口，返回解析后的 JSON。"""

    base_url = config["base_url"].rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps({
            "model": config["model"],
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_content}\n\n严格按此结构输出：{OUTPUT_SCHEMA}"},
            ],
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SplitError(f"LLM HTTP {error.code}: {error.read()[:200]!r}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SplitError(f"LLM 连接失败：{error}") from error
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def load_llm_config() -> dict[str, str]:
    env = read_env_file(REPO_ROOT / ".env")
    # 环境变量优先，便于用本地网关临时替换 .env 里的外部端点。
    api_key = os.environ.get("LLM_API_KEY") or env.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL") or env.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL") or env.get("LLM_MODEL")
    if not api_key or not base_url or not model:
        raise SplitError("缺少 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，无法调用模型")
    return {"api_key": api_key, "base_url": base_url, "model": model}


def run_split(limit: int | None) -> int:
    """对已采集的详情逐个调用 LLM，结果追加写入 llm_splits.jsonl。"""

    config = load_llm_config()
    files = sorted(DETAIL_DIR.glob("*.json"))
    files = [path for path in files if not path.name.endswith((".item.json", ".sku.json"))]
    if limit:
        files = files[:limit]
    if not files:
        log("没有可拆解的详情文件，先运行 collect 并确保浏览器已连接")
        return 2
    done_ids = {json.loads(line)["item_id"]
                for line in SPLIT_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line).get("retry") is False} if SPLIT_PATH.is_file() else set()
    for index, path in enumerate(files, start=1):
        payload = _read_json(path)
        item = payload.get("item") or {}
        if item.get("item_id") in done_ids or not _detail_usable(payload):
            continue
        log(f"({index}/{len(files)}) 拆解 {item.get('category')} {item.get('item_id')}")
        retry = False
        try:
            result = call_llm(split_text(payload), config)
        except (SplitError, json.JSONDecodeError) as error:
            log(f"{item.get('item_id')} 拆解失败：{error}")
            result = {"models": None, "reason": str(error)}
            retry = True
        record = {
            "item_id": item.get("item_id"),
            "category": item.get("category"),
            "title": item.get("title"),
            "url": item.get("url"),
            "search_price_fen": item.get("price_fen"),
            "models": result.get("models"),
            "reason": result.get("reason"),
            "retry": retry,
        }
        with SPLIT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    log("LLM 拆解完成")
    return 0


def normalize_model(value: str) -> str:
    """把型号压成可比较的紧凑串，如「AMD 锐龙7 9800X3D」→「r79800x3d」。"""

    text = (value or "").lower()
    for pattern, replacement in MODEL_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = MODEL_NOISE.sub(" ", text)
    text = re.sub(r"(\d{1,3})g\b", r"\1gb", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_brand(value: str) -> str:
    brand = (value or "").strip().lower()
    return BRAND_ALIASES.get(brand, brand)


def load_master_index() -> dict[str, list[dict[str, Any]]]:
    """按归一化型号建立主库索引；同一型号可能对应多个显存/版本，保留全部供歧义判定。"""

    index: dict[str, list[dict[str, Any]]] = {}
    if not MASTER_PATH.is_file():
        raise SplitError(f"缺少硬件主库：{MASTER_PATH}")
    with MASTER_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("category") not in TARGET_CATEGORIES:
                continue
            key = normalize_model(row.get("model_name") or "")
            if key:
                index.setdefault(key, []).append(row)
    return index


def match_hardware(model: str, category: str, brand: str,
                   index: dict[str, list[dict[str, Any]]]) -> tuple[dict | None, str]:
    """返回唯一命中的主库硬件；同型号多品牌/多 SKU 时用品牌消歧，仍歧义则拒绝。"""

    key = normalize_model(model)
    if not key:
        return None, "EMPTY_MODEL"
    candidates = [row for row in index.get(key, []) if row.get("category") == category]
    if not candidates:
        candidates = [
            row for rows in index.values() for row in rows
            if row.get("category") == category
            and normalize_model(row.get("model_name") or "").startswith(key)
            and GPU_MEMORY_SUFFIX.fullmatch(
                normalize_model(row.get("model_name") or "")[len(key):]
            )
        ]
    if not candidates:
        return None, "NOT_IN_MASTER"
    if len(candidates) == 1:
        return candidates[0], ""
    wanted = normalize_brand(brand)
    narrowed = [row for row in candidates if normalize_brand(row.get("brand")) == wanted]
    if narrowed:
        # 同一品牌同型号在 PCPP 里可能有多条重复记录，取最短 ID 的规范条目收口。
        return min(narrowed, key=lambda row: (len(row["hardware_id"]), row["hardware_id"])), ""
    return None, "AMBIGUOUS_IN_MASTER"


def emit_offers() -> int:
    """代码层二次校验 LLM 结果，只把通过校验的型号写入 llm_offers.json。"""

    if not SPLIT_PATH.is_file():
        log("没有 llm_splits.jsonl，先运行 split")
        return 2
    index = load_master_index()
    offers: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    used: set[str] = set()
    for line in SPLIT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        models = record.get("models")
        if not models:
            rejected.append({**_brief(record), "reason": record.get("reason") or "LLM_NULL"})
            continue
        for entry in models:
            reason, hardware = _validate_entry(entry, record, index, used)
            if reason:
                rejected.append({**_brief(record), "model": entry.get("model"), "reason": reason})
                continue
            used.add(hardware["hardware_id"])
            offers.append({
                "hardware_id": hardware["hardware_id"],
                "category": record["category"],
                "title": record.get("title") or "",
                "url": record.get("url") or "",
                "item_id": record.get("item_id") or "",
                "shop": "淘宝",
                "price_fen": int(round(float(entry["price_cny"]) * 100)),
                "sample_count": 1,
                "spread": 0.0,
                "source_model": entry.get("model"),
            })
    payload = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": "llm-split",
        "price_basis": "ITEM_DETAIL",
        "observed_at": date.today().isoformat(),
        "offers": offers,
        "rejected": rejected,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"通过校验 {len(offers)} 条，拒绝 {len(rejected)} 条 -> {OUTPUT_PATH.name}")
    return 0


def _validate_entry(entry: dict[str, Any], record: dict[str, Any],
                    index: dict[str, list[dict[str, Any]]],
                    used: set[str]) -> tuple[str, dict[str, Any] | None]:
    """返回 (拒绝原因, 命中的主库硬件)；原因为空字符串表示通过。"""

    try:
        price = float(entry.get("price_cny"))
    except (TypeError, ValueError):
        return "PRICE_NOT_NUMERIC", None
    low, high = PRICE_RANGE_FEN[record["category"]]
    if not low <= price * 100 <= high:
        return "PRICE_OUT_OF_RANGE", None
    hardware, reason = match_hardware(
        str(entry.get("model") or ""), record["category"],
        str(entry.get("brand") or ""), index)
    if hardware is None:
        return reason, None
    if hardware["hardware_id"] in used:
        return "DUPLICATE_HARDWARE", None
    return "", hardware


def _brief(record: dict[str, Any]) -> dict[str, Any]:
    return {"item_id": record.get("item_id"), "category": record.get("category"),
            "title": record.get("title")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM 拆解 CPU/GPU 混卖链接并做规则校验")
    parser.add_argument("step", choices=("collect", "split", "emit", "all"))
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个商品")
    args = parser.parse_args(argv)
    if args.step in ("collect", "all"):
        code = collect_details(args.limit)
        if code != 0:
            return code
    if args.step in ("split", "all"):
        code = run_split(args.limit)
        if code != 0:
            return code
    if args.step in ("emit", "all"):
        return emit_offers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
