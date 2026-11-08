package com.example.agent.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.security.SecurityResponseWriter;
import com.example.agent.shared.security.TokenClaims;
import com.example.agent.shared.security.TokenUseFilter;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

/**
 * 令牌用途过滤：服务令牌不能调用用户接口，访问令牌不能调用内部接口。
 */
class TokenUseFilterTests {

    private final SecurityResponseWriter responseWriter = mock(SecurityResponseWriter.class);

    private final TokenUseFilter filter = new TokenUseFilter(responseWriter);

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void serviceTokenShouldBeRejectedOnPublicApi() throws Exception {
        authenticate(TokenClaims.TOKEN_USE_SERVICE);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/auth/me");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        verify(responseWriter).write(eq(response), eq(HttpStatus.UNAUTHORIZED), any(ApiResponse.class));
        assertThat(chain.getRequest()).isNull();
    }

    @Test
    void accessTokenShouldPassPublicApi() throws Exception {
        authenticate(TokenClaims.TOKEN_USE_ACCESS);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/auth/me");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        verify(responseWriter, never()).write(any(), any(), any());
        assertThat(chain.getRequest()).isNotNull();
    }

    @Test
    void accessTokenShouldBeRejectedOnInternalApi() throws Exception {
        authenticate(TokenClaims.TOKEN_USE_ACCESS);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/internal/v1/model-tasks");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        verify(responseWriter).write(eq(response), eq(HttpStatus.UNAUTHORIZED), any(ApiResponse.class));
        assertThat(chain.getRequest()).isNull();
    }

    @Test
    void serviceTokenShouldPassInternalApi() throws Exception {
        authenticate(TokenClaims.TOKEN_USE_SERVICE);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/internal/v1/model-tasks");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        verify(responseWriter, never()).write(any(), any(), any());
        assertThat(chain.getRequest()).isNotNull();
    }

    @Test
    void unauthenticatedRequestShouldPassAndLetAuthorizationRejectIt() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/auth/me");
        MockHttpServletResponse response = new MockHttpServletResponse();
        MockFilterChain chain = new MockFilterChain();

        filter.doFilter(request, response, chain);

        verify(responseWriter, never()).write(any(), any(), any());
        assertThat(chain.getRequest()).isNotNull();
    }

    private void authenticate(String tokenUse) {
        Instant issuedAt = Instant.now();
        Jwt jwt = Jwt.withTokenValue("token")
                .header("alg", "RS256")
                .subject("subject")
                .issuedAt(issuedAt)
                .expiresAt(issuedAt.plusSeconds(60))
                .claim(TokenClaims.TOKEN_USE_CLAIM, tokenUse)
                .claim("roles", List.of("USER"))
                .build();
        SecurityContextHolder.getContext().setAuthentication(new JwtAuthenticationToken(jwt));
    }
}
