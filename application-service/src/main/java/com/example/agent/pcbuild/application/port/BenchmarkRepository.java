package com.example.agent.pcbuild.application.port;

import com.example.agent.pcbuild.domain.Benchmark;
import java.util.List;
import java.util.Optional;

/**
 * 跑分仓储端口。
 */
public interface BenchmarkRepository {

    /**
     * @return 全部跑分映射
     */
    List<Benchmark> findAll();

    /**
     * @param hardwareId 硬件标识
     * @return 命中跑分
     */
    Optional<Benchmark> findByHardwareId(String hardwareId);
}
