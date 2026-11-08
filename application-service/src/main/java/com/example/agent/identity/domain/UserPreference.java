package com.example.agent.identity.domain;

import java.time.Instant;

/**
 * 用户偏好读取模型。
 *
 * <p>偏好不参与鉴权，只在对话时由客户端随请求携带、由 Agent 拼进 system prompt；
 * 因此这里不含任何权限字段，也不能据此放宽任何授权。</p>
 *
 * @param instructions   自定义指令，{@code null} 表示未设置
 * @param replyLanguage  回复语言
 * @param responseStyle  回复风格
 * @param useHistory     是否把历史消息注入对话上下文
 * @param updatedAt      最后保存时间（UTC）；{@code null} 表示从未保存过，取自
 *                       {@link #defaults()} 的默认值
 */
public record UserPreference(
        String instructions,
        ReplyLanguage replyLanguage,
        ResponseStyle responseStyle,
        boolean useHistory,
        Instant updatedAt) {

    /**
     * 用户从未保存过偏好时使用的默认值。
     *
     * <p>默认值与 {@code user_preferences} 的列默认值保持一致；{@code updatedAt}
     * 为 {@code null}，表示库里确实还没有这一行，避免把「默认值」伪装成「刚保存过」。</p>
     *
     * @return 默认偏好
     */
    public static UserPreference defaults() {
        return new UserPreference(null, ReplyLanguage.AUTO, ResponseStyle.BALANCED, true, null);
    }
}
