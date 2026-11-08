package com.example.agent.pcbuild.application.port;

import com.example.agent.pcbuild.domain.BuildSnapshot;
import java.util.Optional;
import java.util.UUID;

/**
 * 方案快照仓储端口。
 *
 * <p>表为 append-only：只提供插入与按归属查询，不提供更新与删除。</p>
 */
public interface BuildSnapshotRepository {

    /**
     * @param snapshot 待写入快照
     */
    void save(BuildSnapshot snapshot);

    /**
     * @param buildId 快照标识
     * @param userId  所属用户
     * @return 命中快照；不存在或不属于该用户时为空
     */
    Optional<BuildSnapshot> findByIdAndUserId(UUID buildId, UUID userId);
}
