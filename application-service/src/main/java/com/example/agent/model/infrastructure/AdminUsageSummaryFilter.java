package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;

/**
 * 管理端用量聚合查询条件。
 *
 * @param provider        Provider 代码，可为空
 * @param modelKey        模型键，可为空
 * @param credentialSource 凭证来源，可为空
 * @param fromInclusive   起始时间（含），可为空
 * @param toExclusive     截止时间（不含），可为空
 */
public record AdminUsageSummaryFilter(
        String provider,
        String modelKey,
        String credentialSource,
        OffsetDateTime fromInclusive,
        OffsetDateTime toExclusive) {
}
