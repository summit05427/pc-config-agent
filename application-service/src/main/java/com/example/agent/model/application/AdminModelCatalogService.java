package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.model.infrastructure.AdminModelCatalogMapper;
import com.example.agent.model.infrastructure.AdminModelRow;
import com.example.agent.model.infrastructure.AdminPricingRow;
import com.example.agent.model.infrastructure.AdminProviderRow;
import com.example.agent.model.web.dto.AdminModelListQuery;
import com.example.agent.model.web.dto.AdminModelPricingCreateRequest;
import com.example.agent.model.web.dto.AdminModelPricingResponse;
import com.example.agent.model.web.dto.AdminModelSummaryResponse;
import com.example.agent.model.web.dto.AdminProviderSummaryResponse;
import com.example.agent.shared.api.PageQuery;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/**
 * 管理端模型目录与定价维护服务。
 *
 * <p>鉴权由 {@code SecurityConfig} 对 {@code /api/v1/admin/**} 统一完成，本层只负责目录规则：
 * 目录条目可停用不可删除（历史台账仍引用模型标识）、定价按生效时间版本化、
 * 同一 {@code (provider, modelKey, effectiveFrom)} 不允许重复。</p>
 *
 * <p>定价写入只追加版本，不修改既有记录，保证历史用量成本不被后续调价重算。</p>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AdminModelCatalogService {

    private static final String DEFAULT_CURRENCY = "USD";
    private static final String KEYWORD_WILDCARD = "%";
    private static final Pattern PROVIDER_CODE_PATTERN = Pattern.compile("^[a-z0-9][a-z0-9-]{0,31}$");
    private static final Pattern MODEL_KEY_PATTERN = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$");

    private final AdminModelCatalogMapper adminModelCatalogMapper;
    private final ObjectMapper objectMapper;

    /**
     * 分页查询模型目录（含停用条目），并为整页模型批量补齐最新定价。
     *
     * @param query 查询参数
     * @return 分页结果
     */
    @Transactional(readOnly = true)
    public PageResult<AdminModelSummaryResponse> listModels(AdminModelListQuery query) {
        String keyword = toKeywordPattern(query.getKeyword());
        String provider = blankToNull(query.getProvider());
        Boolean enabled = parseEnabled(query.getEnabled());
        long total = adminModelCatalogMapper.count(keyword, provider, enabled);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminModelRow> rows = adminModelCatalogMapper.findPage(
                keyword, provider, enabled, query.offset(), query.getSize());
        Map<String, AdminPricingRow> latestPricing = loadLatestPricing(rows);
        List<AdminModelSummaryResponse> models = rows.stream()
                .map(row -> toSummary(row, latestPricing.get(pricingKey(row.providerCode(), row.modelKey()))))
                .toList();
        return PageResult.of(models, total, query);
    }

    /**
     * 启用或停用模型；状态未变化时保持幂等，不写库。
     *
     * @param provider  Provider 代码
     * @param modelKey  模型键
     * @param enabled   目标状态
     * @param adminName 当前管理员登录名，仅用于变更留痕日志
     * @return 更新后的目录条目
     * @throws BusinessException 标识非法 400、模型不存在 404
     */
    @Transactional
    public AdminModelSummaryResponse updateModelStatus(
            String provider, String modelKey, boolean enabled, String adminName) {
        validateProviderCode(provider);
        validateModelKey(modelKey);
        AdminModelRow row = requireModel(provider, modelKey);
        if (Boolean.TRUE.equals(row.enabled()) != enabled) {
            adminModelCatalogMapper.updateEnabled(provider, modelKey, enabled);
            log.info("管理员变更模型状态 provider={} modelKey={} enabled={} admin={}",
                    provider, modelKey, enabled, adminName);
            row = requireModel(provider, modelKey);
        }
        return toSummary(row, loadLatestPricing(List.of(row)).get(pricingKey(provider, modelKey)));
    }

    /**
     * 分页查询某模型的定价版本，按生效时间倒序。
     *
     * @param provider Provider 代码
     * @param modelKey 模型键
     * @param query    分页参数
     * @return 分页结果
     * @throws BusinessException 标识非法 400、模型不存在 404
     */
    @Transactional(readOnly = true)
    public PageResult<AdminModelPricingResponse> listPricing(String provider, String modelKey, PageQuery query) {
        validateProviderCode(provider);
        validateModelKey(modelKey);
        requireModel(provider, modelKey);
        long total = adminModelCatalogMapper.countPricing(provider, modelKey);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminModelPricingResponse> versions = adminModelCatalogMapper
                .findPricingPage(provider, modelKey, query.offset(), query.getSize()).stream()
                .map(AdminModelCatalogService::toPricing)
                .toList();
        return PageResult.of(versions, total, query);
    }

    /**
     * 追加一条定价版本；只新增不修改，历史成本不受影响。
     *
     * @param provider  Provider 代码
     * @param modelKey  模型键
     * @param request   定价内容
     * @param adminName 当前管理员登录名，仅用于变更留痕日志
     * @return 新增后的定价版本
     * @throws BusinessException 标识非法 400、模型不存在 404、
     *                           同一生效时间已有版本 409
     */
    @Transactional
    public AdminModelPricingResponse createPricing(
            String provider, String modelKey, AdminModelPricingCreateRequest request, String adminName) {
        validateProviderCode(provider);
        validateModelKey(modelKey);
        requireModel(provider, modelKey);
        String currency = normalizeCurrency(request.currency());
        OffsetDateTime effectiveFrom = OffsetDateTime.ofInstant(request.effectiveFrom(), ZoneOffset.UTC);
        if (adminModelCatalogMapper.findPricingAt(provider, modelKey, effectiveFrom) != null) {
            throw new BusinessException(ModelErrorCode.PRICING_VERSION_EXISTS);
        }
        try {
            adminModelCatalogMapper.insertPricing(provider, modelKey, currency,
                    request.inputPricePerMillion(), request.outputPricePerMillion(), effectiveFrom);
        } catch (DuplicateKeyException exception) {
            // 并发插入同一生效时间：唯一约束是最终防线，转换为可读的 409
            throw new BusinessException(ModelErrorCode.PRICING_VERSION_EXISTS);
        }
        AdminPricingRow created = adminModelCatalogMapper.findPricingAt(provider, modelKey, effectiveFrom);
        if (created == null) {
            throw new IllegalStateException("定价写入后回读失败 provider=" + provider + " modelKey=" + modelKey);
        }
        log.info("管理员新增模型定价 provider={} modelKey={} currency={} effectiveFrom={} admin={}",
                provider, modelKey, currency, effectiveFrom, adminName);
        return toPricing(created);
    }

    /**
     * 列出全部 Provider（含停用）及模型数量。
     *
     * <p>Provider 是受控的小基数目录，返回完整列表供管理端筛选与启停，不做分页。</p>
     *
     * @return Provider 摘要列表，按代码排序
     */
    @Transactional(readOnly = true)
    public List<AdminProviderSummaryResponse> listProviders() {
        return adminModelCatalogMapper.findProviders().stream()
                .map(AdminModelCatalogService::toProviderSummary)
                .toList();
    }

    /**
     * 启用或停用 Provider；停用后其下模型即使启用也不可用。
     *
     * @param code      Provider 代码
     * @param enabled   目标状态
     * @param adminName 当前管理员登录名，仅用于变更留痕日志
     * @return 更新后的 Provider 摘要
     * @throws BusinessException 代码非法 400、Provider 不存在 404
     */
    @Transactional
    public AdminProviderSummaryResponse updateProviderStatus(String code, boolean enabled, String adminName) {
        validateProviderCode(code);
        AdminProviderRow row = requireProvider(code);
        if (Boolean.TRUE.equals(row.enabled()) != enabled) {
            adminModelCatalogMapper.updateProviderEnabled(code, enabled);
            log.info("管理员变更 Provider 状态 code={} enabled={} admin={}", code, enabled, adminName);
            row = requireProvider(code);
        }
        return toProviderSummary(row);
    }

    private AdminModelRow requireModel(String provider, String modelKey) {
        AdminModelRow row = adminModelCatalogMapper.findByKey(provider, modelKey);
        if (row == null) {
            throw new BusinessException(CommonErrorCode.RESOURCE_NOT_FOUND, "目标模型不存在");
        }
        return row;
    }

    private AdminProviderRow requireProvider(String code) {
        AdminProviderRow row = adminModelCatalogMapper.findProvider(code);
        if (row == null) {
            throw new BusinessException(CommonErrorCode.RESOURCE_NOT_FOUND, "目标 Provider 不存在");
        }
        return row;
    }

    /** 整页模型一次取回最新定价，避免逐模型查询。 */
    private Map<String, AdminPricingRow> loadLatestPricing(List<AdminModelRow> rows) {
        if (rows.isEmpty()) {
            return Map.of();
        }
        List<String> providers = rows.stream().map(AdminModelRow::providerCode).distinct().toList();
        List<String> modelKeys = rows.stream().map(AdminModelRow::modelKey).distinct().toList();
        return adminModelCatalogMapper.findLatestPricingByModels(providers, modelKeys).stream()
                .collect(Collectors.toMap(
                        row -> pricingKey(row.provider(), row.modelKey()),
                        Function.identity(),
                        (existing, ignored) -> existing));
    }

    private AdminModelSummaryResponse toSummary(AdminModelRow row, AdminPricingRow latestPricing) {
        return new AdminModelSummaryResponse(
                row.providerCode(),
                row.modelKey(),
                row.displayName(),
                row.contextWindow(),
                parseCapabilities(row.capabilitiesJson(), row.providerCode(), row.modelKey()),
                row.capabilitySource(),
                row.verifiedAt() == null ? null : row.verifiedAt().toInstant(),
                Boolean.TRUE.equals(row.enabled()),
                Boolean.TRUE.equals(row.providerEnabled()),
                latestPricing == null ? null : toPricing(latestPricing));
    }

    private static AdminProviderSummaryResponse toProviderSummary(AdminProviderRow row) {
        return new AdminProviderSummaryResponse(
                row.code(),
                row.displayName(),
                row.protocol(),
                row.defaultBaseUrl(),
                Boolean.TRUE.equals(row.enabled()),
                row.modelCount() == null ? 0L : row.modelCount(),
                row.enabledModelCount() == null ? 0L : row.enabledModelCount());
    }

    private static AdminModelPricingResponse toPricing(AdminPricingRow row) {
        return new AdminModelPricingResponse(
                row.id(),
                row.currency() == null ? DEFAULT_CURRENCY : row.currency().trim(),
                row.inputPricePerMillion(),
                row.outputPricePerMillion(),
                row.effectiveFrom().toInstant(),
                row.createdAt().toInstant());
    }

    /**
     * 能力元数据异常时降级为空列表并记录告警：管理端页面不应因单条脏数据整体不可用，
     * 但缺陷仍要可观测，避免静默吞掉。
     */
    private List<String> parseCapabilities(String capabilitiesJson, String provider, String modelKey) {
        if (capabilitiesJson == null || capabilitiesJson.isBlank()) {
            return List.of();
        }
        try {
            return List.of(objectMapper.readValue(capabilitiesJson, String[].class));
        } catch (Exception exception) {
            log.warn("模型能力元数据无法解析 provider={} modelKey={}", provider, modelKey, exception);
            return List.of();
        }
    }

    /** 组合键用于 Map 查找；`#` 不在模型标识白名单内，不会与实际键冲突。 */
    private static String pricingKey(String provider, String modelKey) {
        return provider + "#" + modelKey;
    }

    private static String toKeywordPattern(String keyword) {
        return keyword == null || keyword.isBlank()
                ? null
                : KEYWORD_WILDCARD + keyword.trim() + KEYWORD_WILDCARD;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    /** 空白表示不过滤；取值白名单由请求 DTO 的 {@code @Pattern} 保证。 */
    private static Boolean parseEnabled(String value) {
        return value == null || value.isBlank() ? null : Boolean.valueOf(value);
    }

    private static String normalizeCurrency(String value) {
        return value == null ? DEFAULT_CURRENCY : value.toUpperCase(Locale.ROOT);
    }

    private static void validateProviderCode(String provider) {
        if (provider == null || !PROVIDER_CODE_PATTERN.matcher(provider).matches()) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "Provider 代码格式不正确");
        }
    }

    private static void validateModelKey(String modelKey) {
        if (modelKey == null || !MODEL_KEY_PATTERN.matcher(modelKey).matches()) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "模型标识格式不正确");
        }
    }
}
