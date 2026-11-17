---
document_id: kb-data-storage-price-bands
title: 存储价格分档与每 TB 单价分布
source_type: DATASET_SNAPSHOT
source_name: PCPP/PassMark 数据集快照
confidence_level: HIGH
version: 1
---

# 存储价格分档与每 TB 单价分布

## 结论

- 1485 条存储中，NVMe SSD 591 条、HDD 520 条、SATA SSD 365 条，另有 9 条无法归类；NVMe 占 39.8%，HDD 占 35.0%，SATA SSD 占 24.6%。
- 每 TB 单价中位数：NVMe 为 1576.80 元/TB（n=587），SATA SSD 为 2454.47 元/TB（n=356），HDD 为 475.86 元/TB（n=518）。SATA SSD 比 NVMe 高约 55.7%，HDD 约为 NVMe 的 30.2%。
- NVMe 在不同容量下的每 TB 单价：500 GB 及以下 2474.45，1 TB 1655.93，2 TB 1399.48，4 TB 及以上 1405.11 元/TB；2 TB 档单价最低。
- 全表按容量看，价格中位数随容量上升：500 GB 及以下 734.40 元，1 TB 1374.59 元，2 TB 2440.73 元，4 TB 及以上 3815.93 元。
- HDD 的容量效应最明显：4 TB 及以上为 375.00 元/TB，2 TB 为 644.40，1 TB 为 892.80。

## 数据依据

- 数据文件：`pcpp_storage.csv`（1485 行，快照日期 2026-10-05）。
- 过滤规则：剔除 `price<=0`（0 条）与高于 P99=17059.85 元的 15 条长尾，实际统计 1470 条；容量从 `capacity` 字段按 1 TB=1000 GB 换算，无法解析的行不参与每 TB 计算。
- 分类规则：`spec_type=SSD` 且 `nvme=Yes` 记为 NVMe；`spec_type=SSD` 且 `nvme=No` 记为 SATA SSD；`spec_type` 含 `RPM` 记为 HDD。
- 每 TB 单价 = `price / 容量(TB)`，取中位数；小容量与老旧型号会抬高单价，因此同时给出容量分档结果。
- 价格单位：人民币元。`price_gb` 字段与 `price/容量` 的比值中位为 7.20，属于美元口径，未用于本卡片计算。
- PassMark `passmark_disk.csv` 含 16115 条磁盘跑分且关键字段完整，但本卡片只描述价格与容量分布，不引用跑分。

## 使用建议

- 用于判断“同预算下 NVMe、SATA SSD、HDD 的大致容量差”，以及“多大容量开始摊薄每 TB 成本”。
- SATA SSD 的中位单价偏高，主要受小容量与老型号样本影响；不能据此推断所有 SATA 产品都比 NVMe 贵。
- 容量、接口与主板 M.2/SATA 端口数量要一起核对；本卡片不判断具体型号的缓存、主控与寿命。
- 快照价格波动大，实际购买前必须查实时报价。
