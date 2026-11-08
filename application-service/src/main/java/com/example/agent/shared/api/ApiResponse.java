package com.example.agent.shared.api;

import com.example.agent.shared.error.ErrorCode;
import com.example.agent.shared.web.RequestContext;
import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 统一响应结构。
 *
 * <p>HTTP 状态码表达协议层语义，{@code code} 表达业务结果；成功时业务码固定为 {@code 0}。
 * 错误响应额外在**顶层**输出 {@code errorType}：它只在错误时出现，避免与成功响应的
 * {@code data} 混淆——错误时 {@code data} 通常为空，把标识塞进 {@code data} 会让调用方
 * 无法区分「渲染数据」与「弹窗报错」。</p>
 *
 * @param code      业务码，成功固定为 {@code 0}
 * @param errorType 稳定的字符串错误标识，仅错误响应输出
 * @param message   面向调用方的提示信息
 * @param data      业务数据，可为空
 * @param requestId 请求 ID，便于前后端联合排查
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResponse<T>(int code, String errorType, String message, T data, String requestId) {

    public static final int SUCCESS_CODE = 0;

    private static final String SUCCESS_MESSAGE = "ok";

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(SUCCESS_CODE, null, SUCCESS_MESSAGE, data, RequestContext.getRequestId());
    }

    public static ApiResponse<Void> success() {
        return new ApiResponse<>(SUCCESS_CODE, null, SUCCESS_MESSAGE, null, RequestContext.getRequestId());
    }

    public static <T> ApiResponse<T> failure(ErrorCode errorCode) {
        return failure(errorCode, errorCode.message(), null);
    }

    public static <T> ApiResponse<T> failure(ErrorCode errorCode, String message) {
        return failure(errorCode, message, null);
    }

    public static <T> ApiResponse<T> failure(ErrorCode errorCode, String message, T data) {
        return new ApiResponse<>(
                errorCode.code(), errorCode.errorType(), message, data, RequestContext.getRequestId());
    }
}
