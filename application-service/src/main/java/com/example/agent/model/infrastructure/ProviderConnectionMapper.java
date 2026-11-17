package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Provider 连接数据访问，SQL 见 {@code mapper/model/ProviderConnectionMapper.xml}。
 *
 * <p>所有查询都带 {@code user_public_id} 条件，把归属校验下推到 SQL，避免
 * 「先查后判」之间的竞态。</p>
 */
@Mapper
public interface ProviderConnectionMapper {

    /**
     * 插入连接；时间戳由数据库默认值写入。
     *
     * @param row 待插入行
     * @return 影响行数
     */
    int insert(ProviderConnectionRow row);

    /**
     * 查询用户全部 ACTIVE 连接及当前有效凭证。
     *
     * @param userPublicId 用户公开 ID
     * @return 联表视图，按创建时间倒序
     */
    List<ProviderConnectionViewRow> findActiveViewsByUser(@Param("userPublicId") UUID userPublicId);

    /**
     * 分页查询用户 ACTIVE 连接及当前有效凭证，供 v2 分页端点使用。
     *
     * @param userPublicId 用户公开 ID
     * @param offset       跳过条数
     * @param limit        每页条数
     * @return 联表视图，按创建时间倒序
     */
    List<ProviderConnectionViewRow> findActiveViewsPageByUser(
            @Param("userPublicId") UUID userPublicId,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计用户 ACTIVE 连接数，用于分页 {@code total}。
     *
     * @param userPublicId 用户公开 ID
     * @return 连接条数
     */
    long countActiveByUser(@Param("userPublicId") UUID userPublicId);

    /**
     * 查询属于该用户的单条 ACTIVE 连接。
     *
     * @param id           连接标识
     * @param userPublicId 用户公开 ID
     * @return 联表视图；不存在、已删除或属于他人时为 {@code null}
     */
    ProviderConnectionViewRow findActiveViewById(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId);

    /**
     * 软删除连接：仅 ACTIVE 行可迁移到 DELETED。
     *
     * @param id           连接标识
     * @param userPublicId 用户公开 ID
     * @param updatedAt    更新时间
     * @return 影响行数；0 表示连接不存在或已删除
     */
    int markDeleted(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId,
            @Param("updatedAt") OffsetDateTime updatedAt);

    /**
     * 更新连接接入地址，并清空旧验证时间（地址变化后旧验证不再可信）。
     *
     * @param id           连接标识
     * @param userPublicId 用户公开 ID
     * @param baseUrl      新的接入地址
     * @param updatedAt    更新时间
     * @return 影响行数
     */
    int updateBaseUrl(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId,
            @Param("baseUrl") String baseUrl,
            @Param("updatedAt") OffsetDateTime updatedAt);

    /**
     * 按 Provider 查询该用户的 ACTIVE 连接（同用户同 Provider 唯一）。
     *
     * @param userPublicId 用户公开 ID
     * @param providerCode Provider 代码
     * @return 联表视图；无可用连接时为 {@code null}
     */
    ProviderConnectionViewRow findActiveViewByProvider(
            @Param("userPublicId") UUID userPublicId,
            @Param("providerCode") String providerCode);

    /**
     * 记录最近一次上游验证时间。
     *
     * @param id           连接标识
     * @param userPublicId 用户公开 ID
     * @param verifiedAt   验证时间
     * @return 影响行数
     */
    int markVerified(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId,
            @Param("verifiedAt") OffsetDateTime verifiedAt);

    /**
     * 清空最近验证时间：凭证被上游拒绝后，旧的成功时间不再成立。
     *
     * @param id           连接标识
     * @param userPublicId 用户公开 ID
     * @param updatedAt    更新时间
     * @return 影响行数
     */
    int clearVerifiedAt(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId,
            @Param("updatedAt") OffsetDateTime updatedAt);

    /**
     * 按凭证 ID 清空所属连接的最近验证时间。
     *
     * @param credentialId 凭证标识
     * @param userPublicId 用户公开 ID
     * @param updatedAt    更新时间
     * @return 影响行数
     */
    int clearVerifiedAtByCredential(
            @Param("credentialId") UUID credentialId,
            @Param("userPublicId") UUID userPublicId,
            @Param("updatedAt") OffsetDateTime updatedAt);
}
