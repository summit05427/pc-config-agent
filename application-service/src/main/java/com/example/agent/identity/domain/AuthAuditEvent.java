package com.example.agent.identity.domain;

import org.springframework.modulith.NamedInterface;

/**
 * 认证审计事件类型。
 *
 * <p>取值与 {@code auth_audit_logs.event} 的列注释、对外审计查询的
 * 事件白名单保持一一对应，因此使用固定小写字符串而不是枚举序号，
 * 保证历史数据与后续查询不受枚举顺序影响。</p>
 *
 * <p>全部事件均已接入写入点：{@code role_changed} 由管理端角色变更接口、
 * {@code user_disabled} 由管理端禁用接口与刷新会话校验共同产生。</p>
 *
 * <p>标记为命名接口：模型模块写 BYOK 凭证审计时需要引用固定事件类型，
 * 仅暴露该枚举，避免把 identity 的其余实现细节泄露给其它模块。</p>
 */
@NamedInterface("audit")
public enum AuthAuditEvent {

    LOGIN_SUCCESS("login_success"),
    LOGIN_FAILURE("login_failure"),
    REFRESH_REPLAY("refresh_replay"),
    LOGOUT("logout"),
    LOGOUT_ALL("logout_all"),
    PASSWORD_CHANGE("password_change"),
    USER_DISABLED("user_disabled"),
    ROLE_CHANGED("role_changed"),
    MODEL_CREDENTIAL_CREATED("model_credential_created"),
    MODEL_CREDENTIAL_VERIFIED("model_credential_verified"),
    MODEL_CREDENTIAL_VERIFY_FAILED("model_credential_verify_failed"),
    MODEL_CREDENTIAL_UPDATED("model_credential_updated"),
    MODEL_CREDENTIAL_DELETED("model_credential_deleted");

    private final String value;

    AuthAuditEvent(String value) {
        this.value = value;
    }

    /**
     * @return 写入数据库与对外查询使用的事件标识
     */
    public String value() {
        return value;
    }
}
