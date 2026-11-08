package com.example.agent.identity.application;

import com.example.agent.identity.domain.RefreshSession;
import com.example.agent.identity.domain.RefreshSessionFamily;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * 刷新会话数据访问端口。
 *
 * <p>与 {@link UserDirectory} 同样的理由：生产走 MyBatis + PostgreSQL，
 * 测试用内存实现替换，让认证流程测试不必依赖数据库；SQL 语义（行锁、整族撤销）
 * 由独立的 Testcontainers 测试单独验证。</p>
 */
public interface RefreshSessionStore {

    /**
     * 新建会话行。
     *
     * @param draft 除主键与时间戳外的初始字段
     * @return 已落库的会话，含自增主键
     */
    RefreshSession create(RefreshSessionDraft draft);

    /**
     * 按令牌摘要加行锁读取会话。
     *
     * <p>必须加锁：并发刷新时两个请求同时读到「未撤销」，其中一个会误判为使用旧令牌。
     * 锁住后第二个请求能看到第一个请求写入的撤销状态。</p>
     *
     * @param tokenHash 令牌摘要
     * @return 命中的会话；不存在时返回空
     */
    Optional<RefreshSession> lockByTokenHash(String tokenHash);

    /**
     * 标记旧会话已被轮换。
     *
     * @param sessionId    旧会话主键
     * @param replacedById 轮换出的新会话主键
     * @param usedAt       本次使用时间
     */
    void markRotated(Long sessionId, Long replacedById, Instant usedAt);

    /**
     * 撤销单个会话。
     *
     * @param sessionId 会话主键
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 实际更新行数，0 表示已撤销或不存在
     */
    int revoke(Long sessionId, String reason, Instant revokedAt);

    /**
     * 撤销整族会话，用于检测到重放或账号被禁用。
     *
     * @param familyId  令牌族标识
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 实际更新行数
     */
    int revokeFamily(UUID familyId, String reason, Instant revokedAt);

    /**
     * 撤销指定用户除某一令牌族之外的全部有效会话。
     *
     * <p>改密时使用：其他设备下次刷新即失效，当前设备所在族不受影响。</p>
     *
     * @param userId    归属用户内部主键
     * @param familyId  需要保留的令牌族
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 实际更新行数
     */
    int revokeAllExceptFamily(Long userId, UUID familyId, String reason, Instant revokedAt);

    /**
     * 按令牌族列出用户仍然有效的登录设备。
     *
     * <p>聚合语义：同一族的整条轮换链只返回一行，{@code createdAt} 取族内最早时间，
     * {@code lastUsedAt} 取族内最近使用时间；族内没有任何有效行（已撤销或已过期）时整族不出现。</p>
     *
     * @param userId 归属用户内部主键
     * @param offset 偏移量
     * @param limit  每页条数
     * @return 按最近活跃时间倒序排列的设备列表
     */
    List<RefreshSessionFamily> listFamilies(Long userId, long offset, int limit);

    /**
     * 统计用户仍然有效的登录设备数量，与 {@link #listFamilies} 的过滤口径一致。
     *
     * @param userId 归属用户内部主键
     * @return 设备数
     */
    long countFamilies(Long userId);

    /**
     * 撤销某用户指定令牌族中仍然有效的会话。
     *
     * <p>条件里带 {@code user_id}，因此「不是该用户的族」与「族不存在」都返回 0，
     * 调用方无需再单独做归属查询，也就不存在检查与执行之间的竞态。</p>
     *
     * @param userId    归属用户内部主键
     * @param familyId  令牌族标识
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 实际更新行数，0 表示该族不存在、不属于该用户或已撤销
     */
    int revokeFamilyForUser(Long userId, UUID familyId, String reason, Instant revokedAt);

    /**
     * 撤销某用户全部仍然有效的会话，用于「退出所有设备」。
     *
     * @param userId    归属用户内部主键
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 实际更新行数
     */
    int revokeAllForUser(Long userId, String reason, Instant revokedAt);

    /**
     * 物理删除过期已久的历史会话，避免表无限增长。
     *
     * @param cutoff 早于该时间创建的会话将被删除
     * @return 删除行数
     */
    int deleteExpiredBefore(Instant cutoff);

    /**
     * 新建会话所需字段。
     *
     * @param userId           归属用户内部主键
     * @param familyId         令牌族标识
     * @param tokenHash        令牌摘要
     * @param absoluteExpiresAt 绝对过期时间
     * @param idleExpiresAt    闲置过期时间
     */
    record RefreshSessionDraft(
            Long userId,
            UUID familyId,
            String tokenHash,
            Instant absoluteExpiresAt,
            Instant idleExpiresAt) {
    }
}
