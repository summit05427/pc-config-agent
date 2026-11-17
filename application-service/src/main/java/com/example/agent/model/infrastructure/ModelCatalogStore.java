package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.ModelSnapshot;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 模型目录读取入口，application 只接触 {@link ModelSnapshot}。
 */
@Component
@RequiredArgsConstructor
public class ModelCatalogStore {

    private final ModelCatalogMapper modelCatalogMapper;

    public List<ModelSnapshot> listEnabled() {
        return modelCatalogMapper.findEnabled().stream()
                .map(ModelCatalogStore::toSnapshot)
                .toList();
    }

    public long countVisible(UUID userPublicId, boolean includeManaged) {
        return modelCatalogMapper.countVisible(userPublicId, includeManaged);
    }

    public List<ModelSnapshot> listVisiblePage(
            UUID userPublicId, long offset, int limit, boolean includeManaged) {
        return modelCatalogMapper.findVisiblePage(userPublicId, offset, limit, includeManaged).stream()
                .map(ModelCatalogStore::toSnapshot)
                .toList();
    }

    public ModelSnapshot findEnabledByKey(String providerCode, String modelKey) {
        return toSnapshot(modelCatalogMapper.findEnabledByKey(providerCode, modelKey));
    }

    public ModelSnapshot findVisibleByKey(
            String providerCode, String modelKey, UUID userPublicId, boolean includeManaged) {
        return toSnapshot(modelCatalogMapper.findVisibleByKey(
                providerCode, modelKey, userPublicId, includeManaged));
    }

    private static ModelSnapshot toSnapshot(ModelRow row) {
        if (row == null) {
            return null;
        }
        return new ModelSnapshot(
                row.providerCode(), row.modelKey(), row.displayName(),
                row.capabilitiesJson(), row.contextWindow());
    }
}
