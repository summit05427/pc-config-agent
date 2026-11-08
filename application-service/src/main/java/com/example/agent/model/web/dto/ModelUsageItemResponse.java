package com.example.agent.model.web.dto;

import com.example.agent.model.domain.ModelUsageView;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 单条使用明细响应。
 *
 * <p>Token 用量、耗时与费用在上游未提供时保持 {@code null}，不填 0 或估算值。</p>
 *
 * @param invocationId     调用唯一标识
 * @param taskId           运行时任务标识
 * @param threadId         会话标识
 * @param modelRole        模型角色
 * @param provider         Provider 代码
 * @param modelKey         模型键
 * @param credentialSource 凭证来源
 * @param promptTokens     提示词 Token，可为空
 * @param completionTokens 补全 Token，可为空
 * @param latencyMs        调用耗时，可为空
 * @param status           调用结果
 * @param errorType        错误类型，可为空
 * @param estimatedCost    预估费用；{@code costStatus} 非 {@code ESTIMATED} 时为空
 * @param costStatus       成本状态：{@code ESTIMATED} / {@code UNKNOWN} / {@code BYOK_NOT_BILLED}
 * @param costBearer       成本承担方：{@code PLATFORM} / {@code USER}
 * @param currency         费用币种，未估算时为空
 * @param occurredAt       调用发生时间
 */
public record ModelUsageItemResponse(
        UUID invocationId,
        UUID taskId,
        String threadId,
        String modelRole,
        String provider,
        String modelKey,
        String credentialSource,
        Integer promptTokens,
        Integer completionTokens,
        Integer latencyMs,
        String status,
        String errorType,
        BigDecimal estimatedCost,
        String costStatus,
        String costBearer,
        String currency,
        OffsetDateTime occurredAt) {

    /**
     * @param view 使用明细视图
     * @return 对外响应对象
     */
    public static ModelUsageItemResponse from(ModelUsageView view) {
        return new ModelUsageItemResponse(
                view.invocationId(), view.taskId(), view.threadId(), view.modelRole(),
                view.provider(), view.modelKey(), view.credentialSource(),
                view.promptTokens(), view.completionTokens(), view.latencyMs(),
                view.status(), view.errorType(), view.estimatedCost(),
                view.costStatus(), view.costBearer(), view.currency(), view.occurredAt());
    }
}
