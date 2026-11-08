package com.example.agent.identity.domain;

import java.time.Instant;

/**
 * 登录设备视图：一个令牌族代表一次登录，整条轮换链在列表里只占一行。
 *
 * <p>字段来自对 {@code refresh_sessions} 的聚合，而不是单行：</p>
 * <ul>
 *   <li>{@code createdAt}：族内最早创建时间，即这次登录发生的时刻；</li>
 *   <li>{@code lastUsedAt}：族内最近一次使用时间（含已轮换的历史行），未使用为 {@code null}；</li>
 *   <li>{@code idleExpiresAt} / {@code absoluteExpiresAt}：当前仍有效行的期限。</li>
 * </ul>
 *
 * @param familyId          令牌族标识（UUID），对外即设备标识
 * @param createdAt         登录时间
 * @param lastUsedAt        最近活跃时间，从未使用为 {@code null}
 * @param idleExpiresAt     闲置过期时间
 * @param absoluteExpiresAt 绝对过期时间
 */
public record RefreshSessionFamily(
        String familyId,
        Instant createdAt,
        Instant lastUsedAt,
        Instant idleExpiresAt,
        Instant absoluteExpiresAt) {
}
