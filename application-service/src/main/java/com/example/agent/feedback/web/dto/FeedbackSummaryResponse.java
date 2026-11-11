package com.example.agent.feedback.web.dto;

import java.util.List;

/**
 * 反馈统计视图。
 *
 * @param upCount   赞的数量
 * @param downCount 踩的数量
 * @param reasons   踩的原因分布，按数量倒序
 */
public record FeedbackSummaryResponse(long upCount, long downCount, List<FeedbackReasonCount> reasons) {
}
