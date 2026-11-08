# PC 配置市场报价管理

| 项 | 内容 |
| --- | --- |
| 状态 | 已验证（对照 2026-11-08 `offers.json` 与入库脚本） |
| 最后核验 | 2026-11-08 |
| 权威性 | 本文件描述人工核验报价的选品口径、录入与校验流程；字段结构见 [data-model.md](./data-model.md)，术语见 [glossary.md](./glossary.md) |
| 主要证据 | `scripts/pc-config/ingest_offers.py`、`scripts/pc-config/tests/test_offers.py`、[offers.template.json](./offers.template.json)、`pc-config/offers.json` |

## 1. 选品口径

- 只收**京东自营**或**品牌官方旗舰店**的在售商品；不收第三方店铺、二手、矿卡、拆机件。
- CPU 只收**盒装 / 原包**，不收散片；主板、显卡、内存、存储、散热、机箱、电源按标准零售型号收录。
- 优先与 `catalog.json` 的 `model_name` 完全一致的型号。若只能买到同系列升级版或同芯片的其他品牌，必须在 `notes` 写明差异，例如当前 5060 Ti 收七彩虹战斧版、9070 XT 收华硕 PRIME、B850 收 MAX WIFI II。
- 价格只记录页面可见的到手价，币种固定 `CNY`；满减、满赠、会员价不折算，`price_type` 如实选择 `NORMAL` / `PROMO` / `MEMBER`。
- 同一硬件允许多条报价，`hardware_id` 保持不变，`offer_id` 用 `-01`、`-02` 后缀区分。

## 2. 采集与核验流程

1. 用浏览器人工打开商品页，核对店铺类型、型号、规格、SKU、页面价与活动说明。
2. 在 [offers.template.json](./offers.template.json) 中填写条目；不确定或未采购的条目保持 `match_status=PENDING`。
3. 从仓库根运行 `python scripts/pc-config/ingest_offers.py`；可先用 `--dry-run` 只校验不写文件。
4. 脚本读取 `catalog.json` 校验 `hardware_id`，通过后覆写 `application-service/src/main/resources/pc-config/offers.json`。
5. 重启 application-service，让启动期夹具缓存重新加载；求解快照不会回填。

脚本默认路径：模板 `docs/pc-config/offers.template.json`、目录 `application-service/src/main/resources/pc-config/catalog.json`、输出 `.../pc-config/offers.json`，可用 `--template`、`--catalog`、`--output` 覆盖。

## 3. 脚本校验规则

| 规则 | `VERIFIED` | `MOCK` |
| --- | --- | --- |
| `hardware_id` | 必须存在于 catalog | 必须存在于 catalog |
| 必填文本 | `offer_id`、`category`、`platform`、`seller`、`title` | `offer_id`、`category`、`title` |
| 价格 | `price_cny > 0`，最多两位小数，换算为整数分 | 同左 |
| `price_type` | 仅 `NORMAL` / `PROMO` / `MEMBER` | 强制 `NORMAL` |
| 日期 | `verified_at`、`valid_until` 为 `YYYY-MM-DD`，且后者不早于前者 | 不校验，强制 `null` |
| 链接 | `purchase_url` 必须为 `https`，禁止 PCPartPicker 域名 | 不校验，强制 `null` |
| 输出标记 | `match_status=VERIFIED`、`price_source=OWNER_VERIFIED` | `match_status=MOCK`、`price_source=MOCK_DEMO` |

`PENDING` 条目被跳过并计入 `skipped_pending`。任一条目校验失败时脚本打印全部问题并以退出码 1 结束，不写文件；没有有效报价时拒绝覆盖 `offers.json`。`offer_id` 重复同样报错。

## 4. 排除词与匹配陷阱

脚本只做字段校验，**不做标题语义过滤，也不校验卖家白名单**，以下情况必须人工排除：

