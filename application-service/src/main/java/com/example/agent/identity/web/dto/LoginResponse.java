package com.example.agent.identity.web.dto;

/**
 * 登录响应。
 *
 * <p>刷新令牌只通过 HttpOnly Cookie 下发，绝不出现在响应体里，
 * 因此这里的字段只描述访问令牌与用户信息。</p>
 *
 * @param accessToken 访问令牌
 * @param tokenType   令牌类型，固定为 Bearer
 * @param expiresIn   访问令牌有效期秒数
 * @param user        当前用户（公开 ID、登录名、角色）
 */
public record LoginResponse(String accessToken, String tokenType, long expiresIn, CurrentUserResponse user) {
}
