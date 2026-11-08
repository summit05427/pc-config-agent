package com.example.agent.shared.web;

/**
 * 请求上下文，保存当前线程的请求级信息。
 *
 * <p>当前保存请求 ID、客户端 IP 与 User-Agent，供审计与登录限流使用。
 * 使用完毕必须由过滤器在 {@code finally} 中清理，避免线程复用导致数据串号。</p>
 */
public final class RequestContext {

    public static final String REQUEST_ID_MDC_KEY = "requestId";

    private static final ThreadLocal<String> REQUEST_ID_HOLDER = new ThreadLocal<>();
    private static final ThreadLocal<String> CLIENT_IP_HOLDER = new ThreadLocal<>();
    private static final ThreadLocal<String> USER_AGENT_HOLDER = new ThreadLocal<>();

    private RequestContext() {
    }

    public static void setRequestId(String requestId) {
        REQUEST_ID_HOLDER.set(requestId);
    }

    public static String getRequestId() {
        return REQUEST_ID_HOLDER.get();
    }

    /**
     * 设置客户端 IP；由请求元数据过滤器统一解析，业务层只读。
     *
     * @param clientIp 客户端 IP，可为 {@code null}
     */
    public static void setClientIp(String clientIp) {
        CLIENT_IP_HOLDER.set(clientIp);
    }

    /**
     * @return 当前请求的客户端 IP，非 HTTP 线程返回 {@code null}
     */
    public static String getClientIp() {
        return CLIENT_IP_HOLDER.get();
    }

    /**
     * 设置客户端 User-Agent；只用于审计定位，禁止打印完整对话或凭证。
     *
     * @param userAgent 客户端 User-Agent，可为 {@code null}
     */
    public static void setUserAgent(String userAgent) {
        USER_AGENT_HOLDER.set(userAgent);
    }

    /**
     * @return 当前请求的 User-Agent，非 HTTP 线程返回 {@code null}
     */
    public static String getUserAgent() {
        return USER_AGENT_HOLDER.get();
    }

    /**
     * 只清理请求元数据，保留请求 ID，供内外层过滤器各自管理生命周期。
     */
    public static void clearRequestMetadata() {
        CLIENT_IP_HOLDER.remove();
        USER_AGENT_HOLDER.remove();
    }

    public static void clear() {
        REQUEST_ID_HOLDER.remove();
        clearRequestMetadata();
    }
}
