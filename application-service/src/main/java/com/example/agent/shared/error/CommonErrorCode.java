package com.example.agent.shared.error;

import java.util.Locale;
import org.springframework.http.HttpStatus;

/**
 * 公共错误码。
 *
 * <p>业务码区间约定：</p>
 * <ul>
 *   <li>{@code 1xxxx}：通用请求错误，如参数、请求体、请求方法</li>
 *   <li>{@code 2xxxx}：认证与权限</li>
 *   <li>{@code 3xxxx}：资源与通用业务错误</li>
 *   <li>{@code 4xxxx}：业务模块专用，按模块再划分区间</li>
 *   <li>{@code 5xxxx}：服务端错误</li>
 * </ul>
 */
public enum CommonErrorCode implements ErrorCode {

    PARAM_INVALID(10001, HttpStatus.BAD_REQUEST, "请求参数不合法"),
    PARAM_MISSING(10002, HttpStatus.BAD_REQUEST, "缺少必要参数"),
    PARAM_TYPE_MISMATCH(10003, HttpStatus.BAD_REQUEST, "参数类型不正确"),
    REQUEST_BODY_INVALID(10004, HttpStatus.BAD_REQUEST, "请求体格式不正确"),
    METHOD_NOT_ALLOWED(10005, HttpStatus.METHOD_NOT_ALLOWED, "请求方法不支持"),
    MEDIA_TYPE_NOT_SUPPORTED(10006, HttpStatus.UNSUPPORTED_MEDIA_TYPE, "请求内容类型不支持"),
    TOO_MANY_REQUESTS(10007, HttpStatus.TOO_MANY_REQUESTS, "请求过于频繁，请稍后重试"),

    UNAUTHORIZED(20001, HttpStatus.UNAUTHORIZED, "未登录或登录状态已失效"),
    FORBIDDEN(20002, HttpStatus.FORBIDDEN, "没有权限执行该操作"),

    BUSINESS_ERROR(30000, HttpStatus.BAD_REQUEST, "业务处理失败"),
    RESOURCE_NOT_FOUND(30001, HttpStatus.NOT_FOUND, "请求的资源不存在"),
    RESOURCE_CONFLICT(30002, HttpStatus.CONFLICT, "资源状态冲突，请刷新后重试"),

    SYSTEM_ERROR(50000, HttpStatus.INTERNAL_SERVER_ERROR, "系统繁忙，请稍后重试"),
    DEPENDENCY_UNAVAILABLE(50001, HttpStatus.SERVICE_UNAVAILABLE, "依赖服务暂不可用");

    private final int code;
    private final HttpStatus httpStatus;
    private final String message;

    CommonErrorCode(int code, HttpStatus httpStatus, String message) {
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
