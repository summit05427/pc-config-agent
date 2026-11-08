package com.example.agent.model.domain;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 模型运行时任务视图：Agent 凭该结果执行调用，**不含任何凭证**。
 *
 * @param taskId           任务标识，BYOK 兑换凭证时使用
 * @param provider         解析后的 Provider
 * @param modelKey         解析后的稳定模型标识（{@code <provider>:<modelKey>}）
 * @param credentialSource 凭证来源：{@code MANAGED} / {@code BYOK}
 * @param credentialId     BYOK 凭证标识，MANAGED 时为空
 * @param baseUrl          BYOK 接入地址快照，MANAGED 时为空
 * @param expiresAt        任务过期时间
 * @param capabilities     解析模型的目录能力位，供 Agent 在请求侧做能力门控
 */
public record ModelTaskView(
        UUID taskId,
        String provider,
        String modelKey,
        String credentialSource,
        UUID credentialId,
        String baseUrl,
        OffsetDateTime expiresAt,
        List<String> capabilities) {
}
