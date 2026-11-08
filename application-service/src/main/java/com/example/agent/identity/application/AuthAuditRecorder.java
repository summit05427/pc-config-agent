package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.shared.web.RequestContext;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.modulith.NamedInterface;
import org.springframework.stereotype.Component;

/**
 * 认证审计的安全写入入口。
 *
 * <p>审计是旁路能力：写入失败不能反过来让登录、退出或改密失败，
 * 因此这里统一捕获异常并只记一条 {@code warning}，业务调用方无需处理。
 * 真正的持久化在 {@link AuthAuditLog} 实现中完成，其事务独立于业务事务，
 * 保证「认证失败」这类最终抛异常的流程也能留下审计记录。</p>
 *
 * <p>标记为命名接口：模型模块写 BYOK 凭证审计事件时需要复用同一个写入入口，
 * 只暴露该组件，不暴露 identity 的其它应用服务。</p>
 */
@NamedInterface("audit")
@Component
@RequiredArgsConstructor
@Slf4j
public class AuthAuditRecorder {

    private static final int MAX_USERNAME_LENGTH = 64;
    private static final int MAX_USER_AGENT_LENGTH = 255;
    private static final int MAX_REQUEST_ID_LENGTH = 64;
    private static final String UNKNOWN_USERNAME = "unknown";

    private final AuthAuditLog authAuditLog;

    /**
     * 记录一条认证审计事件。
     *
     * @param event    事件类型
     * @param username 登录名；为空时记为 {@code unknown}
     * @param publicId 用户公开 ID，可为 {@code null}
     */
    public void record(AuthAuditEvent event, String username, String publicId) {
        append(event, truncate(username, MAX_USERNAME_LENGTH, UNKNOWN_USERNAME), publicId);
    }

    /**
     * 已登录用户的事件记录：用户名由 SQL 按公开 ID 回查，调用方无需再查用户表。
     *
     * <p>创建、验证、删除 BYOK 凭证属于安全敏感操作，必须留下审计行。</p>
     *
     * @param event        事件类型
     * @param userPublicId 用户公开 ID
     */
    public void recordForUser(AuthAuditEvent event, UUID userPublicId) {
        append(event, null, userPublicId == null ? null : userPublicId.toString());
    }

    private void append(AuthAuditEvent event, String username, String publicId) {
        AuthAuditEntry entry = new AuthAuditEntry(
                event,
                username,
                publicId,
                RequestContext.getClientIp(),
                truncate(RequestContext.getUserAgent(), MAX_USER_AGENT_LENGTH, null),
                truncate(RequestContext.getRequestId(), MAX_REQUEST_ID_LENGTH, null));
        try {
            authAuditLog.append(entry);
        } catch (RuntimeException ex) {
            // 审计失败不阻断业务：记录事件类型与异常类型即可，不打印请求体
            log.warn("认证审计写入失败 event={} errorType={}", event.value(), ex.getClass().getSimpleName());
        }
    }

    /** 数据库列有长度上限，超长输入必须截断而不是让写入整体失败。 */
    private static String truncate(String value, int maxLength, String fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
