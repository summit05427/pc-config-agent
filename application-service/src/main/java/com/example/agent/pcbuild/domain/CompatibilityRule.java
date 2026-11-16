package com.example.agent.pcbuild.domain;

import java.util.List;

/**
 * 九条兼容性规则。
 *
 * <p>{@code ruleId} 是对外稳定标识，改名视为契约变更。规则版本由
 * {@link CompatibilityReport#RULE_VERSION} 统一声明，便于快照追溯。
 * 每条规则携带 {@link RiskLevel}，用于说明「信息缺失」是否阻断推荐。</p>
 *
 * <p>每条规则同时声明它读取的硬件类别 {@link #requiredCategories()}：部分校验
 * （{@code validate-partial}）只执行这些类别全部已选的规则，避免在组件未选时
 * 把规则判成 {@code UNKNOWN} 污染结论。声明顺序与判定顺序一致，便于核对。</p>
 */
public enum CompatibilityRule {

    CPU_SOCKET_MOTHERBOARD("cpu_socket_motherboard", "CPU 插槽与主板插槽一致", RiskLevel.BLOCKING,
            HardwareCategory.CPU, HardwareCategory.MOTHERBOARD),
    MOTHERBOARD_MEMORY_TYPE("motherboard_memory_type", "主板内存类型与内存条一致", RiskLevel.BLOCKING,
            HardwareCategory.MOTHERBOARD, HardwareCategory.MEMORY),
    MOTHERBOARD_CASE_FORM_FACTOR("motherboard_case_form_factor", "主板板型受机箱支持",
            RiskLevel.BLOCKING, HardwareCategory.MOTHERBOARD, HardwareCategory.CASE),
    GPU_CASE_LENGTH("gpu_case_length", "显卡长度不超过机箱限长", RiskLevel.BLOCKING,
            HardwareCategory.GPU, HardwareCategory.CASE),
    COOLER_CPU_SOCKET("cooler_cpu_socket", "散热器支持 CPU 插槽", RiskLevel.BLOCKING,
            HardwareCategory.COOLER, HardwareCategory.CPU),
    COOLER_CASE_HEIGHT("cooler_case_height", "散热器高度不超过机箱限高", RiskLevel.BLOCKING,
            HardwareCategory.COOLER, HardwareCategory.CASE),
    GPU_PSU_POWER("gpu_psu_power", "显卡供电与电源功率/接口匹配", RiskLevel.BLOCKING,
            HardwareCategory.CPU, HardwareCategory.GPU, HardwareCategory.PSU),
    STORAGE_MOTHERBOARD_M2("storage_motherboard_m2", "存储接口与主板 M.2/SATA 匹配",
            RiskLevel.BLOCKING, HardwareCategory.MOTHERBOARD, HardwareCategory.STORAGE),
    MEMORY_MODULE_COUNT("memory_module_count", "内存条数不超过主板插槽数", RiskLevel.BLOCKING,
            HardwareCategory.MOTHERBOARD, HardwareCategory.MEMORY);

    private final String ruleId;
    private final String displayName;
    private final RiskLevel riskLevel;
    private final List<HardwareCategory> requiredCategories;

    CompatibilityRule(
            String ruleId,
            String displayName,
            RiskLevel riskLevel,
            HardwareCategory... requiredCategories) {
        this.ruleId = ruleId;
        this.displayName = displayName;
        this.riskLevel = riskLevel;
        this.requiredCategories = List.of(requiredCategories);
    }

    public String ruleId() {
        return ruleId;
    }

    public String displayName() {
        return displayName;
    }

    public RiskLevel riskLevel() {
        return riskLevel;
    }

    /**
     * @return 该规则读取的硬件类别；这些类别全部已选时规则才有意义
     */
    public List<HardwareCategory> requiredCategories() {
        return requiredCategories;
    }

    /**
     * 判断规则在给定组合上是否可判定。
     *
     * <p>只有规则依赖的类别全部已选时才执行：组件根本没选不是「字段缺失」，
     * 不应产出 {@code UNKNOWN}。</p>
     *
     * @param selection 硬件组合，允许部分为空
     * @return 依赖类别全部已选时为 {@code true}
     */
    public boolean appliesTo(HardwareSelection selection) {
        return requiredCategories.stream().allMatch(category -> selection.get(category) != null);
    }
}
