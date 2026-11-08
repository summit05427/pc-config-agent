package com.example.agent.identity.infrastructure;

import java.time.Instant;
import lombok.Getter;
import lombok.Setter;

/**
 * {@code auth_audit_logs} 管理端查询的行映射对象。
 *
 * <p>只映射对外展示的四个字段；User-Agent 与请求 ID 查询时不下发。</p>
 */
@Getter
@Setter
public class AuthAuditLogRow {

    private String event;
    private String username;
    private String ip;
    private Instant createdAt;
}
