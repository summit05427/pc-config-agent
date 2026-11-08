package com.example.agent.identity.web;

import com.example.agent.identity.infrastructure.JwtTokenService;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

/**
 * 读取访问令牌中的会话标识。
 *
 * <p>刷新 Cookie 的 Path 限定在 {@code /api/v1/auth}，业务接口收不到它，
 * 因此「当前设备」只能靠令牌里的 {@code sid} claim 识别。该值仅用于展示与拦截，
 * 不参与鉴权判断。</p>
 */
final class AccessTokenClaims {

    private AccessTokenClaims() {
    }

    /**
     * @param authentication 过滤器链填充的认证信息
     * @return 当前设备所在令牌族；令牌缺少 {@code sid} 或非 JWT 认证时返回 {@code null}
     */
    static String currentFamilyId(Authentication authentication) {
        if (authentication instanceof JwtAuthenticationToken jwtAuthenticationToken) {
            return jwtAuthenticationToken.getToken().getClaimAsString(JwtTokenService.SESSION_CLAIM);
        }
        return null;
    }
}
