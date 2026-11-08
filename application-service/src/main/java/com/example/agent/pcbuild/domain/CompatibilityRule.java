package com.example.agent.pcbuild.domain;

/**
 * 八条兼容性规则。
 *
 * <p>{@code ruleId} 是对外稳定标识，改名视为契约变更。规则版本由
 * {@link CompatibilityReport#RULE_VERSION} 统一声明，便于快照追溯。</p>
 */
public enum CompatibilityRule {

    CPU_SOCKET_MOTHERBOARD("cpu_socket_motherboard", "CPU 插槽与主板插槽一致"),
    MOTHERBOARD_MEMORY_TYPE("motherboard_memory_type", "主板内存类型与内存条一致"),
    MOTHERBOARD_CASE_FORM_FACTOR("motherboard_case_form_factor", "主板板型受机箱支持"),
    GPU_CASE_LENGTH("gpu_case_length", "显卡长度不超过机箱限长"),
    COOLER_CPU_SOCKET("cooler_cpu_socket", "散热器支持 CPU 插槽"),
    COOLER_CASE_HEIGHT("cooler_case_height", "散热器高度不超过机箱限高"),
    GPU_PSU_POWER("gpu_psu_power", "显卡供电与电源功率/接口匹配"),
    STORAGE_MOTHERBOARD_M2("storage_motherboard_m2", "存储接口与主板 M.2/SATA 匹配");

    private final String ruleId;
    private final String displayName;

    CompatibilityRule(String ruleId, String displayName) {
        this.ruleId = ruleId;
        this.displayName = displayName;
    }

    public String ruleId() {
        return ruleId;
    }

    public String displayName() {
        return displayName;
    }
}
