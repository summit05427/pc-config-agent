package com.example.agent.model.infrastructure;

import java.time.LocalDate;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 每日请求额度数据访问，SQL 见 {@code mapper/model/QuotaMapper.xml}。
 *
 * <p>扣减必须是单语句原子操作，禁止先查后改。</p>
 */
@Mapper
public interface QuotaMapper {

    /**
     * 原子占用一次请求额度。
     *
     * @param userPublicId 用户公开 ID
     * @param quotaDate    UTC 自然日
     * @param dailyLimit   当日上限（当日首次写入时快照）
     * @return 扣减后的额度行；返回 {@code null} 表示已用满、本次未扣减
     */
    QuotaRow tryConsume(
            @Param("userPublicId") UUID userPublicId,
            @Param("quotaDate") LocalDate quotaDate,
            @Param("dailyLimit") int dailyLimit);

    /**
     * 查询当日额度行，仅用于超限时组装错误详情。
     *
     * @param userPublicId 用户公开 ID
     * @param quotaDate    UTC 自然日
     * @return 额度行；当日无记录时为 {@code null}
     */
    QuotaRow find(
            @Param("userPublicId") UUID userPublicId,
            @Param("quotaDate") LocalDate quotaDate);

    /**
     * 对账：统计指定 UTC 自然日内已用数超过上限的用户数。
     *
     * <p>原子扣减保证 {@code used_count <= limit_count}，非 0 说明存在绕过扣减路径的写入。</p>
     *
     * @param quotaDate UTC 自然日
     * @return 超限用户数
     */
    int countOverflow(@Param("quotaDate") LocalDate quotaDate);

    /**
     * 对账：统计指定 UTC 自然日内已用满额度的用户数。
     *
     * @param quotaDate UTC 自然日
     * @return 达到上限的用户数
     */
    int countAtLimit(@Param("quotaDate") LocalDate quotaDate);
}
