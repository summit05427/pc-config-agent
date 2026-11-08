package com.example.agent.model.web.dto;

import com.example.agent.model.domain.ResolvedModel;
import java.util.List;

/**
 * 模型可用性响应。
 *
 * @param available     是否可用（不可用时接口直接返回 403，正常响应固定为 {@code true}）
 * @param provider      Provider 代码
 * @param modelKey      完整模型引用
 * @param displayName   展示名
 * @param capabilities  能力标识
 * @param contextWindow 上下文窗口，未知时为空
 */
public record ModelAvailabilityResponse(
        boolean available,
        String provider,
        String modelKey,
        String displayName,
        List<String> capabilities,
        Integer contextWindow) {

    /**
     * @param model 已解析模型
     * @return 可用性响应
     */
    public static ModelAvailabilityResponse available(ResolvedModel model) {
        return new ModelAvailabilityResponse(
                true, model.provider(), model.reference(), model.displayName(),
                model.capabilities(), model.contextWindow());
    }
}
