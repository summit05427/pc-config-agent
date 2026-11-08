package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ModelReference;
import com.example.agent.model.domain.ModelSnapshot;
import com.example.agent.model.domain.ProviderSummary;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.infrastructure.ModelCatalogStore;
import com.example.agent.model.infrastructure.ProviderCatalogStore;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/**
 * 模型目录服务：唯一的模型解析入口。
 *
 * <p>Agent 不感知 Provider 目录细节，只使用这里返回的稳定引用；目录变更（下架、改名）
 * 只影响 Java 端，因此解析规则必须集中在本服务。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ModelCatalogService {

    private final ModelCatalogStore modelCatalogStore;
    private final ProviderCatalogStore providerCatalogStore;
    private final ModelRuntimeProperties properties;
    private final ModelRuntimeGuard runtimeGuard;
    private final ObjectMapper objectMapper;

    /**
     * 列出所有可用模型。
     *
     * @return 已启用且 Provider 已启用的模型，按 Provider 与模型排序
     */
    @Transactional(readOnly = true)
    public List<ResolvedModel> listAvailable() {
        runtimeGuard.requireEnabled();
        return modelCatalogStore.listEnabled().stream().map(this::toResolvedModel).toList();
    }

    /**
     * 列出 BYOK 供应商选择器可用的 Provider。
     *
     * <p>数据源必须是 providers 目录，而不是从 models 反推：新厂商可能还没有
     * 启用模型，但从产品上仍然允许用户先接入密钥。协议由网关承担，这里只按启用状态过滤。</p>
     *
     * @return 已启用的 Provider 摘要
     */
    @Transactional(readOnly = true)
    public List<ProviderSummary> listProviders() {
        runtimeGuard.requireEnabled();
        return providerCatalogStore.listEnabledSummaries();
    }

    /**
     * 分页列出「当前用户可见」的模型。
     *
     * <p>平台托管模型对所有用户可见；BYOK 专用模型只有用户接入对应 Provider
     * 之后才出现，避免模型选择器暴露实际不可用的条目。</p>
     *
     * @param query        分页参数
     * @param userPublicId 用户公开 ID
     * @return 当前页模型与总数
     */
    @Transactional(readOnly = true)
    public PageResult<ResolvedModel> listAvailable(PageQuery query, UUID userPublicId) {
        runtimeGuard.requireEnabled();
        long total = modelCatalogStore.countVisible(userPublicId);
        if (query.offset() >= total) {
            return PageResult.of(List.of(), total, query);
        }
        List<ResolvedModel> models = modelCatalogStore
                .listVisiblePage(userPublicId, query.offset(), query.getSize()).stream()
                .map(this::toResolvedModel)
                .toList();
        return PageResult.of(models, total, query);
    }

    /**
     * 校验并解析模型引用。
     *
     * @param reference {@code <provider>:<modelKey>}
     * @return 解析后的模型
     * @throws BusinessException 引用格式非法时 400，模型不存在或已停用时 403
     */
    @Transactional(readOnly = true)
    public ResolvedModel requireAvailable(String reference) {
        runtimeGuard.requireEnabled();
        ModelReference modelReference = ModelReference.parse(reference);
        ModelSnapshot row = modelCatalogStore.findEnabledByKey(
                modelReference.provider(), modelReference.modelKey());
        if (row == null) {
            log.warn("请求的模型不可用 reference={}", reference);
            throw new BusinessException(ModelErrorCode.MODEL_NOT_AVAILABLE);
        }
        return toResolvedModel(row);
    }

    /**
     * 校验并解析「当前用户可用」的模型引用。
     *
     * @param reference   {@code <provider>:<modelKey>}
     * @param userPublicId 用户公开 ID
     * @return 解析后的模型
     * @throws BusinessException 引用格式非法时 400，模型不可见或已停用时 403
     */
    @Transactional(readOnly = true)
    public ResolvedModel requireAvailable(String reference, UUID userPublicId) {
        runtimeGuard.requireEnabled();
        ModelReference modelReference = ModelReference.parse(reference);
        ModelSnapshot row = modelCatalogStore.findVisibleByKey(
                modelReference.provider(), modelReference.modelKey(), userPublicId);
        if (row == null) {
            log.warn("请求的模型对当前用户不可用 reference={} userId={}", reference, userPublicId);
            throw new BusinessException(ModelErrorCode.MODEL_NOT_AVAILABLE);
        }
        return toResolvedModel(row);
    }

    /**
     * 解析 Auto：返回平台默认模型。
     *
     * @return 默认模型
     * @throws BusinessException 默认模型被下架时抛出 {@link ModelErrorCode#MODEL_NOT_AVAILABLE}
     */
    @Transactional(readOnly = true)
    public ResolvedModel resolveAuto() {
        return requireAvailable(properties.getDefaultModelKey());
    }

    /**
     * 读取模型引用对应的能力位；模型已下架或停用时返回空列表。
     *
     * <p>用于补齐既有运行时任务（幂等重放、任务读取）的能力位：任务本身仍在 TTL 内有效，
     * 不能因为目录随后下架就拒绝读取，因此这里不做可用性校验，也不抛业务异常。</p>
     *
     * @param reference {@code <provider>:<modelKey>}
     * @return 能力位列表，模型不可用时为空列表
     * @throws BusinessException 引用格式非法时 400
     */
    @Transactional(readOnly = true)
    public List<String> findCapabilities(String reference) {
        ModelReference modelReference = ModelReference.parse(reference);
        ModelSnapshot row = modelCatalogStore.findEnabledByKey(
                modelReference.provider(), modelReference.modelKey());
        return row == null ? List.of() : parseCapabilities(row.capabilitiesJson());
    }

    private ResolvedModel toResolvedModel(ModelSnapshot row) {
        return new ResolvedModel(
                row.providerCode(),
                row.modelKey(),
                row.displayName(),
                parseCapabilities(row.capabilitiesJson()),
                row.contextWindow());
    }

    /**
     * 能力元数据由数据库 JSONB 约束保证是数组；解析失败说明种子或迁移数据有缺陷，
     * 属于需要人工修复的问题，因此按运行时异常暴露，而不是静默返回空列表。
     */
    private List<String> parseCapabilities(String capabilitiesJson) {
        if (capabilitiesJson == null || capabilitiesJson.isBlank()) {
            return List.of();
        }
        try {
            return List.of(objectMapper.readValue(capabilitiesJson, String[].class));
        } catch (Exception ex) {
            throw new IllegalStateException("模型能力元数据不是合法 JSON 数组", ex);
        }
    }
}
