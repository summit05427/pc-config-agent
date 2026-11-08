package com.example.agent.model.domain;

import com.example.agent.shared.error.BusinessException;
import java.util.Optional;

/**
 * 模型引用 {@code <provider>:<modelKey>}，例如 {@code openai:gpt-4o-mini}。
 *
 * <p>该格式同时用于对外目录、会话选择（{@code session_meta.model_key}）与运行时任务，
 * 只允许一个冒号：Provider 与模型标识都不含冒号，拆错会让解析结果指向不存在的模型。</p>
 *
 * @param provider Provider 代码
 * @param modelKey Provider 侧稳定模型标识
 */
public record ModelReference(String provider, String modelKey) {

    private static final String SEPARATOR = ":";

    /**
     * 解析模型引用。
     *
     * @param value 原始字符串，可为 {@code null}
     * @return 合法时为解析结果
     * @throws BusinessException 格式非法时抛出 {@link ModelErrorCode#MODEL_REFERENCE_INVALID}
     */
    public static ModelReference parse(String value) {
        return tryParse(value)
                .orElseThrow(() -> new BusinessException(ModelErrorCode.MODEL_REFERENCE_INVALID));
    }

    /**
     * 宽松解析，供上报数据校验使用：格式非法按拒绝处理，不抛异常中断整批。
     *
     * @param value 原始字符串，可为 {@code null}
     * @return 合法时为解析结果，否则为空
     */
    public static Optional<ModelReference> tryParse(String value) {
        if (value == null || value.isBlank()) {
            return Optional.empty();
        }
        int separatorIndex = value.indexOf(SEPARATOR);
        if (separatorIndex <= 0 || separatorIndex >= value.length() - 1
                || value.indexOf(SEPARATOR, separatorIndex + 1) >= 0) {
            return Optional.empty();
        }
        return Optional.of(new ModelReference(
                value.substring(0, separatorIndex), value.substring(separatorIndex + 1)));
    }

    /**
     * 还原为完整引用。
     *
     * @return {@code <provider>:<modelKey>}
     */
    public String reference() {
        return provider + SEPARATOR + modelKey;
    }
}
