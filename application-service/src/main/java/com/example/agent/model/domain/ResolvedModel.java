package com.example.agent.model.domain;

import java.util.List;

/**
 * 解析后的模型（目录中的一条可用模型）。
 *
 * @param provider       Provider 代码，如 {@code openai}
 * @param modelKey       Provider 侧稳定模型标识，如 {@code gpt-4o-mini}
 * @param displayName    展示名，仅用于前端展示
 * @param capabilities   能力标识列表，如 {@code text}、{@code tool_calling}
 * @param contextWindow  上下文窗口，未知时为 {@code null}
 */
public record ResolvedModel(
        String provider,
        String modelKey,
        String displayName,
        List<String> capabilities,
        Integer contextWindow) {

    /**
     * 对外稳定引用：{@code <provider>:<modelKey>}，也是 {@code session_meta.model_key} 的取值格式。
     *
     * @return 完整模型引用
     */
    public String reference() {
        return provider + ":" + modelKey;
    }
}
