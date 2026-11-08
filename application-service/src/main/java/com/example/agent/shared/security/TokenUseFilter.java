package com.example.agent.shared.security;

import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.CommonErrorCode;
import com.example.agent.shared.web.RequestContext;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 按路径断言令牌用途。
 *
 * <p>Resource Server 只校验签名、有效期与受众，无法分辨令牌是发给用户还是发给服务。
 * 若不额外断言，Agent 用服务令牌就能调用用户接口。这里在
 * {@code BearerTokenAuthenticationFilter} 之后执行：未认证请求直接放行，由授权链统一
 * 返回 401；已认证但用途不匹配的请求直接返回 401。</p>
 */
@Slf4j
@RequiredArgsConstructor
public class TokenUseFilter extends OncePerRequestFilter {

    static final String INTERNAL_PREFIX = "/internal/v1/";

    static final String PUBLIC_PREFIX = "/api/v1/";

    private final SecurityResponseWriter responseWriter;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String path = request.getRequestURI();
        if (path.startsWith(INTERNAL_PREFIX) && !isTokenUse(TokenClaims.TOKEN_USE_SERVICE)) {
            reject(request, response);
            return;
        }
        if (path.startsWith(PUBLIC_PREFIX) && !isTokenUse(TokenClaims.TOKEN_USE_ACCESS)) {
            reject(request, response);
            return;
        }
        filterChain.doFilter(request, response);
    }

    /**
     * @param expected 期望的 {@code token_use}
     * @return 未认证或用途匹配时为 {@code true}
     */
    private boolean isTokenUse(String expected) {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (!(authentication instanceof JwtAuthenticationToken jwtAuthenticationToken)) {
            return true;
        }
        return expected.equals(
                jwtAuthenticationToken.getToken().getClaimAsString(TokenClaims.TOKEN_USE_CLAIM));
    }

    private void reject(HttpServletRequest request, HttpServletResponse response) throws IOException {
        log.warn("令牌用途与路径不匹配 path={} requestId={}",
                request.getRequestURI(), RequestContext.getRequestId());
        responseWriter.write(response, HttpStatus.UNAUTHORIZED, ApiResponse.failure(CommonErrorCode.UNAUTHORIZED));
    }
}
