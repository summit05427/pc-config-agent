package com.example.agent.pcbuild.domain;

/**
 * 九条兼容性规则。
 *
 * <p>{@code ruleId} 是对外稳定标识，改名视为契约变更。规则版本由
 * {@link CompatibilityReport#RULE_VERSION} 统一声明，便于快照追溯。
 * 每条规则携带 {@link RiskLevel}，用于说明「信息缺失」是否阻断推荐。</p>
 */
public enum CompatibilityRule {

    CPU_SOCKET_MOTHERBOARD("cpu_socket_motherboard", "CPU 插槽与主板插槽一致", RiskLevel.BLOCKING),
    MOTHERBOARD_MEMORY_TYPE("motherboard_memory_type", "主板内存类型与内存条一致", RiskLevel.BLOCKING),
    MOTHERBOARD_CASE_FORM_FACTOR("motherboard_case_form_factor", "主板板型受机箱支持", RiskLevel.BLOCKING),
    GPU_CASE_LENGTH("gpu_case_length", "显卡长度不超过机箱限长", RiskLevel.BLOCKING),
    COOLER_CPU_SOCKET("cooler_cpu_socket", "散热器支持 CPU 插槽", RiskLevel.BLOCKING),
    COOLER_CASE_HEIGHT("cooler_case_height", "散热器高度不超过机箱限高", RiskLevel.BLOCKING),
    GPU_PSU_POWER("gpu_psu_power", "显卡供电与电源功率/接口匹配", RiskLevel.BLOCKING),
    STORAGE_MOTHERBOARD_M2("storage_motherboard_m2", "存储接口与主板 M.2/SATA 匹配", RiskLevel.BLOCKING),
    MEMORY_MODULE_COUNT("memory_module_count", "内存条数不超过主板插槽数", RiskLevel.BLOCKING);

    private final String ruleId;
    private final String displayName;
    private final RiskLevel riskLevel;

    CompatibilityRule(String ruleId, String displayName, RiskLevel riskLevel) {
        this.ruleId = ruleId;
        this.displayName = displayName;
        this.riskLevel = riskLevel;
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
}
