package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 模型运行时开关守卫。
 *
 * <p>总开关关闭时所有内部接口与模型目录统一返回 404，而不是 403 或 503：
 * 关闭状态下这些路径对外「不存在」，避免暴露尚未启用的控制面能力。</p>
 *
 * @see ModelRuntimeProperties#isRuntimeEnabled()
 */
@Component
@RequiredArgsConstructor
public class ModelRuntimeGuard {

    private final ModelRuntimeProperties properties;

    /**
     * 校验运行时已启用。
     *
     * @throws BusinessException 关闭时抛出 {@link ModelErrorCode#RUNTIME_DISABLED}
     */
    public void requireEnabled() {
        if (!properties.isRuntimeEnabled()) {
            throw new BusinessException(ModelErrorCode.RUNTIME_DISABLED);
        }
    }

    /**
     * 校验 BYOK 已启用。
     *
     * <p>与总开关一致，关闭时连接与凭证接口对外「不存在」，而不是返回 403：
     * 未启用的能力不应暴露其存在性。</p>
     *
     * @throws BusinessException 关闭时抛出 {@link ModelErrorCode#BYOK_DISABLED}
     */
    public void requireByokEnabled() {
        requireEnabled();
        if (!properties.isByokEnabled()) {
            throw new BusinessException(ModelErrorCode.BYOK_DISABLED);
        }
    }
}
