package com.example.agent.model.web.dto;

import com.example.agent.model.domain.ModelUsageQueryResult;
import java.time.OffsetDateTime;
import java.util.List;

/**
 * 本人用量查询响应。
 *
 * @param quota 当日额度快照
 * @param list  当前页使用明细
 * @param total 总条数
 * @param page  页码
 * @param size  每页条数
 * @param totalTokens 累计消耗 Token 数（输入 + 输出）
 */
public record ModelUsageResponse(
        QuotaResponse quota,
        List<ModelUsageItemResponse> list,
        long total,
        int page,
        int size,
        long totalTokens) {

    /**
     * @param result 查询结果
     * @return 对外响应对象
     */
    public static ModelUsageResponse from(ModelUsageQueryResult result) {
        return new ModelUsageResponse(
                QuotaResponse.from(result.quota()),
                result.list().stream().map(ModelUsageItemResponse::from).toList(),
                result.total(), result.page(), result.size(), result.totalTokens());
    }

    /**
     * 当日额度快照响应。
     *
     * @param quotaType 额度类型
     * @param limit     当日上限
     * @param used      已用请求数
     * @param resetAt   重置时间
     */
    public record QuotaResponse(String quotaType, int limit, int used, OffsetDateTime resetAt) {

        /**
         * @param quota 额度快照
         * @return 对外响应对象
         */
        public static QuotaResponse from(ModelUsageQueryResult.Quota quota) {
            return new QuotaResponse(quota.quotaType(), quota.limit(), quota.used(), quota.resetAt());
        }
    }
}
