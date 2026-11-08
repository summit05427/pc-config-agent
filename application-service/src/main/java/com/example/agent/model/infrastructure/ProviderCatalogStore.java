package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.ProviderDescriptor;
import com.example.agent.model.domain.ProviderSummary;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * Provider 目录读取入口，把目录行转成 domain 描述，避免 application 依赖 Row。
 */
@Component
@RequiredArgsConstructor
public class ProviderCatalogStore {

    private final ModelCatalogMapper modelCatalogMapper;

    /**
     * 列出启用中的 Provider 摘要。
     */
    public List<ProviderSummary> listEnabledSummaries() {
        return modelCatalogMapper.findEnabledProviderSummaries().stream()
                .map(row -> new ProviderSummary(
                        row.code(), row.displayName(), row.protocol(), row.defaultBaseUrl(), row.modelCount()))
                .toList();
    }

    /**
     * 查询启用中的 Provider。
     *
     * @param providerCode Provider 代码
     * @return 描述对象；不存在或已停用时为 {@code null}
     */
    public ProviderDescriptor findEnabledProvider(String providerCode) {
        ProviderRow row = modelCatalogMapper.findEnabledProvider(providerCode);
        return row == null ? null : new ProviderDescriptor(
                row.code(), row.displayName(), row.protocol(), row.defaultBaseUrl());
    }
}
