package com.example.agent.pcbuild.domain;

import java.util.Objects;
import java.util.StringJoiner;

/**
 * 候选硬件。
 *
 * @param hardwareId           稳定标识，来自 fixture，跨求解与快照复用
 * @param category             所属类别
 * @param brand                品牌
 * @param modelName            型号名
 * @param displayName          展示名，可为 {@code null}
 * @param specifications       归一化规格
 * @param dataQualityStatus    数据质量状态，{@code PARTIAL} 表示存在未核验字段
 * @param lifecycleStatus      生命周期状态
 * @param recommendationStatus 推荐状态，只有 {@code ELIGIBLE} 可进入求解
 */
public record Hardware(
        String hardwareId,
        HardwareCategory category,
        String brand,
        String modelName,
        String displayName,
        HardwareSpecifications specifications,
        String dataQualityStatus,
        String lifecycleStatus,
        String recommendationStatus) {

    private static final String RECOMMENDATION_ELIGIBLE = "ELIGIBLE";
    private static final String LIFECYCLE_DISCONTINUED = "DISCONTINUED";
    private static final String LIFECYCLE_EOL = "EOL";
    private static final String UNKNOWN_LABEL = "UNKNOWN";

    public Hardware {
        Objects.requireNonNull(hardwareId, "hardwareId");
        Objects.requireNonNull(category, "category");
        Objects.requireNonNull(specifications, "specifications");
    }

    /**
     * 是否允许进入求解候选池。
     *
     * <p>下架与停产硬件不参与推荐，避免把无法购买的商品算进预算。</p>
     *
     * @return 推荐状态为 {@code ELIGIBLE} 且非停产时为 {@code true}
     */
    public boolean isSolverEligible() {
        boolean isRecommended = RECOMMENDATION_ELIGIBLE.equalsIgnoreCase(recommendationStatus);
        boolean isRetired = LIFECYCLE_DISCONTINUED.equalsIgnoreCase(lifecycleStatus)
                || LIFECYCLE_EOL.equalsIgnoreCase(lifecycleStatus);
        return isRecommended && !isRetired;
    }

    /**
     * 生成面向调用方的规格摘要。
     *
     * <p>摘要只用于展示，不参与规则判断；缺失字段显示为 {@code UNKNOWN}，
     * 避免调用方把空值误读成已确认。</p>
     *
     * @return 单行规格摘要
     */
    public String specSummary() {
        HardwareSpecifications spec = specifications;
        return switch (category) {
            case CPU -> join(
                    "socket=" + text(spec.socket()),
                    pair(spec.coreCount(), spec.threadCount()) + "T",
                    wattage(spec.tdpW()));
            case GPU -> join(
                    "chipset=" + text(spec.chipset()),
                    text(spec.vramGb()) + "GB " + text(spec.memoryType()),
                    text(spec.lengthMm()) + "mm",
                    wattage(spec.tdpW()));
            case MOTHERBOARD -> join(
                    "socket=" + text(spec.socket()),
                    text(spec.formFactor()),
                    text(spec.memoryType()),
                    "M.2x" + text(spec.m2SlotCount()));
            case MEMORY -> join(
                    text(spec.memoryType()),
                    text(spec.capacityGb()) + "GB (" + text(spec.moduleCount())
                            + "x" + text(spec.moduleSizeGb()) + "GB)",
                    text(spec.speedMts()) + "MT/s",
                    "CL" + text(spec.casLatency()));
            case STORAGE -> join(
                    text(spec.capacityGb()) + "GB",
                    text(spec.interfaceType()),
                    text(spec.formFactor()));
            case COOLER -> join(
                    text(spec.coolerType()),
                    text(spec.heightMm()) + "mm",
                    "sockets=" + (spec.supportedSockets() == null ? UNKNOWN_LABEL
                            : String.join("/", spec.supportedSockets())));
            case CASE -> join(
                    "mb=" + (spec.supportedMainboardFormFactors() == null ? UNKNOWN_LABEL
                            : String.join("/", spec.supportedMainboardFormFactors())),
                    "gpu<=" + text(spec.maxGpuLengthMm()) + "mm",
                    "cooler<=" + text(spec.maxCoolerHeightMm()) + "mm");
            case PSU -> join(
                    text(spec.wattageW()) + "W",
                    text(spec.efficiency()),
                    "8pin x" + text(spec.pcie8pinCount()),
                    "12VHPWR x" + text(spec.pcie12vhpwrCount()));
        };
    }

    private static String pair(Integer cores, Integer threads) {
        return text(cores) + "C/" + text(threads);
    }

    private static String wattage(Integer tdpW) {
        return tdpW == null ? "TDP=" + UNKNOWN_LABEL : tdpW + "W";
    }

    private static String text(Object value) {
        return value == null ? UNKNOWN_LABEL : String.valueOf(value);
    }

    private static String join(String... parts) {
        StringJoiner joiner = new StringJoiner("; ");
        for (String part : parts) {
            if (part != null && !part.isBlank()) {
                joiner.add(part);
            }
        }
        return joiner.toString();
    }
}
