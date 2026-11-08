package com.example.agent.shared.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 请求 ID 过滤器。
 *
 * <p>优先复用调用方传入的 {@code X-Request-Id}，未传或不合法时生成新的请求 ID；
 * 请求 ID 同时写入请求上下文、MDC 与响应头，日志与响应可据此关联。</p>
 *
 * <p>类名不使用 {@code RequestContextFilter}，避免与 Spring 自动配置的同名 Bean 冲突。</p>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_HEADER = "X-Request-Id";

    private static final int MAX_REQUEST_ID_LENGTH = 64;

    private static final Pattern SAFE_REQUEST_ID = Pattern.compile("^[A-Za-z0-9._-]{1," + MAX_REQUEST_ID_LENGTH + "}$");

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String requestId = resolveRequestId(request.getHeader(REQUEST_ID_HEADER));
        RequestContext.setRequestId(requestId);
        MDC.put(RequestContext.REQUEST_ID_MDC_KEY, requestId);
        response.setHeader(REQUEST_ID_HEADER, requestId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(RequestContext.REQUEST_ID_MDC_KEY);
            RequestContext.clear();
        }
    }

    /**
     * 校验外部传入的请求 ID，只接受字母、数字、点、下划线与短横线，防止响应头注入。
     *
     * @param candidate 调用方传入的请求 ID，可为空
     * @return 合法请求 ID 或新生成的 32 位请求 ID
     */
    private String resolveRequestId(String candidate) {
        if (candidate != null && SAFE_REQUEST_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString().replace("-", "");
    }
}
