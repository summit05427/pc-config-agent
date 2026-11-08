package com.example.agent.model.application;

import com.example.agent.model.infrastructure.AdminModelUsageMapper;
import com.example.agent.model.infrastructure.AdminUsageFilter;
import com.example.agent.model.infrastructure.AdminUsageModelRow;
import com.example.agent.model.infrastructure.AdminUsageProviderRow;
import com.example.agent.model.infrastructure.AdminUsageStatusRow;
import com.example.agent.model.infrastructure.AdminUsageSummaryFilter;
import com.example.agent.model.infrastructure.AdminUsageTotalsRow;
import com.example.agent.model.web.dto.AdminModelUsageItemResponse;
import com.example.agent.model.web.dto.AdminModelUsageQuery;
import com.example.agent.model.web.dto.AdminModelUsageSummaryQuery;
import com.example.agent.model.web.dto.AdminModelUsageSummaryResponse;
import com.example.agent.shared.api.PageResult;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 管理端用量查询服务：跨用户使用明细与聚合。
 *
 * <p>鉴权由 {@code SecurityConfig} 对 {@code /api/v1/admin/**} 统一限制为 {@code ADMIN}，
 * 本层只负责查询口径。过滤、分页、排序与聚合全部下推到 SQL，调用方无法通过参数
 * 指定列名，也无法让服务端拉全量数据再截断。</p>
 *
 * <p>费用只在单一币种时给出合计：同一口径出现多币种说明定价配置不完整，
 * 此时金额与币种置空，由前端展示「多币种」，绝不把不同币种相加成虚假总额。</p>
 */
@Service
@RequiredArgsConstructor
public class AdminModelUsageService {

    /** 分组维度最多返回条数：看板只展示主要 Provider / 模型，避免响应随目录增长。 */
    static final int GROUP_LIMIT = 20;

    private static final String ORDER_ASC = "asc";
    private static final String COST_STATUS_ESTIMATED = "ESTIMATED";
    private static final String COST_STATUS_UNKNOWN = "UNKNOWN";
    private static final String COST_STATUS_BYOK_NOT_BILLED = "BYOK_NOT_BILLED";

    private final AdminModelUsageMapper adminModelUsageMapper;

    /**
     * 分页查询全部用户的使用明细。
     *
     * @param query 查询参数，空串按「不过滤」处理
     * @return 分页明细，按发生时间排序
     * @throws BusinessException 用户标识非法或日期区间非法
     */
    @Transactional(readOnly = true)
    public PageResult<AdminModelUsageItemResponse> list(AdminModelUsageQuery query) {
        validateRange(query.getFrom(), query.getTo());
        AdminUsageFilter filter = new AdminUsageFilter(
                parseUserId(query.getUserId()),
                blankToNull(query.getProvider()),
                blankToNull(query.getModelKey()),
                blankToNull(query.getCredentialSource()),
                blankToNull(query.getCostStatus()),
                blankToNull(query.getStatus()),
                fromInclusive(query.getFrom()),
                toExclusive(query.getTo()),
                ORDER_ASC.equals(query.getOrder()));
        long total = adminModelUsageMapper.count(filter);
        if (total == 0) {
            return PageResult.empty(query);
        }
        List<AdminModelUsageItemResponse> list = adminModelUsageMapper
                .findPage(filter, query.offset(), query.getSize()).stream()
                .map(AdminModelUsageItemResponse::from)
                .toList();
        return PageResult.of(list, total, query);
    }

    /**
     * 按与列表一致的 UTC 自然日口径聚合用量。
     *
     * @param query 聚合参数，不含用户与成本状态过滤
     * @return 总量、成本状态分布与主要 Provider / 模型分布
     * @throws BusinessException 日期区间非法
     */
    @Transactional(readOnly = true)
    public AdminModelUsageSummaryResponse summarize(AdminModelUsageSummaryQuery query) {
        validateRange(query.getFrom(), query.getTo());
        AdminUsageSummaryFilter filter = new AdminUsageSummaryFilter(
                blankToNull(query.getProvider()),
                blankToNull(query.getModelKey()),
                blankToNull(query.getCredentialSource()),
                fromInclusive(query.getFrom()),
                toExclusive(query.getTo()));
        AdminUsageTotalsRow totals = adminModelUsageMapper.summarizeTotals(filter);
        List<AdminUsageStatusRow> statusRows = adminModelUsageMapper.summarizeByCostStatus(filter);
        List<AdminUsageProviderRow> providerRows =
                adminModelUsageMapper.summarizeByProvider(filter, GROUP_LIMIT);
        List<AdminUsageModelRow> modelRows =
                adminModelUsageMapper.summarizeByModel(filter, GROUP_LIMIT);
        return new AdminModelUsageSummaryResponse(
                query.getFrom(),
                query.getTo(),
                toTotals(totals, statusRows),
                statusRows.stream().map(AdminModelUsageService::toCostStatusBreakdown).toList(),
                providerRows.stream().map(AdminModelUsageService::toProviderBreakdown).toList(),
                modelRows.stream().map(AdminModelUsageService::toModelBreakdown).toList());
    }

    private static AdminModelUsageSummaryResponse.Totals toTotals(
            AdminUsageTotalsRow row, List<AdminUsageStatusRow> statusRows) {
        long promptTokens = nullSafe(row.promptTokens());
        long completionTokens = nullSafe(row.completionTokens());
        boolean isSingleCurrency = isSingleCurrency(row.estimatedCurrencyCount());
        return new AdminModelUsageSummaryResponse.Totals(
                nullSafe(row.requestCount()),
                nullSafe(row.successCount()),
                nullSafe(row.failureCount()),
                promptTokens,
                completionTokens,
                promptTokens + completionTokens,
                isSingleCurrency ? row.estimatedCost() : null,
                isSingleCurrency ? row.estimatedCurrency() : null,
                countStatus(statusRows, COST_STATUS_ESTIMATED),
                countStatus(statusRows, COST_STATUS_UNKNOWN),
                countStatus(statusRows, COST_STATUS_BYOK_NOT_BILLED));
    }

    private static AdminModelUsageSummaryResponse.CostStatusBreakdown toCostStatusBreakdown(
            AdminUsageStatusRow row) {
        boolean isSingleCurrency = isSingleCurrency(row.currencyCount());
        return new AdminModelUsageSummaryResponse.CostStatusBreakdown(
                row.costStatus(),
                nullSafe(row.requestCount()),
                isSingleCurrency ? row.estimatedCost() : null,
                isSingleCurrency ? row.currency() : null);
    }

    private static AdminModelUsageSummaryResponse.ProviderBreakdown toProviderBreakdown(
            AdminUsageProviderRow row) {
        long promptTokens = nullSafe(row.promptTokens());
        long completionTokens = nullSafe(row.completionTokens());
        boolean isSingleCurrency = isSingleCurrency(row.currencyCount());
        return new AdminModelUsageSummaryResponse.ProviderBreakdown(
                row.provider(),
                nullSafe(row.requestCount()),
                promptTokens,
                completionTokens,
                promptTokens + completionTokens,
                isSingleCurrency ? row.estimatedCost() : null,
                isSingleCurrency ? row.currency() : null);
    }

    private static AdminModelUsageSummaryResponse.ModelBreakdown toModelBreakdown(
            AdminUsageModelRow row) {
        long promptTokens = nullSafe(row.promptTokens());
        long completionTokens = nullSafe(row.completionTokens());
        boolean isSingleCurrency = isSingleCurrency(row.currencyCount());
        return new AdminModelUsageSummaryResponse.ModelBreakdown(
                row.provider(),
                row.modelKey(),
                nullSafe(row.requestCount()),
                promptTokens,
                completionTokens,
                promptTokens + completionTokens,
                isSingleCurrency ? row.estimatedCost() : null,
                isSingleCurrency ? row.currency() : null);
    }

    /** 币种数为 1 才允许展示金额；0 表示没有估算，多币种表示不可求和。 */
    private static boolean isSingleCurrency(Integer currencyCount) {
        return currencyCount != null && currencyCount == 1;
    }

    private static long countStatus(List<AdminUsageStatusRow> rows, String costStatus) {
        return rows.stream()
                .filter(row -> costStatus.equals(row.costStatus()))
                .mapToLong(row -> nullSafe(row.requestCount()))
                .sum();
    }

    private static long nullSafe(Long value) {
        return value == null ? 0L : value;
    }

    /** 日期按 UTC 自然日解释，避免管理员在不同时区得到不同统计结果。 */
    private static OffsetDateTime fromInclusive(LocalDate from) {
        return from == null ? null : from.atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
    }

    private static OffsetDateTime toExclusive(LocalDate to) {
        return to == null ? null : to.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
    }

    private static void validateRange(LocalDate from, LocalDate to) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "起始日期不能晚于截止日期");
        }
    }

    /** 用户标识来自查询参数，先校验格式再交给 SQL，避免非法 UUID 变成 500。 */
    private static UUID parseUserId(String rawUserId) {
        String userId = blankToNull(rawUserId);
        if (userId == null) {
            return null;
        }
        try {
            return UUID.fromString(userId);
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID, "用户标识格式不正确");
        }
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
