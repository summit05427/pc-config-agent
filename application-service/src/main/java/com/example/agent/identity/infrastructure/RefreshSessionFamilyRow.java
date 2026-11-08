package com.example.agent.identity.infrastructure;

import java.time.Instant;
import lombok.Getter;
import lombok.Setter;

/**
 * {@code refresh_sessions} 按令牌族聚合后的行对象，只读。
 *
 * <p>MyBatis 需要无参构造 + setter 填充聚合结果，因此不用 record；
 * 领域投影由 {@link MyBatisRefreshSessionStore} 负责转换。</p>
 */
@Getter
@Setter
public class RefreshSessionFamilyRow {

    private String familyId;
    private Instant createdAt;
    private Instant lastUsedAt;
    private Instant idleExpiresAt;
    private Instant absoluteExpiresAt;
}
