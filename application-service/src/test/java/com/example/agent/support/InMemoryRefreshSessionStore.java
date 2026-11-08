package com.example.agent.support;

import com.example.agent.identity.application.RefreshSessionStore;
import com.example.agent.identity.domain.RefreshSession;
import com.example.agent.identity.domain.RefreshSessionFamily;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/**
 * 测试用内存刷新会话仓储。
 *
 * <p>{@code FOR UPDATE} 的并发语义无法在内存里等价复现，因此这里只保证接口行为一致；
 * 行锁、整族撤销的 SQL 由 {@code RefreshSessionPersistenceTests} 连真实 PostgreSQL 验证。</p>
 */
public class InMemoryRefreshSessionStore implements RefreshSessionStore {

    private final Map<Long, RefreshSession> sessions = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public RefreshSession create(RefreshSessionDraft draft) {
        RefreshSession created = new RefreshSession(
                sequence.incrementAndGet(),
                draft.userId(),
                draft.familyId().toString(),
                draft.tokenHash(),
                Instant.now(),
                null,
                draft.absoluteExpiresAt(),
                draft.idleExpiresAt(),
                null,
                null,
                null);
        sessions.put(created.id(), created);
        return created;
    }

    @Override
    public Optional<RefreshSession> lockByTokenHash(String tokenHash) {
        return sessions.values().stream()
                .filter(session -> session.tokenHash().equals(tokenHash))
                .findFirst();
    }

    @Override
    public void markRotated(Long sessionId, Long replacedById, Instant usedAt) {
        RefreshSession current = sessions.get(sessionId);
        if (current == null || current.isRevoked()) {
            return;
        }
        sessions.put(sessionId, new RefreshSession(
                current.id(), current.userId(), current.familyId(), current.tokenHash(), current.createdAt(),
                usedAt, current.absoluteExpiresAt(), current.idleExpiresAt(), usedAt, "rotated", replacedById));
    }

    @Override
    public int revoke(Long sessionId, String reason, Instant revokedAt) {
        RefreshSession current = sessions.get(sessionId);
        if (current == null || current.isRevoked()) {
            return 0;
        }
        sessions.put(sessionId, revokedCopy(current, reason, revokedAt, current.replacedById()));
        return 1;
    }

    @Override
    public int revokeFamily(UUID familyId, String reason, Instant revokedAt) {
        int revoked = 0;
        for (RefreshSession session : sessions.values()) {
            if (session.familyId().equals(familyId.toString()) && !session.isRevoked()) {
                sessions.put(session.id(), revokedCopy(session, reason, revokedAt, session.replacedById()));
                revoked++;
            }
        }
        return revoked;
    }

    @Override
    public int revokeAllExceptFamily(Long userId, UUID familyId, String reason, Instant revokedAt) {
        int revoked = 0;
        for (RefreshSession session : sessions.values()) {
            boolean isSameUser = session.userId().equals(userId);
            boolean isCurrentFamily = session.familyId().equals(familyId.toString());
            if (!isSameUser || isCurrentFamily || session.isRevoked()) {
                continue;
            }
            sessions.put(session.id(), revokedCopy(session, reason, revokedAt, session.replacedById()));
            revoked++;
        }
        return revoked;
    }

    @Override
    public List<RefreshSessionFamily> listFamilies(Long userId, long offset, int limit) {
        return activeFamilies(userId).stream()
                .skip(offset)
                .limit(limit)
                .toList();
    }

    @Override
    public long countFamilies(Long userId) {
        return activeFamilies(userId).size();
    }

    @Override
    public int revokeFamilyForUser(Long userId, UUID familyId, String reason, Instant revokedAt) {
        int revoked = 0;
        for (RefreshSession session : sessions.values()) {
            boolean isTarget = session.userId().equals(userId)
                    && session.familyId().equals(familyId.toString())
                    && !session.isRevoked();
            if (!isTarget) {
                continue;
            }
            sessions.put(session.id(), revokedCopy(session, reason, revokedAt, session.replacedById()));
            revoked++;
        }
        return revoked;
    }

