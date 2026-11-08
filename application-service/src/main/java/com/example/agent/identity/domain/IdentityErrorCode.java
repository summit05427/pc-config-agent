package com.example.agent.identity.domain;

import com.example.agent.shared.error.ErrorCode;
import java.util.Locale;
import org.springframework.http.HttpStatus;

/**
 * 身份模块错误码，区间 {@code 401xx}。
 *
 * <p>口令相关失败刻意用 HTTP 400 而不是 401：前端把 401 解释为「登录已过期」
 * 并触发全局登出与单飞刷新，改密失败不应该让用户掉线。</p>
 */
public enum IdentityErrorCode implements ErrorCode {

    CURRENT_PASSWORD_INVALID(40102, HttpStatus.BAD_REQUEST, "当前口令不正确"),
    PASSWORD_UNCHANGED(40103, HttpStatus.BAD_REQUEST, "新口令与当前口令相同"),
    EMAIL_TAKEN(40104, HttpStatus.CONFLICT, "邮箱已被其他账号使用"),
    SESSION_NOT_FOUND(40105, HttpStatus.NOT_FOUND, "会话不存在或不属于当前用户");

    private final int code;
    private final HttpStatus httpStatus;
    private final String message;

    IdentityErrorCode(int code, HttpStatus httpStatus, String message) {
        this.code = code;
        this.httpStatus = httpStatus;
        this.message = message;
    }

    @Override
    public int code() {
        return code;
    }

    @Override
    public HttpStatus httpStatus() {
        return httpStatus;
    }

    @Override
    public String errorType() {
        return name().toLowerCase(Locale.ROOT);
    }

    @Override
    public String message() {
        return message;
    }
}
