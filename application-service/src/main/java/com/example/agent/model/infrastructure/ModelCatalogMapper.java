package com.example.agent.model.infrastructure;

import java.util.List;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 模型目录数据访问，SQL 见 {@code mapper/model/ModelCatalogMapper.xml}。
 */
@Mapper
public interface ModelCatalogMapper {

    /**
     * 查询所有已启用的模型（同时要求 Provider 已启用）。
     *
     * @return 目录行，按 Provider、模型排序
     */
    List<ModelRow> findEnabled();

    /**
     * 分页查询已启用模型（同时要求 Provider 已启用），供 v2 分页端点使用。
     *
     * @param offset 跳过条数
     * @param limit  每页条数
     * @return 目录行，按 Provider、模型排序
     */
    List<ModelRow> findEnabledPage(
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计已启用模型总数，用于分页 {@code total}。
     *
     * @return 条目数
     */
    long countEnabled();

    /**
     * 分页查询「当前用户可见」的模型：平台托管模型 + 已接入 Provider 的 BYOK 专用模型。
     *
     * @param userPublicId 用户公开 ID
     * @param offset       跳过条数
     * @param limit        每页条数
     * @return 目录行，按 Provider、模型排序
     */
    List<ModelRow> findVisiblePage(
            @Param("userPublicId") UUID userPublicId,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计「当前用户可见」的模型总数。
     *
     * @param userPublicId 用户公开 ID
     * @return 条目数
     */
    long countVisible(@Param("userPublicId") UUID userPublicId);

    /**
     * 按 Provider 与模型标识查询当前用户可见的模型。
     *
     * @param providerCode Provider 代码
     * @param modelKey     Provider 侧模型标识
     * @param userPublicId 用户公开 ID
     * @return 命中行；不存在、已停用或无 BYOK 连接时 {@code null}
     */
    ModelRow findVisibleByKey(
            @Param("providerCode") String providerCode,
            @Param("modelKey") String modelKey,
            @Param("userPublicId") UUID userPublicId);

    /**
     * 查询已启用 Provider 及其启用模型数量，供 BYOK 供应商选择器使用。
     *
     * @return Provider 聚合行，按代码排序
     */
    List<ProviderSummaryRow> findEnabledProviderSummaries();

    /**
     * 按 Provider 与模型标识查询已启用模型。
     *
     * @param providerCode Provider 代码
     * @param modelKey     Provider 侧模型标识
     * @return 命中行；不存在或已停用时为 {@code null}
     */
    ModelRow findEnabledByKey(
            @Param("providerCode") String providerCode,
            @Param("modelKey") String modelKey);

    /**
     * 按代码查询已启用的 Provider。
     *
     * @param providerCode Provider 代码
     * @return Provider 行；不存在或已停用时为 {@code null}
     */
    ProviderRow findEnabledProvider(@Param("providerCode") String providerCode);

    /**
     * 查询 Provider 下第一个已启用模型，供验证探测的最小 chat 回退使用。
     *
     * @param providerCode Provider 代码
     * @return 命中行；Provider 无可用模型时为 {@code null}
     */
    ModelRow findFirstEnabledByProvider(@Param("providerCode") String providerCode);
}
