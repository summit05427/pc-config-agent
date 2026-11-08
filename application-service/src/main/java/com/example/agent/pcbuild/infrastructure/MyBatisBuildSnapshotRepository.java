package com.example.agent.pcbuild.infrastructure;

import com.example.agent.pcbuild.application.port.BuildSnapshotRepository;
import com.example.agent.pcbuild.domain.BuildSnapshot;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Repository;

/**
 * MyBatis 方案快照适配器。
 *
 * <p>只做模型转换；归属校验由 SQL 的 {@code user_id} 条件保证，
 * 领域层拿不到其他用户的快照。</p>
 */
@Repository
@RequiredArgsConstructor
public class MyBatisBuildSnapshotRepository implements BuildSnapshotRepository {

    private final BuildSnapshotMapper mapper;

    @Override
    public void save(BuildSnapshot snapshot) {
        mapper.insert(toRow(snapshot));
    }

    @Override
    public Optional<BuildSnapshot> findByIdAndUserId(UUID buildId, UUID userId) {
        return Optional.ofNullable(mapper.findByIdAndUserId(buildId, userId)).map(this::toDomain);
    }

    private BuildSnapshotRow toRow(BuildSnapshot snapshot) {
        return new BuildSnapshotRow(
                snapshot.buildId(),
                snapshot.userId(),
                snapshot.parentBuildId(),
                snapshot.requirementsSnapshot(),
                snapshot.components(),
                snapshot.totalPriceFen(),
                snapshot.budgetMaxFen(),
                snapshot.compatibilityReport(),
                snapshot.benchmarkSnapshot(),
                snapshot.offerSnapshot(),
                snapshot.solverVersion(),
                snapshot.compatibilityRuleVersion(),
                snapshot.catalogVersion(),
                snapshot.createdAt() == null
                        ? null
                        : snapshot.createdAt().atOffset(ZoneOffset.UTC));
    }

    private BuildSnapshot toDomain(BuildSnapshotRow row) {
        return new BuildSnapshot(
                row.buildId(),
                row.userId(),
                row.parentBuildId(),
                row.requirementsSnapshot(),
                row.components(),
                row.totalPriceFen(),
                row.budgetMaxFen(),
                row.compatibilityReport(),
                row.benchmarkSnapshot(),
                row.offerSnapshot(),
                row.solverVersion(),
                row.compatibilityRuleVersion(),
                row.catalogVersion(),
                row.createdAt() == null ? null : row.createdAt().toInstant());
    }
}
