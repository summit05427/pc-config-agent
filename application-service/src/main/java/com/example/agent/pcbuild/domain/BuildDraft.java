package com.example.agent.pcbuild.domain;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 兼容性校验后、落库前的完整方案。
 *
 * @param requirements        原始需求
 * @param selection           八件硬件
 * @param offers              每个类别实际选用的报价
 * @param benchmarks          每个类别可用的跑分
 * @param totalPriceFen       总价，单位分
 * @param compatibilityReport 兼容性报告
 * @param scenarioScore       场景性能分
 * @param catalogVersion      目录版本
 * @param offerDataStatus     报价数据状态，如 {@code MIXED_DEMO}
 */
public record BuildDraft(
        BuildRequirements requirements,
        HardwareSelection selection,
        Map<HardwareCategory, Offer> offers,
        Map<HardwareCategory, Benchmark> benchmarks,
        long totalPriceFen,
        CompatibilityReport compatibilityReport,
        long scenarioScore,
        String catalogVersion,
        String offerDataStatus) {

    public BuildDraft {
        offers = copyOrdered(offers);
        benchmarks = copyOrdered(benchmarks);
    }

    private static <T> Map<HardwareCategory, T> copyOrdered(Map<HardwareCategory, T> source) {
        Map<HardwareCategory, T> ordered = new LinkedHashMap<>();
        if (source != null) {
            for (HardwareCategory category : HardwareCategory.REQUIRED_CATEGORIES) {
                T value = source.get(category);
                if (value != null) {
                    ordered.put(category, value);
                }
            }
        }
        return Collections.unmodifiableMap(ordered);
    }
}
