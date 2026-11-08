package com.example.agent.identity.web.dto;

import java.time.Instant;

/**
 * 用户偏好响应。
 *
 * <p>字段与前端设置页一一对应；{@code updatedAt} 为 {@code null} 表示从未保存过，
 * 此时其余字段是默认值而不是用户选择。</p>
 *
 * @param instructions   自定义指令，{@code null} 表示未设置
 * @param replyLanguage  回复语言，取值 {@code auto} / {@code zh-CN} / {@code en-US}
 * @param responseStyle  回复风格，取值 {@code concise} / {@code balanced} / {@code detailed}
 * @param useHistory     是否把历史消息注入对话上下文
 * @param updatedAt      最后保存时间（ISO-8601）
 */
public record UserPreferenceResponse(
        String instructions,
        String replyLanguage,
        String responseStyle,
        boolean useHistory,
        Instant updatedAt) {
}
