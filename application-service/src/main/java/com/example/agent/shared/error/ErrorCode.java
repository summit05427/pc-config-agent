package com.example.agent.shared.error;

import org.springframework.http.HttpStatus;

/**
 * 错误码契约。
 *
 * <p>业务码按模块划分数值区间，HTTP 状态码由错误码自身决定，避免在业务代码中散落状态码判断。</p>
 */
public interface ErrorCode {

    /**
     * 业务码，成功固定为 {@code 0}。
     *
     * @return 业务码
     */
    int code();

    /**
     * 对应的 HTTP 状态码。
     *
     * @return HTTP 状态码
     */
    HttpStatus httpStatus();

    /**
     * 稳定的字符串错误标识，写入响应信封顶层 {@code errorType}。
     *
     * <p>跨端（Agent、前端）按该值分流提示，一经发布不得改名；数字码仍用于日志与
     * 既有客户端兼容。</p>
     *
     * @return 小写蛇形标识，如 {@code quota_exceeded}
     */
    String errorType();

    /**
     * 默认提示信息，允许调用方在抛出异常时覆盖。
     *
     * @return 默认提示信息
     */
    String message();
}
