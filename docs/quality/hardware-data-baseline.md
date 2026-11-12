# 硬件数据基线核查

| 项 | 内容 |
| --- | --- |
| 生成方式 | `scripts/pc-config/inspect_dataset.py` 自动生成，不得手改 |
| 扫描时间 | 2026-11-09T05:26:01+00:00 |
| 数据目录 | `F:\LLM_PC_Agent\Hardware data`（只读） |
| 权威性 | Stage 8.1 事实基线；后续治理报告以此为准 |

## 1. 规模总览

| 指标 | 数量 |
| --- | --- |
| PCPartPicker 硬件 | 8238 |
| PassMark 跑分 | 25318 |
| 输入文件 | 11 |
| 原始归档文件 | 18 |
| 原始归档体积 | 31.8 MB |

## 2. 数据文件清单

| 文件 | 行数 | 列数 | 体积 | sha256 |
| --- | --- | --- | --- | --- |
| `csv/pcpp_cpu.csv` | 493 | 32 | 198 KB | `9db34e0a26d1a88e…` |
| `csv/pcpp_gpu.csv` | 1109 | 56 | 577 KB | `76de3651dd40a3a9…` |
| `csv/pcpp_motherboard.csv` | 781 | 49 | 924 KB | `2046ec1cd26b9530…` |
| `csv/pcpp_memory.csv` | 1891 | 22 | 821 KB | `6b27906b62df8500…` |
| `csv/pcpp_storage.csv` | 1485 | 32 | 651 KB | `839ab1edb23fad2c…` |
| `csv/pcpp_cooler.csv` | 863 | 19 | 790 KB | `83e27128a3604286…` |
| `csv/pcpp_case.csv` | 1098 | 26 | 1281 KB | `de49330832e7ebe5…` |
| `csv/pcpp_psu.csv` | 518 | 28 | 264 KB | `f57eb78719d0cc37…` |
| `csv/passmark_cpu.csv` | 6171 | 15 | 681 KB | `b65b54d4421f6124…` |
| `csv/passmark_gpu.csv` | 3032 | 13 | 273 KB | `a5b4b5857222b40f…` |
| `csv/passmark_disk.csv` | 16115 | 12 | 1612 KB | `782ba3b3f794cfca…` |

> 原始归档只登记文件与体积，不纳入版本库；哈希仅覆盖 `csv/` 输入。

## 3. 八类别分布与兼容性关键字段

| 类别 | 行数 | 列数 | 关键字段缺失 |
| --- | --- | --- | --- |
| CPU | 493 | 32 | socket 0 (0.0%)；core_count 0 (0.0%)；tdp 0 (0.0%) |
| GPU | 1109 | 56 | chipset 0 (0.0%)；memory 0 (0.0%)；tdp 0 (0.0%)；length 24 (2.2%)；case_expansion_slot_width 0 (0.0%) |
| MOTHERBOARD | 781 | 49 | socket_cpu 0 (0.0%)；chipset 0 (0.0%)；form_factor 0 (0.0%)；memory_type 0 (0.0%)；m_2_slots 31 (4.0%) |
| MEMORY | 1891 | 22 | speed 0 (0.0%)；modules 0 (0.0%) |
| STORAGE | 1485 | 32 | capacity 0 (0.0%)；spec_type 0 (0.0%)；interface 0 (0.0%) |
| COOLER | 863 | 19 | cpu_socket 0 (0.0%)；height 229 (26.5%) |
| CASE | 1098 | 26 | motherboard_form_factor 1 (0.1%)；maximum_video_card_length 26 (2.4%)；dimensions 59 (5.4%) |
| PSU | 518 | 28 | wattage 0 (0.0%)；length 7 (1.4%) |

## 4. 字段缺失率（缺失数大于 0 的列）

**CPU**（493 行，32 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `model` | 489 (99.2%) | 0 |
| `efficiency_core_clock` | 448 (90.9%) | 0 |
| `efficiency_core_boost_clock` | 448 (90.9%) | 0 |
| `maximum_supported_memory` | 220 (44.6%) | 0 |
| `performance_core_boost_clock` | 173 (35.1%) | 0 |
| `image_url` | 43 (8.7%) | 0 |

