package com.example.agent.shared.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 模型运行时配置。
 *
 * <p>额度数值来自配置而非代码硬编码；服务令牌凭据只在环境变量中提供。
 * 开关默认关闭，关闭时内部端点返回 404，不改变既有行为。</p>
 */
@Getter
@Setter
@Validated
@ConfigurationProperties(prefix = "app.model")
public class ModelRuntimeProperties {

    /** 控制面总开关；关闭时 {@code /internal/v1/**} 与模型目录接口不可用。 */
    private boolean runtimeEnabled = false;

    /** BYOK 开关；关闭时连接与凭证接口统一返回 404。 */
    private boolean byokEnabled = false;

    /**
     * 平台托管模型开关；关闭时目录不返回平台模型，Auto 与显式选择都只能使用用户 BYOK 模型。
     *
     * <p>默认开启以保持既有部署行为；纯 BYOK 部署把它设为 {@code false}，
     * 避免「后端没有可用平台密钥但目录仍展示平台模型」。</p>
     */
    private boolean managedEnabled = true;

    /**
     * 平台托管可用性探测结果的缓存时长。
     *
     * <p>目录与建任务都会读取该结果；每次请求都探测上游会放大延迟与费用，
     * 因此缓存一小段时间。调用失败会立即失效缓存，避免继续放行失效密钥。</p>
     */
    @NotNull(message = "app.model.managed-probe-ttl 不能为空")
    private Duration managedProbeTtl = Duration.ofSeconds(30);

    /** Auto 对应的平台默认模型，值格式 {@code <provider>:<modelKey>}。 */
    @NotBlank(message = "app.model.default-model-key 不能为空")
    private String defaultModelKey = "openai:gpt-4o-mini";

    /** 运行时任务有效期：过期后不可再兑换凭证。 */
    @NotNull(message = "app.model.task-ttl 不能为空")
    private Duration taskTtl = Duration.ofMinutes(10);

    @Valid
    private final Quota quota = new Quota();

    @Valid
    private final Reconcile reconcile = new Reconcile();

    @Valid
    private final TaskCleanup taskCleanup = new TaskCleanup();

    @Valid
    private final InternalAuth internalAuth = new InternalAuth();

    @Valid
    private final Credential credential = new Credential();

    @Valid
    private final Gateway gateway = new Gateway();

    /**
     * 启用运行时后必须配置服务间凭据，否则 Agent 无法换取服务令牌。
     *
     * @return 满足条件时为 {@code true}
     */
    @AssertTrue(message = "启用 app.model.runtime-enabled 时必须配置 app.model.internal-auth.client-secret")
    public boolean isInternalAuthConfiguredForRuntime() {
        if (!runtimeEnabled) {
            return true;
        }
        String secret = internalAuth.getClientSecret();
        return secret != null && !secret.isBlank();
    }

    /**
     * BYOK 依赖运行时总开关；主密钥是否可用由 model 的 CredentialKeyRing 在启动期校验。
     *
     * @return 满足条件时为 {@code true}
     */
    @AssertTrue(message = "启用 app.model.byok-enabled 时必须同时启用 runtime-enabled")
    public boolean isByokRequiresRuntime() {
        return !byokEnabled || runtimeEnabled;
    }

    @Getter
    @Setter
    public static class Quota {

        /** 每用户每日请求上限；当日首条记录写入时快照。 */
        @Min(value = 1, message = "app.model.quota.daily-requests 必须大于 0")
        private int dailyRequests = 100;
    }

    /**
     * 对账与告警配置。
     *
     * <p>定时任务只做只读统计并输出告警日志，不修改台账；关闭后仍可用
     * {@code scripts/reconcile-model-usage.ps1} 手动执行。</p>
     */
    @Getter
    @Setter
    public static class Reconcile {

        /** 定时对账开关；运行时总开关关闭时任务自动跳过。 */
        private boolean enabled = true;

        /** 对账 cron（UTC），默认每日 00:05。 */
        @NotBlank(message = "app.model.reconcile.cron 不能为空")
        private String cron = "0 5 0 * * *";
    }

    /**
     * 过期运行时任务清理配置。
     *
     * <p>只把到期任务标记为 EXPIRED，不删除任务行：使用明细通过 {@code task_id}
     * 外键引用任务，删除会让历史台账丢失归属。</p>
     */
    @Getter
    @Setter
    public static class TaskCleanup {

        /** 定时清理开关；关闭后任务状态停留在 ACTIVE，不影响过期校验。 */
        private boolean enabled = true;

        /** 清理 cron（UTC），默认每小时整点。 */
        @NotBlank(message = "app.model.task-cleanup.cron 不能为空")
        private String cron = "0 0 * * * *";
    }

    @Getter
    @Setter
    public static class InternalAuth {
        @NotBlank(message = "app.model.internal-auth.client-id 不能为空")
        private String clientId = "agent-service";

        /** 服务间共享密钥，只允许通过环境变量注入，禁止提交真实值。 */
        private String clientSecret;

        /** 服务令牌有效期。 */
        @NotNull(message = "app.model.internal-auth.token-ttl 不能为空")
        private Duration tokenTtl = Duration.ofMinutes(5);
    }

    /**
     * 模型网关配置。
     *
     * <p>Provider 协议、默认接入地址与故障切换全部由网关承担；Java 只把用户凭证
     * 与自定义地址转发给网关做一次性探测。</p>
     */
    @Getter
    @Setter
    public static class Gateway {

        /** LiteLLM 网关地址；Java 自身不直连 Provider。 */
        @NotBlank(message = "app.model.gateway.base-url 不能为空")
        private String baseUrl = "http://127.0.0.1:4000";

        /**
         * 网关 master key，只允许通过环境变量注入。
         *
         * <p>允许为空：本地/Solo 模式可能未部署网关，此时探测返回不可用，但不阻断启动。</p>
         */
        private String masterKey;
    }

    /**
     * 凭证加密配置。
     *
     * <p>主密钥只允许通过环境变量注入，且与数据库备份分开保管；丢失主密钥等于全部
     * BYOK 凭证不可用，部署文档必须写明。</p>
     */
    @Getter
    @Setter
    public static class Credential {

        /** 32 字节 AES 主密钥的 base64 编码，禁止硬编码与提交真实值。 */
        private String masterKey;

        /** 新密文使用的密钥版本；旧版本密文保留兼容解密能力。 */
        @Min(value = 1, message = "app.model.credential.key-version 必须大于 0")
        private int keyVersion = 1;

        /**
         * 主密钥环，每项形如 {@code <version>:<base64>}，多项用英文逗号分隔，用于密钥轮换。
         *
         * <p>配置后按密文中的版本号选择密钥；未配置时退回单密钥 {@link #masterKey}，
         * 且只接受与 {@link #keyVersion} 相同的密文版本。用字符串而非集合接收，
         * 避免空值在配置绑定阶段被误判为类型错误。</p>
         */
        private String keyRing;

        /** 远程验证超时；超时按上游不可用处理，不阻塞用户操作。 */
        @NotNull(message = "app.model.credential.verify-timeout 不能为空")
        private Duration verifyTimeout = Duration.ofSeconds(5);

        /** 单用户每分钟最多手动验证次数，防止把验证端点当作探测跳板。 */
        @Min(value = 1, message = "app.model.credential.verify-rate-limit-per-minute 必须大于 0")
        private int verifyRateLimitPerMinute = 5;
    }
}
