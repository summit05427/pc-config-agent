package com.example.agent.pcbuild.domain;

/**
 * 结果中的单个硬件条目。
 *
 * @param hardware 硬件
 * @param offer    选用报价
 * @param benchmark 跑分，可为 {@code null}
 * @param specSummary 规格摘要
 */
public record BuildComponent(
        Hardware hardware,
        Offer offer,
        Benchmark benchmark,
        String specSummary) {
}
