package com.example.agent.model.web.dto;

import com.example.agent.model.domain.ModelTaskView;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/**
 * 运行时任务响应，不含任何凭证。
 *
 * @param taskId           任务标识
 * @param provider         Provider 代码
 * @param modelKey         完整模型引用 {@code <provider>:<modelKey>}
 * @param credentialSource 凭证来源
 * @param credentialId     BYOK 凭证标识，MANAGED 时为空
 * @param baseUrl          BYOK 接入地址，MANAGED 时为空
 * @param expiresAt        任务过期时间
 * @param capabilities     目录能力位，供 Agent 在本次请求上做能力门控
 */
public record ModelTaskResponse(
        UUID taskId,
        String provider,
        String modelKey,
        String credentialSource,
        UUID credentialId,
        String baseUrl,
        OffsetDateTime expiresAt,
        List<String> capabilities) {

    /**
     * @param view 服务层返回的任务视图
     * @return 对外响应对象
     */
    public static ModelTaskResponse from(ModelTaskView view) {
        return new ModelTaskResponse(
                view.taskId(), view.provider(), view.modelKey(), view.credentialSource(),
                view.credentialId(), view.baseUrl(), view.expiresAt(), view.capabilities());
    }
}
