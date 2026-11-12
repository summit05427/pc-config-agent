# Handoff: pc-catalog-benchmark-image-handoff

2026-11-12 15:30 +08:00 · agent-project-template-main / feature/pc-config-data-governance · Agent: TraeCode

## Unfinished Tasks

1. [pending] 数据库导入落地 — 把 `catalog.json` + `benchmarks.json` 从内存 fixture 迁移到 PostgreSQL：新建 `pc_hardware`、`pc_benchmark` 表与 Flyway 迁移脚本，写导入器（catalog 410 行、benchmark 176 行），保留 `hardware_id` 主键与 `stratum` 索引。
2. [pending] 补 51 条产品图 — 48 条国行补充型号（`cn-models.jsonl` 无 PCPP 来源）+ 3 条 PCPP 记录在 `pcpp_hardware_all.csv` 里 `image_url` 为空；需从京东单品页采集主图后写入 `data/pc-config/cleaning/image-map.json`。
3. [pending] 22 条硬盘跑分缺口 — PassMark 用 WDC/希捷料号命名（WD Blue 4TB、Red Plus 2TB、IronWolf Pro、N300/P300/L200），且快照缺 VD10/P510/G50/KP260/MP600 LPX；如需补齐要建立「商品名 → 料号」映射表，不能用家族名猜分数。
4. [pending] 文档同步 — 根 `docs/data/交接文档.md`、`docs/INDEX.md` 尚未反映本轮剔除规则、价格状态降级、跑分/图片映射链路。

## Goal

把 PC 配置推荐 Agent 的硬件候选池收尾：按「国内无售 / 企业级非 DIY / 国内不零售」剔除脏数据，核验 410 条候选池的价格与覆盖度，并把 `F:/LLM_PC_Agent/Hardware data` 里的 PassMark 跑分与产品图接入运行时目录。

## Done

- 剔除规则收敛：`is_excluded` 对 410 条短名单命中 0。新增剔除 PSU 品牌 Apevia / Athena Power / CoolMax / Chieftec，机箱 Anidees / HYTE（仅欧美渠道）；存储新增 `st4000nm`、`travelstar` 企业/停产盘 token。
- 散热器分层修正：`fix_cooler_stratum` 改为以 `water_cooled` 规格为准，名称关键词兜底；`COOLER_STRATUM_OVERRIDES` 修正利民 U120 EX EVO、PA120 Digital（型号名里的 120 是风扇尺寸）。
- 价格状态诚实化：列表页 + 档位/区间话术的 100 条「伪观测」在 `apply_price_observations.py` 里降级为 `ESTIMATED_2026-11-11`；最终 OBSERVED 248 / ESTIMATED 162，0 条无价。
- 128GB DDR5 兜底价从 ¥2800（32GB 基准误套）改为 ¥14999 LOW，并在 note 标注推算依据。
- 新增 [build_benchmark_image_maps.py](../../scripts/data-cleaning/build_benchmark_image_maps.py)：PassMark CPU 72/72、GPU 72/72、硬盘 32/54 匹配，全部为型号级匹配（不猜分）；产物 `benchmark-map.json`、`image-map.json`，重复执行字节一致。
- [export_runtime_catalog.py](../../scripts/data-cleaning/export_runtime_catalog.py) 现在同时：回填 `source.image_url`、把 `benchmarks.json` 写到 `data/pc-config/export/runtime-full/` 与 `application-service/src/main/resources/pc-config/`。
- 测试：pytest 50 passed；`PcFixtureRepositoryTests` + `BuildSolverBenchmarkTests` EXIT=0（测试内 5070 Ti 的 id 改为目录里真实存在的 `gpu-geforce-rtx-5070-ti-16gb-563955`）。

## In Progress / Next

下一步从「数据库导入落地」开始：先确认是否保留内存 fixture 双写，再写 Flyway 迁移 + 导入器。不要先做第 2、3 项采集，它们依赖外部站点且本轮未授权抓取。

