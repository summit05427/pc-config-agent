package com.example.agent.shared.web;

import jakarta.servlet.http.HttpServletRequest;

/**
 * 客户端 IP 解析。
 *
 * <p>生产部署在 Nginx 之后，回源请求由 Nginx 写入代理头，因此优先取
 * {@code X-Forwarded-For} 首段，其次 {@code X-Real-IP}，最后回退到 {@code remoteAddr}。
 * 该值只用于审计与限流，写库前限制长度，避免异常请求头把列写溢出或注入日志。</p>
 */
public final class ClientIpResolver {

    private static final String FORWARDED_FOR_HEADER = "X-Forwarded-For";

    private static final String REAL_IP_HEADER = "X-Real-IP";

    /** 与 {@code auth_audit_logs.ip VARCHAR(45)} 对齐。 */
    private static final int MAX_IP_LENGTH = 45;

    private ClientIpResolver() {
    }

    /**
     * 解析客户端 IP。
     *
     * @param request 当前请求
     * @return 合法时长的 IP；无法解析或超长时返回 {@code null}
     */
    public static String resolve(HttpServletRequest request) {
        String candidate = firstSegment(request.getHeader(FORWARDED_FOR_HEADER));
        if (candidate == null) {
            candidate = request.getHeader(REAL_IP_HEADER);
        }
        if (candidate == null) {
            candidate = request.getRemoteAddr();
        }
        if (candidate == null) {
            return null;
        }
        String normalized = candidate.trim();
        if (normalized.isEmpty() || normalized.length() > MAX_IP_LENGTH) {
            return null;
        }
        return normalized;
    }

    /**
     * 取 {@code X-Forwarded-For} 的首段：可被多次代理追加，只有最左段是原始客户端。
     *
     * @param header 代理头原文，可为 {@code null}
     * @return 首段文本；头缺失或为空时返回 {@code null}
     */
    private static String firstSegment(String header) {
        if (header == null || header.isBlank()) {
            return null;
        }
        int commaIndex = header.indexOf(',');
        return commaIndex < 0 ? header : header.substring(0, commaIndex);
    }
}
