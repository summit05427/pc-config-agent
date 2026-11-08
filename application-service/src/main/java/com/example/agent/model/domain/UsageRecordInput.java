package com.example.agent.model.domain;

import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 一次模型调用上报的计量数据（Agent → Java）。
 *
 * <p>Token 用量与耗时允许为空：上游不返回时留空，禁止填 0 或估算值冒充精确值。
 * 费用不在上报范围内：Agent 不持有定价数据，成本由 Java 依据 {@code model_pricing}
 * 计算并写入台账，避免出现「谁上报谁定价」的两套口径。</p>
 *
 * @param invocationId    每次真实模型调用一个，UUIDv4，幂等键
 * @param taskId          对应的运行时任务
 * @param modelRole       模型角色，如 {@code conversation}
 * @param provider        Provider 代码
 * @param modelKey        完整模型引用 {@code <provider>:<modelKey>}，必须与任务解析结果一致
 * @param credentialSource 凭证来源
 * @param promptTokens    输入 token，可空
 * @param completionTokens 输出 token，可空
 * @param latencyMs       耗时毫秒，可空
 * @param status          调用结果：{@code success} / {@code failure}
 * @param errorType       失败时的错误类型，成功时为空
 * @param occurredAt      调用发生时间（UTC）
 */
public record UsageRecordInput(
        UUID invocationId,
        UUID taskId,
        String modelRole,
        String provider,
        String modelKey,
        String credentialSource,
        Integer promptTokens,
        Integer completionTokens,
        Integer latencyMs,
        String status,
        String errorType,
        OffsetDateTime occurredAt) {
}
