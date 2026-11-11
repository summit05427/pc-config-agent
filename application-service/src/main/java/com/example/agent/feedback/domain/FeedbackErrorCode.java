package com.example.agent.feedback.domain;

import com.example.agent.shared.error.ErrorCode;
import java.util.Locale;
import org.springframework.http.HttpStatus;

/**
 * 反馈模块错误码，区间 {@code 404xx}。
 *
 * <p>标识不合法用 400 而不是 404：路径参数格式错误属于调用方问题，
 * 返回 404 会被前端误判成「消息已被删除」。</p>
 */
public enum FeedbackErrorCode implements ErrorCode {

    MESSAGE_ID_INVALID(40401, HttpStatus.BAD_REQUEST, "消息标识不合法"),
    FEEDBACK_NOT_FOUND(40402, HttpStatus.NOT_FOUND, "反馈不存在"),
    RATING_INVALID(40403, HttpStatus.BAD_REQUEST, "评分只能是 UP 或 DOWN"),
    REASON_INVALID(40404, HttpStatus.BAD_REQUEST, "反馈原因不在允许列表内"),
    THREAD_ID_INVALID(40405, HttpStatus.BAD_REQUEST, "会话标识不合法");

    private final int code;
    private final HttpStatus httpStatus;
    private final String message;

    FeedbackErrorCode(int code, HttpStatus httpStatus, String message) {
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
