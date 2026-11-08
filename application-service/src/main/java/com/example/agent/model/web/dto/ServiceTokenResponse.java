package com.example.agent.model.web.dto;

/**
 * 服务令牌响应。
 *
 * @param accessToken 令牌值
 * @param tokenType   固定 {@code Bearer}
 * @param expiresIn   有效期秒数
 */
public record ServiceTokenResponse(String accessToken, String tokenType, long expiresIn) {
}
