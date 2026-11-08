package com.example.agent.identity.web.dto;

import java.time.Instant;

/**
 * 管理端审计记录条目。
 *
 * <p>不含 User-Agent、请求 ID 与用户内部主键：这些字段只用于服务端排查，
 * 不需要出现在管理端列表里。</p>
 *
 * @param event     事件标识
 * @param username  登录名
 * @param ip        客户端 IP，可为 {@code null}
 * @param createdAt 发生时间（UTC）
 */
public record AdminAuditLogResponse(String event, String username, String ip, Instant createdAt) {
}
