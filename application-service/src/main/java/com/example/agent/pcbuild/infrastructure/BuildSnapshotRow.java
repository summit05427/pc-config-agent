package com.example.agent.pcbuild.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 方案快照数据库行。
 *
 * <p>JSON 字段以字符串承载，由 SQL 侧 {@code CAST(... AS jsonb)} 写入。
 * 字段顺序必须与 {@code BuildSnapshotMapper.xml} 的构造器映射一致。</p>
 */
public record BuildSnapshotRow(
        UUID buildId,
        UUID userId,
        UUID parentBuildId,
        String requirementsSnapshot,
        String components,
        Long totalPriceFen,
        Long budgetMaxFen,
        String compatibilityReport,
        String benchmarkSnapshot,
        String offerSnapshot,
        String solverVersion,
        String compatibilityRuleVersion,
        String catalogVersion,
        OffsetDateTime createdAt) {
}
