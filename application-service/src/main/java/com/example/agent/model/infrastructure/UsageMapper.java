package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 使用明细数据访问，SQL 见 {@code mapper/model/UsageMapper.xml}。
 */
@Mapper
public interface UsageMapper {

    /**
     * 批量插入使用明细，按 {@code invocation_id} 幂等：冲突行直接跳过。
     *
     * <p>用 {@code ON CONFLICT DO NOTHING} 而不是捕获唯一键异常：PostgreSQL 中
     * 语句级错误会中止整个事务，异常后无法继续处理同批次其他记录。</p>
     *
     * @param rows 已通过归属与一致性校验的记录
     * @return 实际新插入的行数，用于推导重复条数
     */
    int insertIgnoreDuplicates(@Param("rows") List<UsageRecordRow> rows);

    /**
     * 按用户分页查询本人使用明细，按发生时间倒序。
     *
     * @param userPublicId  用户公开 ID（取自令牌 sub，禁止由调用方传入他人 ID）
     * @param fromInclusive 起始时间（含），为 {@code null} 表示不限
     * @param toExclusive   截止时间（不含），为 {@code null} 表示不限
     * @param offset        跳过条数
     * @param limit         每页条数
     * @return 使用明细行
     */
    List<UsageRecordRow> findPage(
            @Param("userPublicId") UUID userPublicId,
            @Param("fromInclusive") OffsetDateTime fromInclusive,
            @Param("toExclusive") OffsetDateTime toExclusive,
            @Param("offset") long offset,
            @Param("limit") int limit);

    /**
     * 统计用户使用明细总数，用于分页 {@code total}。
     *
     * @param userPublicId  用户公开 ID
     * @param fromInclusive 起始时间（含），可为 {@code null}
     * @param toExclusive   截止时间（不含），可为 {@code null}
     * @return 记录条数
     */
    long countByUser(
            @Param("userPublicId") UUID userPublicId,
            @Param("fromInclusive") OffsetDateTime fromInclusive,
            @Param("toExclusive") OffsetDateTime toExclusive);

    /**
     * 统计用户累计消耗的 Token 数（输入 + 输出），不受日期过滤影响。
     *
     * @param userPublicId 用户公开 ID
     * @return 累计 Token 数；无记录时为 0
     */
    long sumTokensByUser(@Param("userPublicId") UUID userPublicId);

    /**
     * 对账：统计使用明细与所属任务的用户归属或凭证来源不一致的条数。
     *
     * <p>正常写入路径由任务行推导归属，理论上恒为 0；非 0 说明存在绕过校验的写入。</p>
     *
     * @return 不一致条数
     */
    int countAttributionMismatches();

    /**
     * 对账：统计费用估算为负数的条数，防止上游异常数据污染台账。
     *
     * @return 负数条数
     */
    int countNegativeEstimatedCost();

    /**
     * 对账：统计成本状态与金额/币种不一致的条数。
     *
     * <p>{@code ESTIMATED} 必须同时有金额与币种；其他状态必须没有金额。非 0 说明存在
     * 绕过成本估算的写入或历史数据异常。</p>
     *
     * @return 不一致条数
     */
    int countCostStatusMismatches();
}
