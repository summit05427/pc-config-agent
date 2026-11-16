---
document_id: kb-note-tdp-vs-power
title: TDP 不等于实际功耗
source_type: INTERNAL_NOTE
source_name: 本项目知识卡片
confidence_level: HIGH
version: 1
---

# TDP 不等于实际功耗

## 概念澄清

TDP 是散热设计参考值，不是电源输入功率，也不是满载功耗。
厂商对 TDP 的定义口径并不统一，有的按基础频率标称，有的允许短时间高于标称值运行。

## 对选型的影响

- 电源余量应按整机瞬时峰值估算，而不是把各部件 TDP 简单相加。
- 散热器能力要结合机箱风道、环境温度与持续负载判断。
- 低 TDP 不代表低发热，高 TDP 也不必然意味着高噪音，关键看功耗曲线与散热策略。
- 需要精确功耗时应查独立实测数据，并注明测试条件。
