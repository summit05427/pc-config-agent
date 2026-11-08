package com.example.agent.shared.security;

import java.time.Duration;
import java.util.Map;

/**
 * 一次签发的业务输入。
 *
 * <p>共享签发器只负责把这份输入编码成 RS256 JWT；主体、用途、有效期与附加 claim
 * 的取舍仍由各模块决定。</p>
 *
 * @param subject     令牌主体
 * @param tokenUse    {@code token_use} 取值
 * @param ttl         有效期
 * @param extraClaims 附加 claim，不含 {@code token_use}
 */
public record TokenSpec(String subject, String tokenUse, Duration ttl, Map<String, Object> extraClaims) {

    public TokenSpec {
        extraClaims = extraClaims == null ? Map.of() : Map.copyOf(extraClaims);
    }
}
