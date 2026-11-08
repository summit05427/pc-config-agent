package com.example.agent.pcbuild.application;

import com.example.agent.pcbuild.application.port.BenchmarkRepository;
import com.example.agent.pcbuild.application.port.HardwareCatalogRepository;
import com.example.agent.pcbuild.domain.Benchmark;
import com.example.agent.pcbuild.domain.HardwareCategory;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 跑分查询服务。
 *
 * <p>跑分按 {@code hardware_id} 唯一；当同一硬件缺失跑分时，调用方必须按「无数据」处理，
 * 不能把缺失当作 0 分参与展示以外的判断。</p>
 */
@Service
@RequiredArgsConstructor
public class BenchmarkQueryService {

    private static final Comparator<Benchmark> STABLE_ORDER = Comparator
            .comparing(Benchmark::hardwareId);

    private final BenchmarkRepository benchmarkRepository;

    private final HardwareCatalogRepository hardwareCatalogRepository;

    /**
     * @param category 类别过滤，可为 {@code null}
     * @return 按 hardware_id 排序的跑分
     */
    public List<Benchmark> list(HardwareCategory category) {
        List<Benchmark> all = benchmarkRepository.findAll();
        if (category == null) {
            return all.stream().sorted(STABLE_ORDER).toList();
        }
        Set<String> hardwareIds = hardwareCatalogRepository.findAll().stream()
                .filter(hardware -> hardware.category() == category)
                .map(hardware -> hardware.hardwareId())
                .collect(Collectors.toUnmodifiableSet());
        return all.stream()
                .filter(benchmark -> hardwareIds.contains(benchmark.hardwareId()))
                .sorted(STABLE_ORDER)
                .toList();
    }

    /**
     * @param hardwareId 硬件标识
     * @return 跑分
     */
    public Optional<Benchmark> findByHardwareId(String hardwareId) {
        return benchmarkRepository.findByHardwareId(hardwareId);
    }
}
