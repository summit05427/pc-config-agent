package com.example.agent.shared.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 请求元数据过滤器：把客户端 IP 与 User-Agent 写入 {@link RequestContext}。
 *
 * <p>只在过滤器里解析一次，业务层通过 {@code RequestContext} 读取，
 * 避免每个 Service 都依赖 Servlet API。排在 {@code RequestIdFilter} 之后，
 * 其清理动作由外层过滤器的 {@code finally} 统一完成。</p>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class RequestMetadataFilter extends OncePerRequestFilter {

    private static final String USER_AGENT_HEADER = "User-Agent";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        RequestContext.setClientIp(ClientIpResolver.resolve(request));
        RequestContext.setUserAgent(request.getHeader(USER_AGENT_HEADER));
        filterChain.doFilter(request, response);
    }
}