## Key Files & Paths

- `scripts/data-cleaning/stage4_hot_shortlist.py` — 配额、分层、剔除规则（`NO_CN_RETAIL_IDS`、`OVERSEAS_ONLY_TOKENS`、`COOLER_STRATUM_OVERRIDES`、`fix_cooler_stratum`）
- `scripts/data-cleaning/apply_price_observations.py` — 观测账本合并、`overwrite` 语义、档位价降级（`CATEGORY_LIST_URLS`）
- `scripts/data-cleaning/stage4_price_fallback.py` — 规格档位兜底价；跳过 `price_source=WEBSEARCH` 的行
- `scripts/data-cleaning/build_benchmark_image_maps.py` — PassMark/图片映射生成器
- `scripts/data-cleaning/export_runtime_catalog.py` — 导出 catalog + benchmarks 到两处副本
- `data/pc-config/cleaning/stage4-shortlist.jsonl` — 410 条候选池（价格唯一来源）
- `data/pc-config/cleaning/stage4-price-observations.jsonl` — 价格观测账本（367 行，只追加）
- `data/pc-config/cleaning/benchmark-map.json` / `image-map.json` — 跑分与图片映射
- `data/pc-config/export/runtime-full/catalog.json` / `catalog-full.json` — 运行时目录与全量快照
- `application-service/src/main/resources/pc-config/catalog.json` / `benchmarks.json` — Java 运行时读取
- `application-service/src/test/java/com/example/agent/pcbuild/PcFixtureRepositoryTests.java` — 目录与跑分夹具测试
- `F:/LLM_PC_Agent/Hardware data/csv/` — 只读数据源（passmark_*.csv、pcpp_hardware_all.csv）

## Decisions & Gotchas

- 观测账本只追加，历史行永不改写；修正一律追加 `"overwrite": true` 新记录。
- 价格唯一来源是短名单；`cn-models.jsonl` 只提供型号与规格，不再自带价格。
- 禁止用同芯片/同系列/同容量档推算价格；搜不到保留估价并标 LOW。美元价不折算。
- 档位价记录（列表页 URL + 「档位/上浮/下浮/区间」话术）不再标 OBSERVED；否则预算估算会把区间中值当精确单价。
- 硬盘匹配曾尝试「家族名兜底」，会把 Seagate BarraCuda 配成 Sabrent、Toshiba P300 配成 Patriot P300，已整体删除；宁缺勿错。
- `water_cooled` 为 `None` 时不能靠塔体高度判断风冷（水冷也会被填 120/240 之类数字），只认规格 + 名称关键词。
- 目录 `generated_at` 每次导出都变，因此 catalog 的 MD5 不稳定；`benchmark-map.json` / `image-map.json` 用数据快照日期生成时间，字节稳定。
- 流水线顺序固定：`stage4_hot_shortlist` → `apply_price_observations` → `stage4_price_fallback` → `build_benchmark_image_maps` → `export_runtime_catalog`。

**Skills.** 无强制技能；改 `docs/` 前先看 `.trae/rules/00-monorepo-common.md` 的文档路由。

## How to Verify

```powershell
python scripts\data-cleaning\stage4_hot_shortlist.py
python scripts\data-cleaning\apply_price_observations.py
python scripts\data-cleaning\stage4_price_fallback.py
python scripts\data-cleaning\build_benchmark_image_maps.py
python scripts\data-cleaning\export_runtime_catalog.py
python -m pytest scripts\data-cleaning\tests scripts\pc-config\tests\test_existing_catalog.py -q
cd application-service; .\mvnw.cmd -q "-Dtest=PcFixtureRepositoryTests,BuildSolverBenchmarkTests" test
```

预期输出：`benchmark_entries=176`（72/72/32）、`benchmark_unmatched=22`、`image_missing=51`、`exported=410 missing_in_catalog=0`、pytest `50 passed`、Maven `EXIT=0`。
