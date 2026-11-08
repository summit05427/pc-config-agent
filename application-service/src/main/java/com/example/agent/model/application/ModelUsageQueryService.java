package com.example.agent.model.application;

import com.example.agent.model.domain.ModelUsageQueryResult;
import com.example.agent.model.domain.ModelUsageView;
import com.example.agent.model.domain.QuotaSnapshot;
import com.example.agent.model.infrastructure.QuotaStore;
import com.example.agent.model.infrastructure.UsageStore;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import java.time.Clock;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 本人模型用量查询。
 *
 * <p>用户归属只来自令牌主体，且下推到 SQL；调用方无法通过参数查询他人台账。
 * 额度与明细在同一个只读事务内读取，减少两次查询之间的漂移；默认隔离级别仍是
 * READ COMMITTED，因此不承诺严格同一快照。</p>
 */
@Service
@RequiredArgsConstructor
public class ModelUsageQueryService {

    /** 与 {@code docs/api-contract.md} §4 的 Java 分页约定保持一致。 */
    static final int MAX_PAGE_SIZE = 100;

    private static final String QUOTA_TYPE_DAILY_REQUESTS = "daily_requests";

    private final UsageStore usageStore;
    private final QuotaStore quotaStore;
    private final ModelRuntimeGuard runtimeGuard;
    private final ModelRuntimeProperties properties;
    private final Clock modelRuntimeUtcClock;

    /**
     * 查询本人当日额度与使用明细。
     *
     * @param userPublicId 用户公开 ID，取自令牌 {@code sub}
     * @param from         起始日期（含），可为 {@code null}
     * @param to           截止日期（含），可为 {@code null}
     * @param page         页码，从 1 开始
     * @param size         每页条数，1..100
     * @return 额度快照与明细分页
     * @throws BusinessException 运行时未启用，或分页、时间范围非法
     */
    @Transactional(readOnly = true)
    public ModelUsageQueryResult query(
            UUID userPublicId, LocalDate from, LocalDate to, int page, int size) {
        runtimeGuard.requireEnabled();
        validatePagination(page, size);
        validateRange(from, to);
        OffsetDateTime fromInclusive = from == null
                ? null : from.atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
        OffsetDateTime toExclusive = to == null
                ? null : to.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
        long total = usageStore.countByUser(userPublicId, fromInclusive, toExclusive);
        List<ModelUsageView> rows = usageStore.findPage(
                userPublicId, fromInclusive, toExclusive, (long) (page - 1) * size, size);
        long totalTokens = usageStore.sumTokensByUser(userPublicId);
        return new ModelUsageQueryResult(
                quotaSnapshot(userPublicId), rows, total, page, size, totalTokens);
    }

    private ModelUsageQueryResult.Quota quotaSnapshot(UUID userPublicId) {
        LocalDate today = LocalDate.now(modelRuntimeUtcClock);
        QuotaSnapshot row = quotaStore.find(userPublicId, today);
        int used = row == null ? 0 : row.usedCount();
        int limit = row == null ? properties.getQuota().getDailyRequests() : row.limitCount();
        return new ModelUsageQueryResult.Quota(
                QUOTA_TYPE_DAILY_REQUESTS, limit, used, resetAt(today));
    }

    private OffsetDateTime resetAt(LocalDate quotaDate) {
        return quotaDate.plusDays(1).atStartOfDay(ZoneOffset.UTC).toOffsetDateTime();
    }

    private static void validatePagination(int page, int size) {
        if (page < 1 || size < 1 || size > MAX_PAGE_SIZE) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID);
        }
    }

    private static void validateRange(LocalDate from, LocalDate to) {
        if (from != null && to != null && from.isAfter(to)) {
            throw new BusinessException(CommonErrorCode.PARAM_INVALID);
        }
    }
}
