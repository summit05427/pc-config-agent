package com.example.agent.pcbuild.infrastructure;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * {@code benchmarks.json} 的读取模型。
 *
 * @param entries 跑分条目
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record BenchmarkFixture(
        @JsonProperty("entries") List<Entry> entries) {

    public BenchmarkFixture {
        entries = entries == null ? List.of() : List.copyOf(entries);
    }

    /**
     * 单条跑分。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Entry(
            @JsonProperty("hardware_id") String hardwareId,
            @JsonProperty("benchmark_type") String benchmarkType,
            @JsonProperty("score") double score,
            @JsonProperty("secondary_score") Double secondaryScore,
            @JsonProperty("rank_no") Integer rankNo,
            @JsonProperty("samples") Integer samples,
            @JsonProperty("source") Source source,
            @JsonProperty("match_method") String matchMethod,
            @JsonProperty("match_confidence") Double matchConfidence) {

        /**
         * 数据来源。
         */
        @JsonIgnoreProperties(ignoreUnknown = true)
        public record Source(@JsonProperty("name") String name) {
        }
    }
}
