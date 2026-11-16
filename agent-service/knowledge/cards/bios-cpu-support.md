---
document_id: kb-note-bios-cpu-support
title: BIOS 支持决定 CPU 可用性
source_type: INTERNAL_NOTE
source_name: 本项目知识卡片
confidence_level: HIGH
version: 1
---

# BIOS 支持决定 CPU 可用性

## 为什么不能只看插槽

同一插槽在不同代际之间可能复用，但芯片组、供电设计与 BIOS 微码支持并不相同。
主板标称支持某插槽，不代表开箱即可点亮所有该插槽的处理器。

## 核对顺序

1. 查主板厂商的 CPU 支持列表，确认目标处理器与 PCB 版本。
2. 确认所需的最低 BIOS 版本；旧批次主板可能需要先升级。
3. 确认是否支持无处理器刷新 BIOS，否则需要兼容的旧处理器过渡。
4. 核对芯片组对通道、接口与超频能力的限制。
5. 品牌整机或服务器主板的支持范围以厂商文档为准，不能套用零售主板结论。