**GPU**（1109 行，56 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `mini_display_port_1_4_outputs` | 1108 (99.9%) | 0 |
| `vhdci_outputs` | 1107 (99.8%) | 0 |
| `s_video_outputs` | 1107 (99.8%) | 0 |
| `mini_display_port_2_1_outputs` | 1106 (99.7%) | 0 |
| `hdmi_1_4_outputs` | 1106 (99.7%) | 0 |
| `dvi_d_single_link_outputs` | 1106 (99.7%) | 0 |
| `mini_display_port_2_1b_outputs` | 1105 (99.6%) | 0 |
| `usb_type_c_outputs` | 1104 (99.5%) | 0 |
| `hdmi_2_0_outputs` | 1104 (99.5%) | 0 |
| `dvi_outputs` | 1104 (99.5%) | 0 |
| `display_port_2_0_outputs` | 1102 (99.4%) | 0 |
| `hdmi_2_0b_outputs` | 1100 (99.2%) | 0 |
| …其余 25 列 | | |

**MOTHERBOARD**（781 行，49 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `half_mini_pcie_slots` | 780 (99.9%) | 0 |
| `mini_pcie_m_sata_slots` | 780 (99.9%) | 0 |
| `sas_3_0_gb_s_ports` | 780 (99.9%) | 0 |
| `mini_pcie_slots` | 780 (99.9%) | 0 |
| `pata_100_ports` | 779 (99.7%) | 0 |
| `pcie_x16_gc_hpwr_slots` | 777 (99.5%) | 0 |
| `e_sata_6_0_gb_s_ports` | 777 (99.5%) | 0 |
| `u_2_ports` | 776 (99.4%) | 0 |
| `pata_133_ports` | 775 (99.2%) | 0 |
| `e_sata_3_0_gb_s_ports` | 773 (99.0%) | 0 |
| `pcie_x8_slots` | 769 (98.5%) | 0 |
| `sata_3_0_gb_s_ports` | 762 (97.6%) | 0 |
| …其余 16 列 | | |

**MEMORY**（1891 行，22 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `model` | 1889 (99.9%) | 0 |
| `timing` | 966 (51.1%) | 0 |
| `color` | 100 (5.3%) | 0 |
| `image_url` | 47 (2.5%) | 0 |
| `price_gb` | 2 (0.1%) | 0 |

**STORAGE**（1485 行，32 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `power_loss_protection` | 1477 (99.5%) | 0 |
| `hybrid_ssd_cache` | 1476 (99.4%) | 0 |
| `model` | 1475 (99.3%) | 0 |
| `ssd_controller` | 1419 (95.6%) | 0 |
| `ssd_nand_flash_type` | 1330 (89.6%) | 0 |
| `full_disk_write_throughput` | 1252 (84.3%) | 0 |
| `full_disk_write_throughput_lowest_10_seconds` | 1252 (84.3%) | 0 |
| `random_read_throughput_qd1` | 1252 (84.3%) | 0 |
| `random_read_throughput_qd32` | 1252 (84.3%) | 0 |
| `random_write_throughput_qd1` | 1252 (84.3%) | 0 |
| `random_write_throughput_qd32` | 1252 (84.3%) | 0 |
| `sequential_read_throughput_qd1` | 1252 (84.3%) | 0 |
| …其余 6 列 | | |

**COOLER**（863 行，19 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `bearing` | 847 (98.1%) | 0 |
| `model` | 460 (53.3%) | 0 |
| `height` | 229 (26.5%) | 0 |
| `noise_level` | 88 (10.2%) | 0 |
| `fan_rpm` | 75 (8.7%) | 0 |
| `color` | 66 (7.6%) | 0 |
| `image_url` | 3 (0.3%) | 0 |

