package com.example.agent.identity.infrastructure;

import java.time.Instant;
import lombok.Getter;
import lombok.Setter;

/**
 * {@code refresh_sessions} 表的可变行对象。
 *
 * <p>MyBatis 需要无参构造 + setter 填充结果，因此这里不用不可变 record；
 * 领域对象由 {@link MyBatisRefreshSessionStore} 负责转换。</p>
 */
@Getter
@Setter
public class RefreshSessionRow {

    private Long id;
    private Long userId;
    /** {@code family_id} 在库中是 UUID，这里用字符串承载，转换在仓储层完成。 */
    private String familyId;
    private String tokenHash;
    private Instant createdAt;
    private Instant lastUsedAt;
    private Instant absoluteExpiresAt;
    private Instant idleExpiresAt;
    private Instant revokedAt;
    private String revokedReason;
    private Long replacedById;
}
