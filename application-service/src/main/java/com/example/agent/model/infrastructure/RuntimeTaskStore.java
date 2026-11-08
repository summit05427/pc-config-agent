package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.RuntimeTaskSnapshot;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 运行时任务读写入口，application 只接触 {@link RuntimeTaskSnapshot}。
 */
@Component
@RequiredArgsConstructor
public class RuntimeTaskStore {

    private final RuntimeTaskMapper runtimeTaskMapper;

    public RuntimeTaskSnapshot findById(UUID taskId) {
        return toSnapshot(runtimeTaskMapper.findById(taskId));
    }

    public RuntimeTaskSnapshot findByUserAndKey(UUID userPublicId, String idempotencyKey) {
        return toSnapshot(runtimeTaskMapper.findByUserAndKey(userPublicId, idempotencyKey));
    }

    public List<RuntimeTaskSnapshot> findByIds(Collection<UUID> ids) {
        return runtimeTaskMapper.findByIds(ids).stream()
                .map(RuntimeTaskStore::toSnapshot)
                .toList();
    }

    public int insert(RuntimeTaskSnapshot task) {
        return runtimeTaskMapper.insert(new RuntimeTaskRow(
                task.id(), task.userPublicId(), task.threadId(), task.requestedModel(),
                task.resolvedModel(), task.credentialSource(), task.credentialId(), task.baseUrl(),
                task.status(), task.expiresAt(), null, task.idempotencyKey()));
    }

    public int markExpiredBefore(OffsetDateTime now) {
        return runtimeTaskMapper.markExpiredBefore(now);
    }

    public int markLeased(UUID taskId, OffsetDateTime leasedAt) {
        return runtimeTaskMapper.markLeased(taskId, leasedAt);
    }

    private static RuntimeTaskSnapshot toSnapshot(RuntimeTaskRow row) {
        if (row == null) {
            return null;
        }
        return new RuntimeTaskSnapshot(
                row.id(), row.userPublicId(), row.threadId(), row.requestedModel(),
                row.resolvedModel(), row.credentialSource(), row.credentialId(), row.baseUrl(),
                row.status(), row.expiresAt(), row.createdAt(), row.idempotencyKey());
    }
}
