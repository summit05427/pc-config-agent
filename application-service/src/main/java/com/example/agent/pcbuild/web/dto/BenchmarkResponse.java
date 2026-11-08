package com.example.agent.pcbuild.web.dto;

import com.example.agent.pcbuild.domain.Benchmark;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

/**
 * 跑分响应。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record BenchmarkResponse(
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
     * @param benchmark 领域跑分
     * @return 响应
     */
    public static BenchmarkResponse from(Benchmark benchmark) {
        return new BenchmarkResponse(
                benchmark.hardwareId(),
                benchmark.benchmarkType(),
                benchmark.score(),
                benchmark.secondaryScore(),
                benchmark.rankNo(),
                benchmark.samples(),
                benchmark.matchMethod(),
                benchmark.matchConfidence(),
                benchmark.sourceName());
    }

    /**
     * @param benchmarks 领域跑分
     * @return 列表响应
     */
    public static BenchmarkListResponse listOf(List<Benchmark> benchmarks) {
        List<BenchmarkResponse> list = benchmarks.stream().map(BenchmarkResponse::from).toList();
        return new BenchmarkListResponse(list.size(), list);
    }
}
