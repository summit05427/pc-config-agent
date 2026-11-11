package com.example.agent.feedback.infrastructure;

import java.time.OffsetDateTime;

/**
 * 管理端筛选条件。
 *
 * <p>时间区间左闭右开：{@code fromInclusive} 含当天零点，{@code toExclusive} 是结束日期次日零点，
 * 避免调用方为「包含结束日」自行加 23:59:59 而漏掉最后一秒。</p>
 *
 * @param rating        评分过滤，{@code null} 表示不限
 * @param reasonCode    原因过滤，{@code null} 表示不限
 * @param userId        提交者公开 ID 过滤
 * @param threadId      会话过滤
 * @param fromInclusive 起始时间（含）
 * @param toExclusive   结束时间（不含）
 */
public record AdminFeedbackFilter(
        String rating,
        String reasonCode,
        String userId,
        String threadId,
        OffsetDateTime fromInclusive,
        OffsetDateTime toExclusive) {
}
