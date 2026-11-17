package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * Provider 凭证数据访问，SQL 见 {@code mapper/model/ProviderCredentialMapper.xml}。
 */
@Mapper
public interface ProviderCredentialMapper {

    /**
     * 插入凭证密文。
     *
     * @param row 待插入行
     * @return 影响行数
     */
    int insert(ProviderCredentialRow row);

    /**
     * 查询连接下属于该用户的有效凭证。
     *
     * @param connectionId 连接标识
     * @param userPublicId 用户公开 ID
     * @return 凭证行；不存在或已撤销时为 {@code null}
     */
    ProviderCredentialRow findActiveByConnection(
            @Param("connectionId") UUID connectionId,
            @Param("userPublicId") UUID userPublicId);

    /**
     * 按凭证标识查询属于该用户的有效凭证，供一次性兑换使用。
     *
     * @param id           凭证标识
     * @param userPublicId 用户公开 ID
     * @return 凭证行；不存在或已撤销时为 {@code null}
     */
    ProviderCredentialRow findActiveById(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId);

    /**
     * 标记凭证已通过上游验证。
     *
     * @param id           凭证标识
     * @param userPublicId 用户公开 ID
     * @return 影响行数
     */
    int markVerified(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId);

    /**
     * 标记凭证被上游拒绝：状态置 INVALID，保留行以便用户重新验证或轮换。
     *
     * @param id           凭证标识
     * @param userPublicId 用户公开 ID
     * @return 影响行数
     */
    int markInvalid(
            @Param("id") UUID id,
            @Param("userPublicId") UUID userPublicId);

    /**
     * 撤销连接下全部未撤销凭证。
     *
     * @param connectionId 连接标识
     * @param userPublicId 用户公开 ID
     * @param revokedAt    撤销时间
     * @return 影响行数
     */
    int markRevokedByConnection(
            @Param("connectionId") UUID connectionId,
            @Param("userPublicId") UUID userPublicId,
            @Param("revokedAt") OffsetDateTime revokedAt);
}