- 外接显卡盒：`扩展坞`、`显卡坞`、`AI BOX` 等商品标题可能包含目标 GPU 型号，但不是显卡本体。
- 整机与套装：`整机`、`主机`、`组装机`、`主板套装`、`CPU 主板套装` 不是单件报价。
- 配件：`显卡支架`、`水冷风扇`、`硬盘盒`、`散热片`、`转接线` 容易被型号关键词命中。
- 型号后缀噪声：`GRE`、`O8G` 等系列或超频后缀可能对应不同芯片/显存版本；必须核对 `chipset` 与 `vram_gb`，不能只看标题前缀。
- CPU 散片、无盒装、无原装散热器的条目不符合口径；页面上「盒装」字样要与商品规格一致。

## 5. 当前 10 条已核验报价

全部 `verified_at=2026-11-08`、`valid_until=2026-11-15`，`price_type=NORMAL`。

| 类别 | 目录型号 | 价格（元） | `platform_sku` | 店铺 |
| --- | --- | --- | --- | --- |
| CPU | AMD Ryzen 5 9600X | 1269 | 100110580225 | AMD京东自营旗舰店 |
| CPU | AMD Ryzen 7 9800X3D | 2999 | 100147630258 | AMD京东自营旗舰店 |
| CPU | Intel Core Ultra 5 245K | 1229 | 100145512964 | 英特尔京东自营旗舰店 |
| CPU | Intel Core Ultra 7 265K | 1869 | 100120799071 | 英特尔京东自营旗舰店 |
| GPU | GeForce RTX 5060 Ti 16GB | 6649 | 100160762603 | 七彩虹京东自营旗舰店 |
| GPU | GeForce RTX 5070 Ti 16GB | 13999 | 100200707220 | 微星京东自营旗舰店 |
| GPU | Radeon RX 9060 XT 16GB | 5199 | 100216218685 | 撼讯京东自营旗舰店 |
| GPU | Radeon RX 9070 XT 16GB | 7299 | 100193357148 | 华硕京东自营旗舰店 |
| MOTHERBOARD | MSI MAG B850 TOMAHAWK MAX WIFI | 1849 | 100430896544 | 微星京东自营旗舰店 |
| MOTHERBOARD | Asus TUF GAMING B860M-PLUS WIFI | 1299 | 10134850633266 | 华硕官方旗舰店 |

其中 9 条为京东自营，1 条为品牌官方旗舰店；RTX 5070 Ti 页面价明显高于参考价，已记录待复核。

## 6. 18 条 MOCK 说明

18 条 MOCK 覆盖主板 2、内存 4、存储 3、散热 3、机箱 3、电源 3，均为 `platform=MOCK_DEMO`、`seller=演示数据`、`purchase_url=null`、`verified_at=null`、`valid_until=null`、`match_status=MOCK`。它们只为打通端到端链路，价格是占位值，不能用于采购或预算结论；替换前会持续参与演示求解。

## 7. 复核与替换步骤

1. 先检查 `valid_until`，临近或已过期的条目重新打开商品页核验。
2. 更新 `price_cny`、`platform_sku`、`title`、`verified_at`、`valid_until`，必要时补充 `notes`。
3. 把 MOCK 条目改为 `match_status=VERIFIED`，补齐 `platform`、`seller`、`shop_name`、`purchase_url`、日期与 `price_type`。
4. 先跑 `python scripts/pc-config/ingest_offers.py --dry-run`，确认无校验问题再正式运行。
5. 重启 Java 并复跑一次求解；MOCK 归零后 `data_status` 才会从 `MIXED_DEMO` 变为 `OWNER_VERIFIED`。

## 8. 【未实现】

- 自动抓取、定时复核、价格历史与降价提醒。
- `purchase_url` 可达性、SKU 唯一性与卖家白名单的自动校验。
- 价格异常检测（如明显偏离参考价）与核验截图留存。
- 过期报价的自动清理或状态流转。
