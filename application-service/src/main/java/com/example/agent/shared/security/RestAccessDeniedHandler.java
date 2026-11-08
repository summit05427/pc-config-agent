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
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

/**
 * 已认证但权限不足时返回 403。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final SecurityResponseWriter responseWriter;

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        log.warn("权限不足 path={} requestId={}", request.getRequestURI(), RequestContext.getRequestId());
        responseWriter.write(response, HttpStatus.FORBIDDEN, ApiResponse.failure(CommonErrorCode.FORBIDDEN));
    }
}
