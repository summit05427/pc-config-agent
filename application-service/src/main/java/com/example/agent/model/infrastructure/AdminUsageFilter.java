package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 管理端使用明细查询条件。
 *
 * <p>条件集中在不可变记录里，Mapper 只接收一个对象，避免十余个 {@code @Param}
 * 在 XML 与接口签名之间漂移。</p>
 *
 * @param userId          用户公开 ID，可为空
 * @param provider        Provider 代码，可为空
 * @param modelKey        模型键，可为空
 * @param credentialSource 凭证来源，可为空
 * @param costStatus      成本状态，可为空
 * @param status          调用结果，可为空
 * @param fromInclusive   起始时间（含），可为空
 * @param toExclusive     截止时间（不含），可为空
 * @param ascending       是否按发生时间升序
 */
public record AdminUsageFilter(
        UUID userId,
        String provider,
        String modelKey,
        String credentialSource,
        String costStatus,
        String status,
        OffsetDateTime fromInclusive,
        OffsetDateTime toExclusive,
        boolean ascending) {
}
