package com.example.agent.model.infrastructure;

import com.example.agent.model.domain.ModelUsageView;
import com.example.agent.model.domain.UsageRecordDraft;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 用量明细分页读取与批量写入入口。
 */
@Component
@RequiredArgsConstructor
public class UsageStore {

    private final UsageMapper usageMapper;

    public long countByUser(UUID userPublicId, OffsetDateTime fromInclusive, OffsetDateTime toExclusive) {
        return usageMapper.countByUser(userPublicId, fromInclusive, toExclusive);
    }

    public List<ModelUsageView> findPage(
            UUID userPublicId, OffsetDateTime fromInclusive, OffsetDateTime toExclusive,
            long offset, int limit) {
        return usageMapper.findPage(userPublicId, fromInclusive, toExclusive, offset, limit).stream()
                .map(UsageStore::toView)
                .toList();
    }

    public long sumTokensByUser(UUID userPublicId) {
        return usageMapper.sumTokensByUser(userPublicId);
    }

    public int insertIgnoreDuplicates(List<UsageRecordDraft> records) {
        return usageMapper.insertIgnoreDuplicates(records.stream().map(UsageStore::toRow).toList());
    }

    private static ModelUsageView toView(UsageRecordRow row) {
        return new ModelUsageView(
                row.invocationId(), row.taskId(), row.threadId(), row.modelRole(),
                row.provider(), row.modelKey(), row.credentialSource(),
                row.promptTokens(), row.completionTokens(), row.latencyMs(),
                row.status(), row.errorType(), row.estimatedCost(),
                row.costStatus(), row.costBearer(), row.currency(), row.occurredAt());
    }

    private static UsageRecordRow toRow(UsageRecordDraft draft) {
        return new UsageRecordRow(
                draft.invocationId(), draft.taskId(), draft.userPublicId(), draft.threadId(),
                draft.modelRole(), draft.provider(), draft.modelKey(), draft.credentialSource(),
                draft.promptTokens(), draft.completionTokens(), draft.latencyMs(),
                draft.status(), draft.errorType(), draft.estimatedCost(),
                draft.costStatus(), draft.costBearer(), draft.currency(), draft.occurredAt());
    }
}
