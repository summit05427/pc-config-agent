package com.example.agent.model.infrastructure;

import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 运行时任务数据访问，SQL 见 {@code mapper/model/RuntimeTaskMapper.xml}。
 */
@Mapper
public interface RuntimeTaskMapper {

    /**
     * 插入任务。
     *
     * <p>行里带 {@code idempotencyKey} 时 SQL 追加 {@code ON CONFLICT DO NOTHING}：
     * 并发重放不会抛唯一约束异常，返回 0 表示已存在同键任务。</p>
     *
     * @param row 待插入行，主键由应用层生成
     * @return 影响行数；0 表示命中幂等冲突
     */
    int insert(RuntimeTaskRow row);

    /**
     * 按用户与幂等键查询任务。
     *
     * @param userPublicId   用户公开 ID
     * @param idempotencyKey 幂等键
     * @return 命中行；不存在时为 {@code null}
     */
    RuntimeTaskRow findByUserAndKey(
            @Param("userPublicId") UUID userPublicId,
            @Param("idempotencyKey") String idempotencyKey);

    /**
     * 把已到期且仍为 ACTIVE 的任务标记为 EXPIRED。
     *
     * <p>不删除任务行：使用明细通过 {@code task_id} 外键引用任务，
     * 删除会让历史台账失去归属。</p>
     *
     * @param now 判定过期的当前时间
     * @return 影响行数
     */
    int markExpiredBefore(@Param("now") OffsetDateTime now);

    /**
     * 按主键批量查询任务，供使用明细上报做归属与一致性校验。
     *
     * @param ids 任务主键集合
     * @return 命中行；不存在的 ID 不出现在结果中
     */
    List<RuntimeTaskRow> findByIds(@Param("ids") Collection<UUID> ids);

    /**
     * 按主键查询单个任务，供凭证兑换使用。
     *
     * @param id 任务主键
     * @return 命中行；不存在时为 {@code null}
     */
    RuntimeTaskRow findById(@Param("id") UUID id);

    /**
     * 标记任务已兑换凭证。
     *
     * <p>{@code leased_at IS NULL} 条件把「是否已兑换」的判定下推到数据库，
     * 保证并发兑换只有一次能成功。</p>
     *
     * @param id       任务主键
     * @param leasedAt 兑换时间
     * @return 影响行数；0 表示任务不存在、已过期或已被兑换
     */
    int markLeased(@Param("id") UUID id, @Param("leasedAt") OffsetDateTime leasedAt);
}
