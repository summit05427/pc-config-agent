"""Stage 3D：京东联盟商品查询客户端（价格 + 30 天销量）。

注意：该接口需要京东联盟实名账号与应用授权，数据限推广用途；
未配置凭证时只做配置探测，不会发起网络请求。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
ENDPOINT = "https://api.jd.com/routerjson"
METHOD = "jd.union.open.goods.query"


class JdUnionNotConfigured(RuntimeError):
    """凭证缺失时抛出，避免用空 Key 发起无效请求。"""


@dataclass(frozen=True)
class JdUnionConfig:
    app_key: str
    app_secret: str
    site_id: str
    access_token: str | None = None

    @classmethod
    def from_env(cls) -> "JdUnionConfig":
        app_key = os.getenv("JD_UNION_APP_KEY", "").strip()
        app_secret = os.getenv("JD_UNION_APP_SECRET", "").strip()
        site_id = os.getenv("JD_UNION_SITE_ID", "").strip()
        if not app_key or not app_secret or not site_id:
            raise JdUnionNotConfigured(
                "缺少 JD_UNION_APP_KEY / JD_UNION_APP_SECRET / JD_UNION_SITE_ID"
            )
        return cls(app_key, app_secret, site_id, os.getenv("JD_UNION_ACCESS_TOKEN") or None)


def sign(params: dict[str, str], app_secret: str) -> str:
    """京东 JOS 签名：参数按 ASCII 排序后拼接，首尾加 secret，取 MD5 大写。"""

    joined = "".join(f"{key}{params[key]}" for key in sorted(params))
    return hashlib.md5(f"{app_secret}{joined}{app_secret}".encode("utf-8")).hexdigest().upper()


def build_request(config: JdUnionConfig, keyword: str, page_size: int = 20) -> dict[str, str]:
    params = {
        "method": METHOD,
        "app_key": config.app_key,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": "1.0",
        "sign_method": "md5",
        "360buy_param_json": json.dumps(
            {
                "goodsReqDTO": {
                    "keyword": keyword,
                    "pageIndex": 1,
                    "pageSize": max(1, min(page_size, 50)),
                    "sortName": "inOrderCount30DaysSku",
                    "sort": "desc",
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    if config.access_token:
        params["access_token"] = config.access_token
    params["sign"] = sign(params, config.app_secret)
    return params


def parse_response(payload: dict) -> list[dict]:
    """兼容京东返回的 JSON 字符串嵌套结构。"""

    raw = payload.get("jd_union_open_goods_query_responce") or {}
    result = raw.get("queryResult")
    if isinstance(result, str):
        result = json.loads(result)
    items = (result or {}).get("data") or []
    parsed: list[dict] = []
    for item in items:
        price_info = item.get("priceInfo") or {}
        parsed.append({
            "sku_id": item.get("skuId"),
            "name": item.get("skuName"),
            "price_cny": price_info.get("lowestPrice") or price_info.get("price"),
            "coupon_price_cny": price_info.get("lowestCouponPrice"),
            "sales_30d": item.get("inOrderCount30Days"),
            "shop_name": (item.get("shopInfo") or {}).get("shopName"),
            "url": item.get("materialUrl"),
        })
    return parsed


def search_goods(config: JdUnionConfig, keyword: str, page_size: int = 20) -> list[dict]:
    body = urllib.parse.urlencode(build_request(config, keyword, page_size)).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return parse_response(json.loads(response.read().decode("utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3D 京东联盟查询")
    parser.add_argument("--probe", action="store_true", help="只检查凭证是否配置")
    parser.add_argument("--query", default=None, help="按关键词查询商品")
    parser.add_argument("--page-size", type=int, default=5)
    args = parser.parse_args()

    try:
        config = JdUnionConfig.from_env()
    except JdUnionNotConfigured as error:
        print(f"NOT_CONFIGURED: {error}")
        print("配置后可用：JD_UNION_APP_KEY / JD_UNION_APP_SECRET / JD_UNION_SITE_ID")
        return 2

    print("CONFIGURED")
    if args.probe or not args.query:
        return 0
    for item in search_goods(config, args.query, args.page_size):
        print(json.dumps(item, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