**CASE**（1098 行，26 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `model` | 1022 (93.1%) | 0 |
| `included_fans` | 842 (76.7%) | 161 |
| `radiator_support` | 110 (10.0%) | 890 |
| `dimensions` | 59 (5.4%) | 1039 |
| `volume` | 59 (5.4%) | 1039 |
| `maximum_video_card_length` | 26 (2.4%) | 1072 |
| `color` | 12 (1.1%) | 0 |
| `fan_support` | 11 (1.0%) | 954 |
| `image_url` | 10 (0.9%) | 0 |
| `drive_bays` | 10 (0.9%) | 885 |
| `expansion_slots` | 3 (0.3%) | 166 |
| `motherboard_form_factor` | 1 (0.1%) | 1030 |

**PSU**（518 行，28 列）

| 列 | 缺失 | 多行取值 |
| --- | --- | --- |
| `output` | 474 (91.5%) | 0 |
| `model` | 333 (64.3%) | 0 |
| `color` | 46 (8.9%) | 0 |
| `efficiency_rating` | 42 (8.1%) | 0 |
| `length` | 7 (1.4%) | 0 |
| `image_url` | 1 (0.2%) | 0 |

## 5. 重复情况

| 类别 | pcpp_id 重复 | part_number 重复 | 品牌+名称重复 |
| --- | --- | --- | --- |
| CPU | 0 | 1 | 4 |
| GPU | 0 | 1 | 41 |
| MOTHERBOARD | 0 | 0 | 0 |
| MEMORY | 0 | 0 | 296 |
| STORAGE | 0 | 1 | 119 |
| COOLER | 0 | 0 | 216 |
| CASE | 0 | 0 | 376 |
| PSU | 0 | 0 | 48 |

> 重复数只表示「多出来的行数」，不等于冲突；是否合并由 Stage 8.4 判定。

## 6. PassMark 关联情况（粗测）

> 本节只用于判断规模，正式匹配方法与置信度由 Stage 8.5 输出。粗测采用归一化令牌子串匹配。

| 对象 | 命中 | 总数 | 粗测命中率 |
| --- | --- | --- | --- |
| CPU | 450 | 493 | 91.3% |
| GPU（芯片级） | 1099 | 1109 | 99.1% |
| 存储 | 978 | 1485 | 65.9% |

显卡板卡 1109 条对应 242 个芯片型号，PassMark 侧有 2924 个型号键，因此显卡跑分只能是芯片级多对一。

## 7. 已知异常

1. PCPartPicker 八张分类表均无 release_date 字段，生命周期无法直接由发布日期判定：CPU、GPU、MOTHERBOARD、MEMORY、STORAGE、COOLER、CASE、PSU
2. 内存表无独立 DDR 类型字段，只能从 speed 派生（DDR5/DDR4/DDR3/DDR2）
3. 散热器 height 缺失 229/863，机箱限高规则会返回 UNKNOWN
4. 机箱 maximum_video_card_length 缺失 26 条
5. 显卡为板卡级共 1109 条、242 个芯片型号，PassMark 显卡为芯片级 2924 个键，映射天然多对一
6. PassMark CPU 主指标完整，无缺失
7. PassMark GPU 主指标完整，无缺失
8. PassMark DISK 主指标完整，无缺失
9. PCPartPicker 价格为美元参考价（2026-10 快照），不得作为人民币报价写入主数据
10. PassMark 存储型号名含 2.5"、反斜杠等脏字符，需要在映射阶段额外容错
11. raw/pcpp/images.json 仅 1,600 条映射，图片应以 CSV 的 image_url 为准

## 8. 对后续阶段的输入

- 原始数据保持只读，治理产物写入 `data/pc-config/`，不在本阶段生成。
- 关键字段缺失集中在散热器高度与机箱尺寸，需在 Stage 8.3 明确 `missing_reason`。
- 生命周期缺少发布日期基础，按 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §3.3 分类别推进。
- 显卡跑分按芯片级映射，按 [PC 配置模块决策合并记录](../adr/0027-pc-config-decisions.md) §3.3 与 `glossary.md` 的「匹配范围」口径表述。
