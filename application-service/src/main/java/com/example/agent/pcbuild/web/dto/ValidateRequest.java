package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import java.util.EnumMap;
import java.util.Map;

/**
 * 八类硬件标识请求：兼容性校验与指定组合生成共用。
 *
 * <p>八个类别的 {@code hardware_id} 都必须提供；缺失时返回 400 {@code 40303}，
 * 不会用空位代替。</p>
 */
public record ValidateRequest(
        @NotBlank String cpu,
        @NotBlank String motherboard,
        @NotBlank String memory,
        @NotBlank String gpu,
        @NotBlank String psu,
        @NotBlank @JsonProperty("case") String caseUnit,
        @NotBlank String cooler,
        @NotBlank String storage) {

    /**
     * 转换为类别到硬件标识的映射。
     *
     * @return 八类硬件标识
     * @throws BusinessException 有类别缺失时 400 {@code 40303}
     */
    public Map<HardwareCategory, String> toHardwareIds() {
        Map<HardwareCategory, String> ids = new EnumMap<>(HardwareCategory.class);
        put(ids, HardwareCategory.CPU, cpu);
        put(ids, HardwareCategory.MOTHERBOARD, motherboard);
        put(ids, HardwareCategory.MEMORY, memory);
        put(ids, HardwareCategory.GPU, gpu);
        put(ids, HardwareCategory.PSU, psu);
        put(ids, HardwareCategory.CASE, caseUnit);
        put(ids, HardwareCategory.COOLER, cooler);
        put(ids, HardwareCategory.STORAGE, storage);
        return ids;
    }

    private void put(Map<HardwareCategory, String> ids, HardwareCategory category, String hardwareId) {
        if (hardwareId == null || hardwareId.isBlank()) {
            throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE,
                    "缺少类别: " + category.name());
        }
        ids.put(category, hardwareId.trim());
    }
}
