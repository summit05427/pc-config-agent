package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.application.HardwareCandidate;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import java.util.List;

/**
 * 候选硬件响应。
 *
 * <p>字段是 {@link HardwareResponse} 的超集：新增 {@code priceFen} 与 {@code missingFields}
 * 供调用方直接决策，既有的十个字段保持不变，旧调用方不受影响。</p>
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
 * @param priceFen             最低可用报价，单位分；没有可用报价时为 {@code null}，
 *                             不使用目录参考价兜底
 * @param missingFields        兼容性关键字段的缺失项，字段名与规格键一致
 */
public record HardwareCandidateResponse(
        String hardwareId,
        HardwareCategory category,
        String brand,
        String modelName,
        String displayName,
        HardwareSpecifications specifications,
        String specSummary,
        String dataQualityStatus,
        String lifecycleStatus,
        String recommendationStatus,
        Long priceFen,
        List<String> missingFields) {

    /**
     * @param candidate 候选硬件
     * @return 响应
     */
    public static HardwareCandidateResponse from(HardwareCandidate candidate) {
        Hardware hardware = candidate.hardware();
        return new HardwareCandidateResponse(
                hardware.hardwareId(),
                hardware.category(),
                hardware.brand(),
                hardware.modelName(),
                hardware.displayName(),
                hardware.specifications(),
                hardware.specSummary(),
                hardware.dataQualityStatus(),
                hardware.lifecycleStatus(),
                hardware.recommendationStatus(),
                candidate.priceFen(),
                candidate.missingFields());
    }
}
