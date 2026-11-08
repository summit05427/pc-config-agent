package com.example.agent.model.infrastructure;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 管理端使用明细数据访问，SQL 见 {@code mapper/model/AdminModelUsageMapper.xml}。
 *
 * <p>所有过滤条件都下推到 SQL，分页与聚合在同一组条件下执行，避免前端拉全量再计算。</p>
 */
@Mapper
public interface AdminModelUsageMapper {

    /**
     * 统计满足条件的使用明细条数。
     *
     * @param filter 查询条件
     * @return 记录条数
     */
    long count(@Param("filter") AdminUsageFilter filter);

    /**
     * 分页查询使用明细，按发生时间排序。
     *
     * @param filter 查询条件
     * @param offset 跳过条数
     * @param limit  每页条数
     * @return 使用明细行
     */
    List<AdminUsageRow> findPage(
            @Param("filter") AdminUsageFilter filter,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 聚合总量：请求数、成功/失败数、Token 合计与估算费用。
     *
     * @param filter 聚合条件
     * @return 总量行；无数据时各项为 0 或空
     */
    AdminUsageTotalsRow summarizeTotals(@Param("filter") AdminUsageSummaryFilter filter);

    /**
     * 按成本状态聚合。
     *
     * @param filter 聚合条件
     * @return 各成本状态的条数与费用
     */
    List<AdminUsageStatusRow> summarizeByCostStatus(@Param("filter") AdminUsageSummaryFilter filter);

    /**
     * 按 Provider 聚合，按调用量倒序。
     *
     * @param filter 聚合条件
     * @param limit  最多返回的 Provider 数，避免响应无界增长
     * @return Provider 维度明细
     */
    List<AdminUsageProviderRow> summarizeByProvider(
            @Param("filter") AdminUsageSummaryFilter filter,
            @Param("limit") int limit);

    /**
     * 按模型聚合，按调用量倒序。
     *
     * @param filter 聚合条件
     * @param limit  最多返回的模型数，避免响应无界增长
     * @return 模型维度明细
     */
    List<AdminUsageModelRow> summarizeByModel(
            @Param("filter") AdminUsageSummaryFilter filter,
            @Param("limit") int limit);
}
