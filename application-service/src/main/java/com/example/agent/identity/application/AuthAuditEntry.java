package com.example.agent.identity.application;

import com.example.agent.identity.domain.AuthAuditEvent;

/**
 * 一条待写入的认证审计记录。
 *
 * <p>只携带定位信息：用户名、公开 ID、IP、User-Agent 与请求 ID。
 * 不包含口令、Token、Cookie 或请求体，避免把凭证写进审计表。</p>
 *
 * @param event     事件类型
 * @param username  登录名；登录失败时可能是未注册的输入值
 * @param publicId  用户公开 ID，可为 {@code null}（失败或用户已删除）
 * @param ip        客户端 IP，可为 {@code null}
 * @param userAgent 客户端 User-Agent，可为 {@code null}
 * @param requestId 请求 ID，可为 {@code null}
 */
public record AuthAuditEntry(
        AuthAuditEvent event,
        String username,
        String publicId,
        String ip,
        String userAgent,
        String requestId) {
}
