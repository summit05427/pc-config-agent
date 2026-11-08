package com.example.agent.model.infrastructure;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 管理端模型目录数据访问，SQL 见 {@code mapper/model/AdminModelCatalogMapper.xml}。
 *
 * <p>与面向用户的 {@link ModelCatalogMapper} 分离：用户侧只查已启用，
 * 管理端需要同时看到停用记录与 Provider 启用状态，混用会破坏用户侧「只暴露可用模型」的约束。</p>
 */
@Mapper
public interface AdminModelCatalogMapper {

    /**
     * 分页查询模型目录（含停用记录）。
     *
     * @param keyword   已包裹通配符的匹配串，{@code null} 表示不过滤
     * @param provider  Provider 代码，{@code null} 表示不过滤
     * @param enabled   启用状态过滤，{@code null} 表示不过滤
     * @param offset    跳过条数
     * @param limit     每页条数
     * @return 目录行，按 Provider 与模型排序
     */
    List<AdminModelRow> findPage(
            @Param("keyword") String keyword,
            @Param("provider") String provider,
            @Param("enabled") Boolean enabled,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计符合条件的模型条目数。
     *
     * @param keyword  已包裹通配符的匹配串，{@code null} 表示不过滤
     * @param provider Provider 代码，{@code null} 表示不过滤
     * @param enabled  启用状态过滤，{@code null} 表示不过滤
     * @return 条目数
     */
    long count(
            @Param("keyword") String keyword,
            @Param("provider") String provider,
            @Param("enabled") Boolean enabled);

    /**
     * 按完整组合查询模型条目，不限制启用状态。
     *
     * @param provider Provider 代码
     * @param modelKey 模型键
     * @return 命中行；不存在时为 {@code null}
     */
    AdminModelRow findByKey(
            @Param("provider") String provider,
            @Param("modelKey") String modelKey);

    /**
     * 更新模型启用状态。
     *
     * @param provider Provider 代码
     * @param modelKey 模型键
     * @param enabled  目标状态
     * @return 受影响行数；0 表示条目不存在
     */
    int updateEnabled(
            @Param("provider") String provider,
            @Param("modelKey") String modelKey,
            @Param("enabled") boolean enabled);

    /**
     * 查询全部 Provider（含停用）及模型数量。
     *
     * @return Provider 行，按代码排序
     */
    List<AdminProviderRow> findProviders();

    /**
     * 按代码查询 Provider，不限制启用状态。
     *
     * @param code Provider 代码
     * @return 命中行；不存在时为 {@code null}
     */
    AdminProviderRow findProvider(@Param("code") String code);

    /**
     * 更新 Provider 启用状态。
     *
     * @param code    Provider 代码
     * @param enabled 目标状态
     * @return 受影响行数；0 表示 Provider 不存在
     */
    int updateProviderEnabled(@Param("code") String code, @Param("enabled") boolean enabled);

    /**
     * 按模型组合批量读取各自最新的一条定价版本，避免逐模型查询。
     *
     * @param providers  Provider 代码集合，不可为空
     * @param modelKeys  模型键集合，不可为空
     * @return 每个组合的最新版本
     */
    List<AdminPricingRow> findLatestPricingByModels(
            @Param("providers") Collection<String> providers,
            @Param("modelKeys") Collection<String> modelKeys);

    /**
     * 分页查询某模型的定价版本，按生效时间倒序。
     *
     * @param provider Provider 代码
     * @param modelKey 模型键
     * @param offset   跳过条数
     * @param limit    每页条数
     * @return 定价版本行
     */
    List<AdminPricingRow> findPricingPage(
            @Param("provider") String provider,
            @Param("modelKey") String modelKey,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计某模型的定价版本数。
     *
     * @param provider Provider 代码
     * @param modelKey 模型键
     * @return 版本数
     */
    long countPricing(@Param("provider") String provider, @Param("modelKey") String modelKey);

    /**
     * 按唯一键 {@code (provider, modelKey, effectiveFrom)} 查询定价版本。
     *
     * @param provider      Provider 代码
     * @param modelKey      模型键
     * @param effectiveFrom 生效时间
     * @return 命中行；不存在时为 {@code null}
     */
    AdminPricingRow findPricingAt(
            @Param("provider") String provider,
            @Param("modelKey") String modelKey,
            @Param("effectiveFrom") OffsetDateTime effectiveFrom);

    /**
     * 新增一条定价版本。
     *
     * @param provider              Provider 代码
     * @param modelKey              模型键
     * @param currency              币种
     * @param inputPricePerMillion  每百万输入 token 单价
     * @param outputPricePerMillion 每百万输出 token 单价
     * @param effectiveFrom         生效时间
     * @return 受影响行数
     */
    int insertPricing(
            @Param("provider") String provider,
            @Param("modelKey") String modelKey,
            @Param("currency") String currency,
            @Param("inputPricePerMillion") BigDecimal inputPricePerMillion,
            @Param("outputPricePerMillion") BigDecimal outputPricePerMillion,
            @Param("effectiveFrom") OffsetDateTime effectiveFrom);
}
