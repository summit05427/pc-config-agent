# 市场报价管理

| 项 | 内容 |
| --- | --- |
| 适用范围 | 运行时 `offers.json` 的来源、平台观测价口径、核验升级与发布 |
| 状态 | Current |
| 最后更新 | 2026-11-17 |
| 权威性 | 本文描述报价运营流程；字段结构见 [data.md](./data.md)，接口字段以 [docs/api-contract.md](../api-contract.md) §5.7 为准 |
| 主要证据 | `scripts/data-cleaning/build_offers_from_shortlist.py`、`scripts/data-cleaning/stage4-price-observations.jsonl`、`application-service/src/main/resources/pc-config/offers.json` |

## 1. 结论先行

- 当前报价 **402 条全部为 `PLATFORM_OBSERVED`**，`data_status=PLATFORM_OBSERVED_ONLY`，没有任何 `OWNER_VERIFIED`。
- 平台观测价只能作为参考价展示，不能表述为人工核验价。
- 同一硬件允许多条报价；运行时取最低有效报价，价格相同按 `offer_id` 升序。
- `offers.json` 是价格唯一运行时出口，`catalog.json` 的参考价不参与预算。
- 购买链接不是入库门槛；链接只用于来源展示。

## 2. 价格来源

| `price_source` | 含义 | 用户侧表述 |
| --- | --- | --- |
| `OWNER_VERIFIED` | 人工核验价，`match_status=VERIFIED` | 已核验价 |
| `PLATFORM_OBSERVED` | 平台检索/估算得到的参考价，`match_status=OBSERVED` | 参考价（平台观测，未经人工核验） |
| `MOCK_DEMO` | 演示占位价 | 演示价格，非真实在售 |

`verified_offer_count` 只统计 `OWNER_VERIFIED`；`PLATFORM_OBSERVED` 与 `MOCK_DEMO` 都不计入。`BuildResult.demoOfferCount` 统计非 `OWNER_VERIFIED` 条目，因此当前快照中该值会把平台观测价一并计入，不能据此判定「演示价」。

## 3. 运行时生成链路

```text
data/pc-config/cleaning/stage4-shortlist.jsonl          （候选与价格来源）
  → stage4-price-observations.jsonl                     （人工/脚本追加价格观测）
  → apply_price_observations.py
  → stage4_price_fallback.py
  → export_runtime_catalog.py        → catalog.json
  → build_offers_from_shortlist.py   → offers.json
```

- `build_offers_from_shortlist.py` 读取短名单，`price_cny × 100 → price_fen`，并写整体 `data_status`。
- 当前短名单 402 条，因此 catalog 与 offers 都是 402 条，一一对应。
- `scripts/pc-config/ingest_offers.py` 是旧入口，不在运行时链路中；不要在未确认的情况下用它覆盖现有 `offers.json`。

## 4. 录入与核验规则（升级 `OWNER_VERIFIED` 时）

| 规则 | `OWNER_VERIFIED` | `MOCK_DEMO` |
| --- | --- | --- |
| `hardware_id` | 必须存在于 catalog | 必须存在于 catalog |
| 必填文本 | `offer_id`、`category`、`platform`、`seller`、`title` | `offer_id`、`category`、`title` |
| 价格 | `price_cny > 0`，最多两位小数，换算整数分 | 同左 |
| `price_type` | `NORMAL` / `PROMO` / `MEMBER` | 强制 `NORMAL` |
| 日期 | `verified_at`、`valid_until` 为 `YYYY-MM-DD`，后者不早于前者 | 强制 `null` |
| 链接 | 可空；非空时只接受 `http(s)` | 可空 |
| 输出标记 | `match_status=VERIFIED`、`price_source=OWNER_VERIFIED` | `match_status=MOCK`、`price_source=MOCK_DEMO` |

- CPU 只收盒装/原包，不收散片；其余类别按标准零售型号收录。
- 型号必须与 `model_name` 对齐；只能买到同系列升级版或同芯片其他品牌时，在 `notes` 写明差异。
- 价格只记录页面可见到手价，币种固定 `CNY`；满减、会员价按 `price_type` 如实选择。
- 任一条目校验失败时脚本应整体拒绝写文件，不产生半套报价。

## 5. 升级与复核步骤

1. 打开商品页，核对型号、规格、SKU、页面价与有效期。
2. 在 `stage4-price-observations.jsonl` 追加观测；修正历史值用 `"overwrite": true`。
3. 重新运行 §3 的短名单与 offers 生成脚本，确保 `catalog_version` 与 catalog 一致。
4. 用 `--dry-run`（如脚本支持）或测试校验 `hardware_id`、价格、日期与重复 `offer_id`。
5. 重启 application-service，使夹具缓存重新加载；旧快照不回填。
6. 只有人工逐件核验完成后，`data_status` 才可能变为 `OWNER_VERIFIED`。

## 6. 匹配陷阱

- 型号后缀噪声（`GRE`、`O8G` 等）可能对应不同芯片或显存版本，必须核对 `chipset` 与 `vram_gb`。
- 外接显卡盒、整机与套装价格不是单件价；若用于定价，必须在 `notes` 标注并降级。
- 同型号多来源价格差异过大时，不取平均值伪装成观测价；保留来源与日期，交给人工复核。

## 7. 未实现

- 自动抓取、定时复核、价格历史与降价提醒。
- 价格异常检测与核验截图留存。
- 过期报价自动清理与状态流转。
- 管理端报价维护页面。

## 8. 相关文档

- 数据结构与可用性：[data.md](./data.md)
- 兼容规则：[compatibility-rules.md](./compatibility-rules.md)
- 治理报告：[hardware-data-governance-report.md](../quality/hardware-data-governance-report.md)
