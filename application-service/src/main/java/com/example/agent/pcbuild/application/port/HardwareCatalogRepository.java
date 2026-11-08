package com.example.agent.pcbuild.application.port;

import com.example.agent.pcbuild.domain.Hardware;
import java.util.List;
import java.util.Optional;

/**
 * 硬件目录仓储端口。
 *
 * <p>上层只依赖该接口，不感知数据来自 classpath JSON 还是未来数据库。</p>
 */
public interface HardwareCatalogRepository {

    /**
     * @return 全部硬件，顺序稳定
     */
    List<Hardware> findAll();

    /**
     * @param hardwareId 硬件标识
     * @return 命中硬件
     */
    Optional<Hardware> findById(String hardwareId);

    /**
     * @return 目录版本，随快照落库
     */
    String catalogVersion();
}
