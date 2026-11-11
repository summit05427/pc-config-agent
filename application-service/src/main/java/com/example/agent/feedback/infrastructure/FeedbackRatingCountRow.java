package com.example.agent.feedback.infrastructure;

/**
 * 按评分聚合的计数行。
 *
 * @param upCount   赞的数量
 * @param downCount 踩的数量
 */
public record FeedbackRatingCountRow(long upCount, long downCount) {
}
