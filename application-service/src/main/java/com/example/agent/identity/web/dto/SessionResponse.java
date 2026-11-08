package com.example.agent.identity.web.dto;

import java.time.Instant;

/**
 * 登录设备响应，一个令牌族对应一台设备。
 *
 * <p>不含刷新令牌摘要与内部主键：{@code familyId} 是唯一对外标识，后续撤销请求也用它。</p>
 *
 * @param familyId          令牌族标识（UUID）
 * @param createdAt         登录时间（ISO-8601）
 * @param lastUsedAt        最近活跃时间，从未使用为 {@code null}
 * @param idleExpiresAt     闲置过期时间
 * @param absoluteExpiresAt 绝对过期时间
 * @param current           是否为发起本次请求的设备；仅用于展示，不参与鉴权
 */
public record SessionResponse(
        String familyId,
        Instant createdAt,
        Instant lastUsedAt,
        Instant idleExpiresAt,
        Instant absoluteExpiresAt,
        boolean current) {
}
