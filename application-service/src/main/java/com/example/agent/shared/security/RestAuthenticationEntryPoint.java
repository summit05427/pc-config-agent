package com.example.agent.shared.security;

import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.error.CommonErrorCode;
import com.example.agent.shared.web.RequestContext;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

/**
 * 未认证统一入口：无 Token、Token 非法或已过期时返回 401。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RestAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final SecurityResponseWriter responseWriter;

    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response,
                         AuthenticationException authException) throws IOException {
        log.warn("认证失败 path={} requestId={} reason={}",
                request.getRequestURI(), RequestContext.getRequestId(), authException.getClass().getSimpleName());
        responseWriter.write(response, HttpStatus.UNAUTHORIZED, ApiResponse.failure(CommonErrorCode.UNAUTHORIZED));
    }
}
