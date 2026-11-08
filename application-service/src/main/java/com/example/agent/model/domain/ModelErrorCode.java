package com.example.agent.model.domain;

import com.example.agent.shared.error.ErrorCode;
import java.util.Locale;
import org.springframework.http.HttpStatus;

/**
 * 模型模块错误码，区间 {@code 402xx}。
 *
 * <p>{@code errorType} 由枚举名派生成小写蛇形，跨端映射依赖该值，改名即视为契约变更。</p>
 */
public enum ModelErrorCode implements ErrorCode {

    QUOTA_EXCEEDED(40201, HttpStatus.TOO_MANY_REQUESTS, "今日请求额度已用尽，请明日再试"),
    MODEL_NOT_AVAILABLE(40202, HttpStatus.FORBIDDEN, "模型不存在或当前账号不可用"),
    CAPABILITY_UNSUPPORTED(40203, HttpStatus.UNPROCESSABLE_ENTITY, "当前模型不支持所需能力"),
    RUNTIME_DISABLED(40204, HttpStatus.NOT_FOUND, "模型运行时未启用"),
    SERVICE_TOKEN_INVALID(40205, HttpStatus.UNAUTHORIZED, "服务身份校验失败"),
    TASK_NOT_FOUND(40206, HttpStatus.NOT_FOUND, "模型运行时任务不存在或已失效"),
    USER_TOKEN_INVALID(40207, HttpStatus.UNAUTHORIZED, "用户令牌无效或已失效"),
    MODEL_REFERENCE_INVALID(40208, HttpStatus.BAD_REQUEST, "模型标识格式不正确"),
    BYOK_DISABLED(40209, HttpStatus.NOT_FOUND, "BYOK 未启用"),
    CONNECTION_NOT_FOUND(40210, HttpStatus.NOT_FOUND, "模型连接不存在或不属于当前用户"),
    PROVIDER_NOT_SUPPORTED(40211, HttpStatus.BAD_REQUEST, "Provider 不存在或不受支持"),
    CONNECTION_EXISTS(40212, HttpStatus.CONFLICT, "该 Provider 已存在连接，请先删除原连接"),
    CREDENTIAL_CORRUPTED(40213, HttpStatus.INTERNAL_SERVER_ERROR, "凭证数据损坏，请重新录入"),
    BASE_URL_INVALID(40214, HttpStatus.BAD_REQUEST, "接入地址格式不正确"),
    CREDENTIAL_LEASE_CONSUMED(40215, HttpStatus.CONFLICT, "凭证已兑换，请重新发起请求"),
    CREDENTIAL_REVOKED(40216, HttpStatus.UNAUTHORIZED, "凭证已撤销或不可用，请重新配置"),
    CREDENTIAL_VERIFY_FAILED(40217, HttpStatus.BAD_GATEWAY, "凭证验证失败，Provider 暂不可用"),
    LEASE_NOT_BYOK(40218, HttpStatus.CONFLICT, "该任务使用平台托管凭证，无需兑换"),
    CREDENTIAL_REJECTED(40219, HttpStatus.UNPROCESSABLE_ENTITY, "Provider 拒绝了该凭证，请检查密钥"),
    IDEMPOTENCY_CONFLICT(40220, HttpStatus.CONFLICT, "幂等键已用于其他请求，请重新发起"),
    PRICING_VERSION_EXISTS(40221, HttpStatus.CONFLICT, "同一生效时间已存在定价版本"),
    CREDENTIAL_VERIFY_RATE_LIMITED(40222, HttpStatus.TOO_MANY_REQUESTS, "凭证验证过于频繁，请稍后再试"),
    CREDENTIAL_REQUIRED(40223, HttpStatus.BAD_REQUEST, "API Key 不能为空");

    private final int code;
    private final HttpStatus httpStatus;
    private final String message;

    ModelErrorCode(int code, HttpStatus httpStatus, String message) {
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
