package com.example.agent.shared.security;

/**
 * 令牌公共 claim 名称与取值。
 *
 * <p>用户令牌与服务令牌共用同一套签名密钥和受众，只能靠 {@code token_use} 区分用途；
 * 常量集中在这里，避免签发端与校验端各写一份字面量而逐渐漂移。</p>
 */
public final class TokenClaims {

    /** 令牌用途 claim。 */
    public static final String TOKEN_USE_CLAIM = "token_use";

    /** 用户访问令牌，仅可调用 {@code /api/v1/**}。 */
    public static final String TOKEN_USE_ACCESS = "access";

    /** 服务令牌，仅可调用 {@code /internal/v1/**}。 */
    public static final String TOKEN_USE_SERVICE = "service";

    /** 权限范围 claim，服务令牌使用。 */
    public static final String SCOPE_CLAIM = "scope";

    private TokenClaims() {
    }
}
