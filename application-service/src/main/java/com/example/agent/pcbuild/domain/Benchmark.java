package com.example.agent.pcbuild.domain;

/**
 * PassMark 跑分映射。
 *
 * <p>跑分只用于场景评分与展示，不参与兼容性判断。分数允许为小数（PassMark 原始值），
 * 但金额一律使用 {@code long} 分，两者不得混用。</p>
 *
 * @param hardwareId     对应硬件标识
 * @param benchmarkType  跑分类型，如 {@code CPUMARK}、{@code G3D_MARK}
 * @param score          主分数
 * @param secondaryScore 次分数，可为 {@code null}
 * @param rankNo         排名，可为 {@code null}
 * @param samples        样本数，可为 {@code null}
 * @param matchMethod    匹配方式
 * @param matchConfidence 匹配置信度
 * @param sourceName     数据来源名称
 */
public record Benchmark(
        String hardwareId,
        String benchmarkType,
        double score,
        Double secondaryScore,
        Integer rankNo,
        Integer samples,
        String matchMethod,
        Double matchConfidence,
        String sourceName) {

    /**
     * 把分数转为整数，供只使用整数运算的评分逻辑调用。
     *
     * @return 四舍五入后的分数
     */
    public long scoreAsLong() {
        return Math.round(score);
    }
}