    @Override
    public int revokeAllForUser(Long userId, String reason, Instant revokedAt) {
        int revoked = 0;
        for (RefreshSession session : sessions.values()) {
            if (!session.userId().equals(userId) || session.isRevoked()) {
                continue;
            }
            sessions.put(session.id(), revokedCopy(session, reason, revokedAt, session.replacedById()));
            revoked++;
        }
        return revoked;
    }

    @Override
    public int deleteExpiredBefore(Instant cutoff) {
        List<Long> expired = sessions.values().stream()
                .filter(session -> session.absoluteExpiresAt().isBefore(cutoff))
                .map(RefreshSession::id)
                .toList();
        expired.forEach(sessions::remove);
        return expired.size();
    }

    /** 直接写入预设会话，供测试构造「已过期」「已撤销」等状态。 */
    public void seed(RefreshSession session) {
        sessions.put(session.id(), session);
        sequence.updateAndGet(current -> Math.max(current, session.id()));
    }

    public List<RefreshSession> findAll() {
        return List.copyOf(sessions.values());
    }

    public Optional<RefreshSession> findById(Long id) {
        return Optional.ofNullable(sessions.get(id));
    }

    /**
     * 与 SQL 聚合口径保持一致：整条轮换链算一台设备，只保留仍有有效行的族，
     * 按最近活跃时间倒序。
     */
    private List<RefreshSessionFamily> activeFamilies(Long userId) {
        Instant now = Instant.now();
        Map<String, List<RefreshSession>> byFamily = sessions.values().stream()
                .filter(session -> session.userId().equals(userId))
                .collect(Collectors.groupingBy(RefreshSession::familyId));
        return byFamily.entrySet().stream()
                .filter(entry -> entry.getValue().stream().anyMatch(session -> isUsable(session, now)))
                .map(entry -> toFamily(entry.getKey(), entry.getValue(), now))
                .sorted(Comparator.comparing(InMemoryRefreshSessionStore::latestActivity).reversed())
                .toList();
    }

    private static boolean isUsable(RefreshSession session, Instant now) {
        return !session.isRevoked()
                && session.idleExpiresAt().isAfter(now)
                && session.absoluteExpiresAt().isAfter(now);
    }

    private static Instant latestActivity(RefreshSessionFamily family) {
        return family.lastUsedAt() != null ? family.lastUsedAt() : family.createdAt();
    }

    private static RefreshSessionFamily toFamily(String familyId, List<RefreshSession> rows, Instant now) {
        Instant createdAt = rows.stream().map(RefreshSession::createdAt).min(Instant::compareTo).orElseThrow();
        Instant lastUsedAt = rows.stream()
                .map(RefreshSession::lastUsedAt)
                .filter(Objects::nonNull)
                .max(Instant::compareTo)
                .orElse(null);
        Instant idleExpiresAt = rows.stream()
                .filter(row -> isUsable(row, now))
                .map(RefreshSession::idleExpiresAt)
                .min(Instant::compareTo)
                .orElseThrow();
        Instant absoluteExpiresAt = rows.stream()
                .filter(row -> isUsable(row, now))
                .map(RefreshSession::absoluteExpiresAt)
                .min(Instant::compareTo)
                .orElseThrow();
        return new RefreshSessionFamily(familyId, createdAt, lastUsedAt, idleExpiresAt, absoluteExpiresAt);
    }

    private static RefreshSession revokedCopy(
            RefreshSession session, String reason, Instant revokedAt, Long replacedById) {
        return new RefreshSession(
                session.id(), session.userId(), session.familyId(), session.tokenHash(), session.createdAt(),
                session.lastUsedAt(), session.absoluteExpiresAt(), session.idleExpiresAt(),
                revokedAt, reason, replacedById);
    }
}
