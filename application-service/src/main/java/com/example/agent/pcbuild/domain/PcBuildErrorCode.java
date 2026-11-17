package com.example.agent.pcbuild.domain;

import com.example.agent.shared.error.ErrorCode;
import java.util.Locale;
import org.springframework.http.HttpStatus;

/**
 * PC 配置模块错误码，区间 {@code 403xx}。
 *
 * <p>{@code errorType} 由枚举名派生为小写，跨端映射依赖该值，改名视为契约变更。</p>
 */
public enum PcBuildErrorCode implements ErrorCode {

    HARDWARE_NOT_FOUND(40301, HttpStatus.NOT_FOUND, "硬件不存在"),
    BUILD_NOT_FOUND(40302, HttpStatus.NOT_FOUND, "配置快照不存在或不属于当前用户"),
    BUILD_INCOMPLETE(40303, HttpStatus.BAD_REQUEST, "配置必须包含八个硬件类别"),
    CATALOG_UNAVAILABLE(40305, HttpStatus.SERVICE_UNAVAILABLE, "硬件目录不可用"),
    USER_TOKEN_INVALID(40306, HttpStatus.UNAUTHORIZED, "缺少或无效的用户访问令牌"),
    BUILD_OFFER_UNAVAILABLE(40307, HttpStatus.CONFLICT, "所选硬件缺少可用报价"),
    BUILD_INCOMPATIBLE(40308, HttpStatus.UNPROCESSABLE_ENTITY, "所选硬件存在兼容性冲突"),
    BUDGET_EXCEEDED(40309, HttpStatus.UNPROCESSABLE_ENTITY, "配置总价超过预算上限");

    private final int code;
    private final HttpStatus httpStatus;
    private final String message;

    PcBuildErrorCode(int code, HttpStatus httpStatus, String message) {
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
