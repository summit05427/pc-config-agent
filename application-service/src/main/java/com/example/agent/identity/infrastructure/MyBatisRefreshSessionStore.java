package com.example.agent.identity.infrastructure;

import com.example.agent.identity.application.RefreshSessionStore;
import com.example.agent.identity.domain.RefreshSession;
import com.example.agent.identity.domain.RefreshSessionFamily;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * PostgreSQL 刷新会话仓储实现。
 *
 * <p>只做「行对象 ↔ 领域对象」转换与 UUID 文本的显式转换，
 * 过期判断、重放判定等业务规则全部留在 {@code RefreshSessionService}。</p>
 */
@Component
@RequiredArgsConstructor
public class MyBatisRefreshSessionStore implements RefreshSessionStore {

    private final RefreshSessionMapper refreshSessionMapper;

    @Override
    public RefreshSession create(RefreshSessionDraft draft) {
        RefreshSessionRow row = new RefreshSessionRow();
        row.setUserId(draft.userId());
        row.setFamilyId(draft.familyId().toString());
        row.setTokenHash(draft.tokenHash());
        row.setAbsoluteExpiresAt(draft.absoluteExpiresAt());
        row.setIdleExpiresAt(draft.idleExpiresAt());
        refreshSessionMapper.insert(row);
        return toSession(row);
    }

    @Override
    public Optional<RefreshSession> lockByTokenHash(String tokenHash) {
        return Optional.ofNullable(refreshSessionMapper.lockByTokenHash(tokenHash)).map(MyBatisRefreshSessionStore::toSession);
    }

    @Override
    public void markRotated(Long sessionId, Long replacedById, Instant usedAt) {
        refreshSessionMapper.markRotated(sessionId, replacedById, usedAt);
    }

    @Override
    public int revoke(Long sessionId, String reason, Instant revokedAt) {
        return refreshSessionMapper.revoke(sessionId, reason, revokedAt);
    }

    @Override
    public int revokeFamily(UUID familyId, String reason, Instant revokedAt) {
        return refreshSessionMapper.revokeFamily(familyId.toString(), reason, revokedAt);
    }

    @Override
    public int revokeAllExceptFamily(Long userId, UUID familyId, String reason, Instant revokedAt) {
        return refreshSessionMapper.revokeAllExceptFamily(userId, familyId.toString(), reason, revokedAt);
    }

    @Override
    public List<RefreshSessionFamily> listFamilies(Long userId, long offset, int limit) {
        return refreshSessionMapper.listFamilies(userId, offset, limit).stream()
                .map(MyBatisRefreshSessionStore::toFamily)
                .toList();
    }

    @Override
    public long countFamilies(Long userId) {
        return refreshSessionMapper.countFamilies(userId);
    }

    @Override
    public int revokeFamilyForUser(Long userId, UUID familyId, String reason, Instant revokedAt) {
        return refreshSessionMapper.revokeFamilyForUser(userId, familyId.toString(), reason, revokedAt);
    }

    @Override
    public int revokeAllForUser(Long userId, String reason, Instant revokedAt) {
        return refreshSessionMapper.revokeAllForUser(userId, reason, revokedAt);
    }

    @Override
    public int deleteExpiredBefore(Instant cutoff) {
        return refreshSessionMapper.deleteExpiredBefore(cutoff);
    }

    private static RefreshSession toSession(RefreshSessionRow row) {
        return new RefreshSession(
                row.getId(),
                row.getUserId(),
                row.getFamilyId(),
                row.getTokenHash(),
                row.getCreatedAt(),
                row.getLastUsedAt(),
                row.getAbsoluteExpiresAt(),
                row.getIdleExpiresAt(),
                row.getRevokedAt(),
                row.getRevokedReason(),
                row.getReplacedById());
    }

    private static RefreshSessionFamily toFamily(RefreshSessionFamilyRow row) {
        return new RefreshSessionFamily(
                row.getFamilyId(),
                row.getCreatedAt(),
                row.getLastUsedAt(),
                row.getIdleExpiresAt(),
                row.getAbsoluteExpiresAt());
    }
}
