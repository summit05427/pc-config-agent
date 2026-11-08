package com.example.agent.pcbuild.infrastructure;

import com.example.agent.pcbuild.application.port.HardwareCatalogRepository;
import com.example.agent.pcbuild.domain.Hardware;
import com.example.agent.pcbuild.domain.HardwareCategory;
import com.example.agent.pcbuild.domain.HardwareSpecifications;
import com.example.agent.pcbuild.domain.PcBuildErrorCode;
import com.example.agent.shared.error.BusinessException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * 基于 classpath {@code pc-config/catalog.json} 的硬件目录适配器。
 *
 * <p>启动时加载一次并缓存不可变列表；目录版本会随求解快照落库，便于追溯。</p>
 */
@Repository
public class JsonHardwareCatalogRepository implements HardwareCatalogRepository {

    private static final String RESOURCE_PATH = "pc-config/catalog.json";

    /** 未知类别硬件的丢弃计数只在构造期使用，因此不引入日志框架。 */
    private final List<Hardware> hardware;

    private final Map<String, Hardware> byId;

    private final String catalogVersion;

    /**
     * @param objectMapper Spring 容器提供的 Jackson 映射器
     */
    public JsonHardwareCatalogRepository(ObjectMapper objectMapper) {
        CatalogFixture fixture = JsonFixtureLoader.load(objectMapper, RESOURCE_PATH, CatalogFixture.class);
        this.catalogVersion = fixture.catalogVersion();
        Map<String, Hardware> index = new LinkedHashMap<>();
        for (CatalogFixture.Entry entry : fixture.hardware()) {
            Hardware hardwareEntry = toDomain(entry);
            index.put(hardwareEntry.hardwareId(), hardwareEntry);
        }
        this.byId = Map.copyOf(index);
        this.hardware = List.copyOf(index.values());
    }

    @Override
    public List<Hardware> findAll() {
        return hardware;
    }

    @Override
    public Optional<Hardware> findById(String hardwareId) {
        return Optional.ofNullable(byId.get(hardwareId));
    }

    @Override
    public String catalogVersion() {
        return catalogVersion;
    }

    private Hardware toDomain(CatalogFixture.Entry entry) {
        HardwareCategory category = HardwareCategory.parse(entry.category());
        if (category == null) {
            throw new BusinessException(PcBuildErrorCode.CATALOG_UNAVAILABLE,
                    "未知硬件类别: " + entry.category());
        }
        HardwareSpecifications specifications = entry.specifications();
        if (specifications == null) {
            throw new BusinessException(PcBuildErrorCode.CATALOG_UNAVAILABLE,
                    "硬件缺少规格: " + entry.hardwareId());
        }
        return new Hardware(
                entry.hardwareId(),
                category,
                entry.brand(),
                entry.modelName(),
                entry.displayName(),
                specifications,
                entry.dataQualityStatus(),
                entry.lifecycleStatus(),
                entry.recommendationStatus());
    }
}
