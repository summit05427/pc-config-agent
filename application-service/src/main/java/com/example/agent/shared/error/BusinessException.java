package com.example.agent.shared.error;

/**
 * 业务异常，表示可预期的业务失败。
 *
 * <p>不填充堆栈，避免高频业务失败带来的性能开销；业务异常由全局异常处理器统一记录，
 * 业务代码中不要重复打印日志。</p>
 *
 * <p>{@code payload} 用于错误时需要随响应返回的结构化信息（如额度上限、已用数、
 * 重置时间）。它进入响应 {@code data} 字段，仅限内部/错误场景，正常成功响应不使用。</p>
 */
public class BusinessException extends RuntimeException {

    private final ErrorCode errorCode;

    private final transient Object payload;

    public BusinessException(ErrorCode errorCode) {
        this(errorCode, errorCode.message(), null);
    }

    /**
     * @param errorCode 错误码，决定响应中的业务码、{@code errorType} 与 HTTP 状态码
     * @param message   面向调用方的提示信息，禁止包含堆栈、SQL 与内部标识
     */
    public BusinessException(ErrorCode errorCode, String message) {
        this(errorCode, message, null);
    }

    /**
     * @param errorCode 错误码
     * @param message   面向调用方的提示信息
     * @param payload   随错误返回的结构化信息，可为 {@code null}
     */
    public BusinessException(ErrorCode errorCode, String message, Object payload) {
        super(message, null, false, false);
        this.errorCode = errorCode;
        this.payload = payload;
    }

    public ErrorCode getErrorCode() {
        return errorCode;
    }

    public Object getPayload() {
        return payload;
    }
}
