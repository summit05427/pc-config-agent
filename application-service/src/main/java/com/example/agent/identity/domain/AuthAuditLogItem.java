package com.example.agent.identity.domain;

import java.time.Instant;

/**
 * 审计日志的只读视图。
 *
 * <p>只包含对外可展示的定位字段：事件、登录名、客户端 IP 与发生时间。
 * User-Agent、请求 ID、用户内部主键与任何凭证都不进入该视图。</p>
 *
 * @param event     事件标识，取值见 {@link AuthAuditEvent}
 * @param username  登录名
 * @param ip        客户端 IP，可为 {@code null}
 * @param createdAt 发生时间（UTC）
 */
public record AuthAuditLogItem(String event, String username, String ip, Instant createdAt) {
}
