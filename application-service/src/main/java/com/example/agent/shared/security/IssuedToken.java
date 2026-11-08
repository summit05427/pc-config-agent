package com.example.agent.shared.security;

/**
 * 令牌签发结果。
 *
 * @param value            令牌字符串
 * @param expiresInSeconds 有效期秒数，供调用方展示或前端提前续期
 */
public record IssuedToken(String value, long expiresInSeconds) {
}
