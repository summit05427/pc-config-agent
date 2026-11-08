package com.example.agent.identity.web;

import com.example.agent.shared.config.AppSecurityProperties;
import java.time.Duration;
import java.time.Instant;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

/**
 * 刷新 Cookie 的装配。
 *
 * <p>属性集中在这里，避免登录、刷新、退出三处各写一遍导致 Cookie 不一致：
 * <ul>
 *   <li>{@code HttpOnly}：前端 JS 拿不到刷新令牌，XSS 无法直接窃取；</li>
 *   <li>{@code SameSite=Strict}：跨站请求不会携带它，配合服务端 Origin 校验形成双保险；</li>
 *   <li>{@code Path=/api/v1/auth}：只有认证接口能带上它，其他接口即使被注入请求也不携带；</li>
 *   <li>{@code Secure}：本地 http 默认关闭，生产由配置守卫强制开启。</li>
 * </ul>
 */
@Component
public class RefreshCookieFactory {

    /** Cookie 名，前端与服务端共用；不含业务含义，避免暴露实现细节。 */
    public static final String COOKIE_NAME = "agent_refresh";

    private static final String COOKIE_PATH = "/api/v1/auth";
    private static final String SAME_SITE = "Strict";

    private final AppSecurityProperties properties;

    public RefreshCookieFactory(AppSecurityProperties properties) {
        this.properties = properties;
    }

    /**
     * 生成下发用的 Cookie。
     *
     * @param rawToken  刷新令牌明文
     * @param expiresAt 绝对过期时间，决定浏览器端的保留时长
     * @return 待写入 Set-Cookie 的 Cookie
     */
    public ResponseCookie create(String rawToken, Instant expiresAt) {
        Duration maxAge = Duration.between(Instant.now(), expiresAt);
        return base(rawToken).maxAge(maxAge.isNegative() ? Duration.ZERO : maxAge).build();
    }

    /**
     * 生成清除用的 Cookie。
     *
     * <p>属性必须与下发时一致，否则浏览器会当成另一个 Cookie 而保留旧的刷新令牌。</p>
     *
     * @return Max-Age 为 0 的 Cookie
     */
    public ResponseCookie clear() {
        return base("").maxAge(Duration.ZERO).build();
    }

    private ResponseCookie.ResponseCookieBuilder base(String value) {
        return ResponseCookie.from(COOKIE_NAME, value)
                .httpOnly(true)
                .secure(properties.getCookie().isSecure())
                .sameSite(SAME_SITE)
                .path(COOKIE_PATH);
    }
}
