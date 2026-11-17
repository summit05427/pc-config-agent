package com.example.agent.model.application;

import com.example.agent.model.domain.ModelCatalogEntry;
import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.domain.ModelReference;
import com.example.agent.model.domain.ModelSnapshot;
import com.example.agent.model.domain.ProviderConnectionView;
import com.example.agent.model.domain.ProviderSummary;
import com.example.agent.model.domain.ResolvedModel;
import com.example.agent.model.infrastructure.ModelCatalogStore;
import com.example.agent.model.infrastructure.ProviderCatalogStore;
import com.example.agent.model.infrastructure.ProviderConnectionStore;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
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

    private static final String CREDENTIAL_STATUS_INVALID = "INVALID";

    /** 没有平台模型时，Auto 最多检查这么多条 BYOK 模型，避免为了找推理模型无限翻页。 */
    private static final int BYOK_AUTO_CANDIDATES = 50;

    /** 推理内容可见的能力位；Auto 优先选用，保证用户能看到思考过程。 */
    private static final String CAPABILITY_REASONING_VISIBLE = "reasoning_visible";

    /** 未配置任何可用密钥时给用户的明确指引，不暴露内部错误码语义。 */
    public static final String NO_MODEL_CREDENTIAL_MESSAGE =
            "尚未配置可用的模型密钥，请先在设置中添加 API Key";

    private final ModelCatalogStore modelCatalogStore;
    private final ProviderCatalogStore providerCatalogStore;
    private final ProviderConnectionStore connectionStore;
    private final ManagedModelAvailability managedAvailability;
    private final ModelRuntimeProperties properties;
    private final ModelRuntimeGuard runtimeGuard;
    private final ObjectMapper objectMapper;

    /**
     * 列出所有平台托管模型（v1 兼容接口，不含用户维度）。
     *
     * @return 已启用且 Provider 已启用的平台模型；纯 BYOK 部署返回空列表
     */
    @Transactional(readOnly = true)
    public List<ModelCatalogEntry> listAvailable() {
        runtimeGuard.requireEnabled();
        if (!managedAvailability.isAvailable()) {
            return List.of();
        }
        return modelCatalogStore.listEnabled().stream()
                .map(row -> new ModelCatalogEntry(
                        toResolvedModel(row), ModelCatalogEntry.SOURCE_MANAGED))
                .toList();
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
     * <p>平台托管开关打开时，平台模型对所有用户可见；BYOK 专用模型只有用户接入
     * 对应 Provider 且凭证未被撤销/拒绝后才出现。关闭平台托管后只返回 BYOK 模型。</p>
     *
     * @param query        分页参数
     * @param userPublicId 用户公开 ID
     * @return 当前页模型、凭证来源与总数
     */
    @Transactional(readOnly = true)
    public PageResult<ModelCatalogEntry> listAvailable(PageQuery query, UUID userPublicId) {
        runtimeGuard.requireEnabled();
        boolean includeManaged = managedAvailability.isAvailable();
        long total = modelCatalogStore.countVisible(userPublicId, includeManaged);
        if (query.offset() >= total) {
            return PageResult.of(List.of(), total, query);
        }
        Set<String> byokProviders = byokProviderCodes(userPublicId);
        List<ModelCatalogEntry> entries = modelCatalogStore
                .listVisiblePage(userPublicId, query.offset(), query.getSize(), includeManaged).stream()
                .map(row -> {
                    ResolvedModel model = toResolvedModel(row);
                    String source = byokProviders.contains(model.provider())
                            ? ModelCatalogEntry.SOURCE_BYOK
                            : ModelCatalogEntry.SOURCE_MANAGED;
                    return new ModelCatalogEntry(model, source);
                })
                .toList();
        return PageResult.of(entries, total, query);
    }

    /**
     * 校验并解析模型引用（不含用户维度，仅用于平台默认模型）。
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
                modelReference.provider(), modelReference.modelKey(), userPublicId,
                managedAvailability.isAvailable());
        if (row == null) {
            log.warn("请求的模型对当前用户不可用 reference={} userId={}", reference, userPublicId);
            throw new BusinessException(ModelErrorCode.MODEL_NOT_AVAILABLE);
        }
        return toResolvedModel(row);
    }

    /**
     * 解析 Auto。
     *
     * <p>平台托管可用时使用配置的默认模型；纯 BYOK 部署返回该用户第一条可用 BYOK 模型。
     * 两类都没有时明确失败，禁止在无密钥状态下继续创建任务。</p>
     *
     * @param userPublicId 用户公开 ID
     * @return 默认模型
     * @throws BusinessException 默认模型不可用或用户没有任何 BYOK 模型时 403
     */
    @Transactional(readOnly = true)
    public ResolvedModel resolveAuto(UUID userPublicId) {
        if (managedAvailability.isAvailable()) {
            return requireAvailable(properties.getDefaultModelKey());
        }
        List<ModelSnapshot> candidates = modelCatalogStore
                .listVisiblePage(userPublicId, 0, BYOK_AUTO_CANDIDATES, false);
        ModelSnapshot first = candidates.stream()
                .filter(model -> parseCapabilities(model.capabilitiesJson())
                        .contains(CAPABILITY_REASONING_VISIBLE))
                .findFirst()
                .orElse(candidates.isEmpty() ? null : candidates.getFirst());
        if (first == null) {
            throw new BusinessException(ModelErrorCode.MODEL_NOT_AVAILABLE, NO_MODEL_CREDENTIAL_MESSAGE);
        }
        return toResolvedModel(first);
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

    /**
     * 收集当前用户可用的 BYOK Provider：连接必须是 ACTIVE，且凭证不是已撤销/已失效。
     */
    private Set<String> byokProviderCodes(UUID userPublicId) {
        if (!properties.isByokEnabled()) {
            return Set.of();
        }
        return connectionStore.listActive(userPublicId).stream()
                .filter(connection -> connection.credential() != null)
                .filter(connection -> !CREDENTIAL_STATUS_INVALID.equals(
                        connection.credential().status()))
                .map(ProviderConnectionView::provider)
                .collect(Collectors.toSet());
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
