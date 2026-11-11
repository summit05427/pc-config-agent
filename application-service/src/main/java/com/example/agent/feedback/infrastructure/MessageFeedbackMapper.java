package com.example.agent.feedback.infrastructure;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 消息反馈持久化端口。
 *
 * <p>所有以用户为条件的查询都显式传入 {@code userId}，由 SQL 保证只能读写本人反馈；
 * 管理端查询不复用用户条件，但仅暴露给带 {@code ADMIN} 角色的接口。</p>
 */
@Mapper
public interface MessageFeedbackMapper {

    /**
     * 写入或覆盖一条反馈。
     *
     * @param userId     提交者公开 ID
     * @param threadId   会话标识
     * @param messageId  稳定消息标识
     * @param rating     评分枚举名
     * @param reasonCode 原因枚举名，可为 {@code null}
     * @param comment    备注，可为 {@code null}
     * @return 受影响行数
     */
    int upsert(
            @Param("userId") String userId,
            @Param("threadId") String threadId,
            @Param("messageId") String messageId,
            @Param("rating") String rating,
            @Param("reasonCode") String reasonCode,
            @Param("comment") String comment);

    /**
     * 删除本人对某条消息的反馈。
     *
     * @param userId    提交者公开 ID
     * @param messageId 稳定消息标识
     * @return 受影响行数，0 表示原本没有反馈
     */
    int delete(@Param("userId") String userId, @Param("messageId") String messageId);

    /**
     * 查询本人在一个会话内的全部反馈。
     *
     * @param userId   提交者公开 ID
     * @param threadId 会话标识
     * @return 反馈列表，按创建时间正序
     */
    List<MessageFeedbackRow> findByThread(@Param("userId") String userId, @Param("threadId") String threadId);

    /**
     * 统计管理端筛选结果总数。
     *
     * @param filter 筛选条件
     * @return 总条数
     */
    long countPage(@Param("filter") AdminFeedbackFilter filter);

    /**
     * 分页查询管理端反馈。
     *
     * @param filter 筛选条件
     * @param size   每页条数
     * @param offset 偏移量
     * @return 按时间倒序的反馈
     */
    List<AdminFeedbackRow> selectPage(
            @Param("filter") AdminFeedbackFilter filter, @Param("size") int size, @Param("offset") long offset);

    /**
     * 按评分统计赞踩数量。
     *
     * @param filter 筛选条件
     * @return 计数行，无数据时两个计数均为 0
     */
    FeedbackRatingCountRow countByRating(@Param("filter") AdminFeedbackFilter filter);

    /**
     * 按原因统计踩的数量。
     *
     * @param filter 筛选条件
     * @return 按数量倒序的原因计数
     */
    List<FeedbackReasonCountRow> countByReason(@Param("filter") AdminFeedbackFilter filter);

    /**
     * 导出用查询，按时间倒序，最多返回 {@code limit} 条。
     *
     * @param filter 筛选条件
     * @param limit  上限，防止无筛选导出撑爆内存
     * @return 反馈列表
     */
    List<AdminFeedbackRow> selectForExport(@Param("filter") AdminFeedbackFilter filter, @Param("limit") int limit);
}
