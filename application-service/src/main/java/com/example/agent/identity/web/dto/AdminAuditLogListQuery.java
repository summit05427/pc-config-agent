package com.example.agent.identity.web.dto;

import com.example.agent.shared.api.PageQuery;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * 管理端审计查询参数。
 *
 * <p>{@code event} 的白名单与 {@code auth_audit_logs.event} 的列注释保持一致；
 * 空串表示不过滤。</p>
 */
@Getter
@Setter
public class AdminAuditLogListQuery extends PageQuery {

    public static final String EVENT_PATTERN =
            "^$|login_success|login_failure|refresh_replay|logout|logout_all"
                    + "|password_change|user_disabled|role_changed"
                    + "|model_credential_created|model_credential_verified"
                    + "|model_credential_verify_failed|model_credential_updated"
                    + "|model_credential_deleted";

    @Pattern(regexp = EVENT_PATTERN, message = "event 不在允许的事件列表内")
    private String event;

    @Size(max = 64, message = "username 不能超过 64 个字符")
    private String username;
}
