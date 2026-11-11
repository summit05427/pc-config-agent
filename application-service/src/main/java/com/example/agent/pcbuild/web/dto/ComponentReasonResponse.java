package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.ComponentRationale;
import com.example.agent.pcbuild.domain.HardwareCategory;

/**
 * 单个硬件的确定性选型理由响应。
 *
 * @param hardwareCategory  硬件类别
 * @param hardwareId        硬件标识
 * @param reason            中文理由
 * @param scoreContribution 对方案总分的原始贡献分数
 * @param priceFen          该件价格，单位人民币分
 */
public record ComponentReasonResponse(
        HardwareCategory hardwareCategory,
        String hardwareId,
        String reason,
        long scoreContribution,
        long priceFen) {

    /**
     * @param rationale 领域理由
     * @return 响应
     */
    public static ComponentReasonResponse from(ComponentRationale rationale) {
        return new ComponentReasonResponse(
                rationale.hardwareCategory(),
                rationale.hardwareId(),
                rationale.reason(),
                rationale.scoreContribution(),
                rationale.priceFen());
    }
}
