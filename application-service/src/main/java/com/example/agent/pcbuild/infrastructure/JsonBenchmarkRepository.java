package com.example.agent.pcbuild.infrastructure;

import com.example.agent.pcbuild.application.port.BenchmarkRepository;
import com.example.agent.pcbuild.domain.Benchmark;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * 基于 classpath {@code pc-config/benchmarks.json} 的跑分适配器。
 */
@Repository
public class JsonBenchmarkRepository implements BenchmarkRepository {

    private static final String RESOURCE_PATH = "pc-config/benchmarks.json";

    private final List<Benchmark> benchmarks;

    private final Map<String, Benchmark> byHardwareId;

    /**
     * @param objectMapper Spring 容器提供的 Jackson 映射器
     */
    public JsonBenchmarkRepository(ObjectMapper objectMapper) {
        BenchmarkFixture fixture = JsonFixtureLoader.load(objectMapper, RESOURCE_PATH, BenchmarkFixture.class);
        Map<String, Benchmark> index = new LinkedHashMap<>();
        for (BenchmarkFixture.Entry entry : fixture.entries()) {
            index.put(entry.hardwareId(), new Benchmark(
                    entry.hardwareId(),
                    entry.benchmarkType(),
                    entry.score(),
                    entry.secondaryScore(),
                    entry.rankNo(),
                    entry.samples(),
                    entry.matchMethod(),
                    entry.matchConfidence(),
                    entry.source() == null ? null : entry.source().name()));
        }
        this.byHardwareId = Map.copyOf(index);
        this.benchmarks = List.copyOf(index.values());
    }

    @Override
    public List<Benchmark> findAll() {
        return benchmarks;
    }

    @Override
    public Optional<Benchmark> findByHardwareId(String hardwareId) {
        return Optional.ofNullable(byHardwareId.get(hardwareId));
    }
}
