package com.example.agent.pcbuild.domain;

/**
 * 单个硬件的确定性选型理由。
 *
 * <p>文本只由已有报价、跑分与规格拼出，不调用模型、不引入外部知识。
 * {@code scoreContribution} 是原始贡献分数（非百分比），百分比由理由文本给出，
 * 便于调用方复核与展示。</p>
 *
 * @param hardwareCategory  硬件类别
 * @param hardwareId        硬件标识
 * @param reason            中文理由，包含排序依据、得分贡献与价格占比
 * @param scoreContribution 对方案总分的原始贡献分数
 * @param priceFen          该件价格，单位人民币分
 */
public record ComponentRationale(
        HardwareCategory hardwareCategory,
        String hardwareId,
        String reason,
        long scoreContribution,
        long priceFen) {
}
