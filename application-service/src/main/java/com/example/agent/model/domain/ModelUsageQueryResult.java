package com.example.agent.model.domain;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 本人用量查询结果：当日额度快照 + 使用明细分页。
 *
 * @param quota 当日额度快照
 * @param list  当前页使用明细
 * @param total 命中过滤条件的总条数
 * @param page       页码，从 1 开始
 * @param size       每页条数
 * @param totalTokens 累计消耗 Token 数（输入 + 输出，全时段）
 */
public record ModelUsageQueryResult(
        Quota quota,
        List<ModelUsageView> list,
        long total,
        int page,
        int size,
        long totalTokens) {

    /**
     * 当日额度快照。
     *
     * <p>当日尚无记录时不伪造已用数：{@code used=0}，{@code limit} 取当前配置值，
     * 与「首条记录写入时才快照上限」的语义一致。</p>
     *
     * @param quotaType 额度类型，固定 {@code daily_requests}
     * @param limit     当日上限
     * @param used      已用请求数
     * @param resetAt   额度重置时间（次日 00:00 UTC）
     */
    public record Quota(String quotaType, int limit, int used, OffsetDateTime resetAt) {
    }
}
