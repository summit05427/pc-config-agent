package com.example.agent.identity.infrastructure;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * {@code refresh_sessions} 表数据访问接口，SQL 见 {@code mapper/identity/RefreshSessionMapper.xml}。
 *
 * <p>所有写操作都带条件（{@code revoked_at IS NULL}），保证撤销是幂等的：
 * 并发撤销同一会话时只有第一个请求真正改动数据。</p>
 */
@Mapper
public interface RefreshSessionMapper {

    /**
     * 插入会话并回填自增主键。
     *
     * @param row 待插入行，成功后 {@code id} 被回填
     * @return 影响行数
     */
    int insert(RefreshSessionRow row);

    /**
     * 按令牌摘要加行锁读取。
     *
     * @param tokenHash 令牌摘要
     * @return 命中的行；不存在时返回 {@code null}
     */
    RefreshSessionRow lockByTokenHash(@Param("tokenHash") String tokenHash);

    /**
     * 标记轮换：写入撤销原因、后继会话与使用时间。
     *
     * @param id           旧会话主键
     * @param replacedById 新会话主键
     * @param usedAt       使用时间
     * @return 影响行数
     */
    int markRotated(
            @Param("id") Long id,
            @Param("replacedById") Long replacedById,
            @Param("usedAt") Instant usedAt);

    /**
     * 撤销单个有效会话。
     *
     * @param id        会话主键
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 影响行数
     */
    int revoke(
            @Param("id") Long id,
            @Param("reason") String reason,
            @Param("revokedAt") Instant revokedAt);

    /**
     * 撤销整族中仍然有效的会话。
     *
     * @param familyId  令牌族标识（UUID 文本）
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 影响行数
     */
    int revokeFamily(
            @Param("familyId") String familyId,
            @Param("reason") String reason,
            @Param("revokedAt") Instant revokedAt);

    /**
     * 撤销某用户除指定令牌族之外仍然有效的会话。
     *
     * @param userId    归属用户内部主键
     * @param familyId  需要保留的令牌族（UUID 文本）
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 影响行数
     */
    int revokeAllExceptFamily(
            @Param("userId") Long userId,
            @Param("familyId") String familyId,
            @Param("reason") String reason,
            @Param("revokedAt") Instant revokedAt);

    /**
     * 按令牌族聚合用户仍有效的登录设备。
     *
     * @param userId 归属用户内部主键
     * @param offset 偏移量
     * @param limit  每页条数
     * @return 按最近活跃时间倒序的设备聚合行
     */
    List<RefreshSessionFamilyRow> listFamilies(
            @Param("userId") Long userId,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计用户仍有效的登录设备数。
     *
     * @param userId 归属用户内部主键
     * @return 设备数
     */
    long countFamilies(@Param("userId") Long userId);

    /**
     * 撤销某用户指定令牌族中仍然有效的会话。
     *
     * @param userId    归属用户内部主键
     * @param familyId  令牌族标识（UUID 文本）
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 影响行数
     */
    int revokeFamilyForUser(
            @Param("userId") Long userId,
            @Param("familyId") String familyId,
            @Param("reason") String reason,
            @Param("revokedAt") Instant revokedAt);

    /**
     * 撤销某用户全部仍然有效的会话。
     *
     * @param userId    归属用户内部主键
     * @param reason    撤销原因
     * @param revokedAt 撤销时间
     * @return 影响行数
     */
    int revokeAllForUser(
            @Param("userId") Long userId,
            @Param("reason") String reason,
            @Param("revokedAt") Instant revokedAt);

    /**
     * 删除过期时间早于阈值的会话。
     *
     * @param cutoff 阈值
     * @return 删除行数
     */
    int deleteExpiredBefore(@Param("cutoff") Instant cutoff);
}
