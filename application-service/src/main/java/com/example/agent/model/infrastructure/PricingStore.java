package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.ModelPricingVersion;
import java.util.Collection;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 模型定价读取入口；写入仍归管理端目录服务。
 */
@Component
@RequiredArgsConstructor
public class PricingStore {

    private final ModelPricingMapper modelPricingMapper;

    /**
     * 按 Provider 与模型键分别过滤后批量取回，可能多取到不属于同一组合的版本；
     * 调用方按 {@code provider:modelKey} 精确分组后再选择生效版本。
     */
    public List<ModelPricingVersion> findByModels(
            Collection<String> providers, Collection<String> modelKeys) {
        return modelPricingMapper.findByModels(providers, modelKeys).stream()
                .map(PricingStore::toVersion)
                .toList();
    }

    private static ModelPricingVersion toVersion(ModelPricingRow row) {
        return new ModelPricingVersion(
                row.provider(), row.modelKey(), row.inputPricePerMillion(),
                row.outputPricePerMillion(), row.currency(), row.effectiveFrom());
    }
}
