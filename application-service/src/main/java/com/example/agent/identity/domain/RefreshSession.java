package com.example.agent.identity.domain;

import java.time.Instant;

/**
 * 刷新会话。
 *
 * <p>一行代表一个 Refresh Token 的生命周期；轮换不会原地更新，而是新建一行并把旧行标记为
 * {@code revoked}，因此「旧令牌被重放」总能被识别出来。</p>
 *
 * @param id                内部自增主键，只在服务端使用
 * @param userId            归属用户内部主键
 * @param familyId          令牌族标识，同一族来自同一次登录
 * @param tokenHash         Refresh Token 的 SHA-256 摘要，明文永不落库
 * @param createdAt         创建时间
 * @param lastUsedAt        最近一次使用时间，未使用为 {@code null}
 * @param absoluteExpiresAt 绝对过期时间，轮换不会延长
 * @param idleExpiresAt     闲置过期时间，每次使用后向后推移但不超过绝对过期
 * @param revokedAt         撤销时间，{@code null} 表示仍然有效
 * @param revokedReason     撤销原因，便于审计与区分重放
 * @param replacedById      轮换出的新会话主键，直接撤销（如退出）时为空
 */
public record RefreshSession(
        Long id,
        Long userId,
        String familyId,
        String tokenHash,
        Instant createdAt,
        Instant lastUsedAt,
        Instant absoluteExpiresAt,
        Instant idleExpiresAt,
        Instant revokedAt,
        String revokedReason,
        Long replacedById) {

    /** 未撤销的会话才可能通过校验；判断逻辑集中在领域对象里，避免各处重复。 */
    public boolean isRevoked() {
        return revokedAt != null;
    }

    /** 被轮换过（存在后继会话），用于区分「正常轮换留下的旧令牌」与「直接撤销」。 */
    public boolean isRotated() {
        return replacedById != null;
    }
}
