package com.example.agent.identity.web.dto;

/**
 * 刷新响应。
 *
 * <p>只返回新的访问令牌；新的刷新令牌通过 Set-Cookie 轮换，响应体里看不到它。</p>
 *
 * @param accessToken 新的访问令牌
 * @param tokenType   令牌类型，固定为 Bearer
 * @param expiresIn   访问令牌有效期秒数
 */
public record RefreshResponse(String accessToken, String tokenType, long expiresIn) {
}
