package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;

/**
 * 硬件详情响应。
 *
 * @param hardwareId           硬件标识
 * @param category             类别
 * @param brand                品牌
 * @param modelName            型号名
 * @param displayName          展示名
 * @param specifications       规格；缺失字段不输出
 * @param specSummary          单行规格摘要
 * @param dataQualityStatus    数据质量状态
 * @param lifecycleStatus      生命周期状态
 * @param recommendationStatus 推荐状态
 */
public record HardwareResponse(
        String hardwareId,
        HardwareCategory category,
        String brand,
        String modelName,
        String displayName,
        HardwareSpecifications specifications,
        String specSummary,
        String dataQualityStatus,
        String lifecycleStatus,
        String recommendationStatus) {

    /**
     * @param hardware 领域硬件
     * @return 响应
     */
    public static HardwareResponse from(Hardware hardware) {
        return new HardwareResponse(
                hardware.hardwareId(),
                hardware.category(),
                hardware.brand(),
                hardware.modelName(),
                hardware.displayName(),
                hardware.specifications(),
                hardware.specSummary(),
                hardware.dataQualityStatus(),
                hardware.lifecycleStatus(),
                hardware.recommendationStatus());
    }
}
