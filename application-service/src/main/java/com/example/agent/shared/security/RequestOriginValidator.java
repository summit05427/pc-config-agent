package com.example.agent.shared.security;

import com.example.agent.shared.config.CorsProperties;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;

/**
 * 校验「带 Cookie 的写请求」来源，防御 CSRF。
 *
 * <p>项目是无状态 JWT，没有表单，真正的 CSRF 风险只在靠 Cookie 认证的接口上：
 * 跨站页面可以伪造 POST /refresh 或 /logout。浏览器对跨站请求必带 {@code Origin}，
 * 因此这里要求 Origin（缺失时退回 Referer）与白名单一致，或者与当前 Host 同源。</p>
 *
 * <p>同源判断是必要的：前端与接口经 Nginx 同域名部署时，Origin 就是站点自身，
 * 没必要逼运维把它重复写进跨域白名单。</p>
 */
@Component
@RequiredArgsConstructor
public class RequestOriginValidator {

    private final CorsProperties corsProperties;

    /**
     * 校验请求来源，不通过时抛 403。
     *
     * @param request 当前请求
     * @throws BusinessException 来源缺失或不可信
     */
    public void requireTrustedOrigin(HttpServletRequest request) {
        String origin = request.getHeader(HttpHeaders.ORIGIN);
        if (isTrusted(request, origin)) {
            return;
        }
        String referer = request.getHeader(HttpHeaders.REFERER);
        if (isTrustedReferer(request, referer)) {
            return;
        }
        throw new BusinessException(CommonErrorCode.FORBIDDEN, "请求来源不可信，已拒绝该操作");
    }

    private boolean isTrusted(HttpServletRequest request, String origin) {
        if (origin == null || origin.isBlank()) {
            return false;
        }
        return corsProperties.getAllowedOrigins().contains(origin) || isSameOrigin(request, origin);
    }

    private boolean isTrustedReferer(HttpServletRequest request, String referer) {
        if (referer == null || referer.isBlank()) {
            return false;
        }
        try {
            URI uri = URI.create(referer);
            if (uri.getScheme() == null || uri.getRawAuthority() == null) {
                return false;
            }
            return isTrusted(request, uri.getScheme() + "://" + uri.getRawAuthority());
        } catch (IllegalArgumentException ex) {
            // 畸形 Referer 直接视为不可信，不能靠异常吞掉校验
            return false;
        }
    }

    private boolean isSameOrigin(HttpServletRequest request, String origin) {
        try {
            String authority = URI.create(origin).getRawAuthority();
            String host = request.getHeader(HttpHeaders.HOST);
            return authority != null && host != null && authority.equalsIgnoreCase(host);
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }
}
