package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import jakarta.validation.constraints.NotNull;
import java.util.EnumMap;
import java.util.Map;

/**
 * 部分兼容性校验请求。
 *
 * <p>{@code components} 允许任意子集，但必须非空；键必须是八类之一（大小写不敏感），
 * 值必须非空。未知键与空值都按 {@code 400 40303} 拒绝——静默忽略会让调用方
 * 误以为该组件参与了校验。</p>
 *
 * @param components 类别到硬件标识的映射，键为 {@code cpu} / {@code motherboard} 等
 */
public record PartialValidateRequest(@NotNull Map<String, String> components) {

    /**
     * 转换为类别到硬件标识的映射，按 {@link HardwareCategory#REQUIRED_CATEGORIES} 顺序解析。
     *
     * @return 已选类别与硬件标识
     * @throws BusinessException 组件为空、键未知或值空白时 400 {@code 40303}
     */
    public Map<HardwareCategory, String> toHardwareIds() {
        if (components == null || components.isEmpty()) {
            throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE, "至少需要一个硬件组件");
        }
        Map<HardwareCategory, String> ids = new EnumMap<>(HardwareCategory.class);
        for (String rawKey : components.keySet()) {
            HardwareCategory category = HardwareCategory.parse(rawKey);
            if (category == null) {
                throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE,
                        "未知组件类别: " + rawKey);
            }
            String hardwareId = components.get(rawKey);
            if (hardwareId == null || hardwareId.isBlank()) {
                throw new BusinessException(PcBuildErrorCode.BUILD_INCOMPLETE,
                        "组件 " + rawKey + " 缺少硬件标识");
            }
            ids.put(category, hardwareId.trim());
        }
        return ids;
    }
}
