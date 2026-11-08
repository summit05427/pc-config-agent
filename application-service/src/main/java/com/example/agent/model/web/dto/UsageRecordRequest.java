package com.example.agent.model.web.dto;

import com.example.agent.model.domain.UsageRecordInput;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.time.OffsetDateTime;
import java.util.UUID;

/**
 * 单条使用明细上报。
 *
 * <p>Token 用量与耗时允许为空：上游未返回时留空，禁止填 0 或估算值冒充精确值。
 * 费用不在此处上报：成本由 Java 依据定价表统一计算，上报方无法指定金额。</p>
 *
 * @param invocationId     单次调用幂等键
 * @param taskId           运行时任务标识
 * @param modelRole        模型角色，如 {@code conversation}
 * @param provider         Provider 代码
 * @param modelKey         完整模型引用 {@code <provider>:<modelKey>}
 * @param credentialSource 凭证来源
 * @param promptTokens     输入 token，可空
 * @param completionTokens 输出 token，可空
 * @param latencyMs        耗时毫秒，可空
 * @param status           调用结果 {@code success} / {@code failure}
 * @param errorType        失败时的错误类型，成功时为空
 * @param occurredAt       调用发生时间（UTC），用于选择生效定价版本
 */
public record UsageRecordRequest(
        @NotNull(message = "invocationId 不能为空")
        UUID invocationId,

        @NotNull(message = "taskId 不能为空")
        UUID taskId,

        @NotBlank(message = "modelRole 不能为空")
        @Size(max = 32, message = "modelRole 长度不能超过 32")
        String modelRole,

        @NotBlank(message = "provider 不能为空")
        @Size(max = 32, message = "provider 长度不能超过 32")
        String provider,

        @NotBlank(message = "modelKey 不能为空")
        @Size(max = 64, message = "modelKey 长度不能超过 64")
        String modelKey,

        @NotBlank(message = "credentialSource 不能为空")
        @Size(max = 16, message = "credentialSource 长度不能超过 16")
        String credentialSource,

        @PositiveOrZero(message = "promptTokens 不能为负数")
        Integer promptTokens,

        @PositiveOrZero(message = "completionTokens 不能为负数")
        Integer completionTokens,

        @PositiveOrZero(message = "latencyMs 不能为负数")
        Integer latencyMs,

        @NotBlank(message = "status 不能为空")
        @Pattern(regexp = "success|failure", message = "status 只能是 success 或 failure")
        String status,

        @Size(max = 64, message = "errorType 长度不能超过 64")
        String errorType,

        @NotNull(message = "occurredAt 不能为空")
        OffsetDateTime occurredAt) {

    /**
     * @return 服务层输入模型
     */
    public UsageRecordInput toInput() {
        return new UsageRecordInput(
                invocationId, taskId, modelRole, provider, modelKey, credentialSource,
                promptTokens, completionTokens, latencyMs, status, errorType, occurredAt);
    }
}
