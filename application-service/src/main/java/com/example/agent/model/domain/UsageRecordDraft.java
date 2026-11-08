package com.example.agent.model.domain;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 待写入的用量记录。
 *
 * <p>归属、模型一致性与成本口径已由 application 推导完成，这里只承载入库所需的最终值。</p>
 *
 * @param invocationId     调用标识，幂等键
 * @param taskId           运行时任务
 * @param userPublicId     用户公开 ID，来自任务行
 * @param threadId         会话线程
 * @param modelRole        模型角色
 * @param provider         Provider 代码
 * @param modelKey         模型键
 * @param credentialSource 凭证来源
 * @param promptTokens     输入 token
 * @param completionTokens 输出 token
 * @param latencyMs        耗时毫秒
 * @param status           调用状态
 * @param errorType        错误类型
 * @param estimatedCost    估算成本，为空表示不估算
 * @param costStatus       成本状态
 * @param costBearer       成本承担方
 * @param currency         币种
 * @param occurredAt       发生时间
 */
public record UsageRecordDraft(
        UUID invocationId,
        UUID taskId,
        UUID userPublicId,
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
}
