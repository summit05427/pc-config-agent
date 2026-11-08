package com.example.agent.shared.config;

import com.example.agent.shared.security.JwtKeyLoader;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 认证鉴权配置。
 *
 * <p>令牌签名使用 RS256 非对称密钥：本服务持有私钥签发，Agent 只拿公钥验签，
 * 密钥泄露面因此收敛到单一服务。所有敏感项只允许通过环境变量注入，
 * 缺失或不是一对合法密钥时应用启动直接失败。</p>
 */
@Getter
@Setter
@Validated
@ConfigurationProperties(prefix = "app.security")
public class AppSecurityProperties {

    @Valid
    private final Jwt jwt = new Jwt();

    @Valid
    private final Refresh refresh = new Refresh();

    @Valid
    private final Cookie cookie = new Cookie();

    private List<@Valid BootstrapUser> bootstrapUsers = new ArrayList<>();

    @Getter
    @Setter
    public static class Jwt {

        @NotBlank(message = "app.security.jwt.private-key 不能为空，请通过 JWT_PRIVATE_KEY 环境变量提供 PKCS#8 PEM 私钥")
        private String privateKey;

        @NotBlank(message = "app.security.jwt.public-key 不能为空，请通过 JWT_PUBLIC_KEY 环境变量提供 X.509 PEM 公钥")
        private String publicKey;

        /** 密钥标识，写入 JWS Header，便于后续轮换时按 kid 选择验签公钥。 */
        @NotBlank(message = "app.security.jwt.kid 不能为空")
        private String kid = "rsa-2026-10";

        /** 令牌受众，Java 与 Agent 必须一致，否则两端无法互相校验。 */
        @NotBlank(message = "app.security.jwt.audience 不能为空")
        private String audience = "agent-clients";

        @NotBlank(message = "app.security.jwt.issuer 不能为空")
        private String issuer = "agent-application-service";

        /**
         * 访问令牌有效期。前端已接入单飞刷新，短令牌被窃取后的可用窗口更小；
         * 需要临时放宽时通过 JWT_ACCESS_TTL 覆盖。
         */
        @NotNull(message = "app.security.jwt.access-token-ttl 不能为空")
        private Duration accessTokenTtl = Duration.ofMinutes(10);

        /**
         * 校验私钥与公钥成对，避免注入错配密钥导致签发的令牌全部无法验签。
         *
         * @return 两者模数一致时为 {@code true}
         */
        @AssertTrue(message = "app.security.jwt.private-key 与 public-key 不是一对匹配的 RSA 密钥")
        public boolean isKeyPairValid() {
            try {
                RSAPrivateKey parsedPrivateKey = JwtKeyLoader.loadPrivateKey(privateKey);
                RSAPublicKey parsedPublicKey = JwtKeyLoader.loadPublicKey(publicKey);
                return parsedPrivateKey.getModulus().equals(parsedPublicKey.getModulus());
            } catch (IllegalArgumentException ex) {
                return false;
            }
        }
    }

    /**
     * 刷新会话配置。
     *
     * <p>双重过期是 Refresh Token 的常见折中：闲置过期让长期不用的会话自动失效，
     * 绝对过期保证令牌族最多存活固定天数，两者都不会因为持续使用而被无限延长。</p>
     */
    @Getter
    @Setter
    public static class Refresh {

        /** 闲置期限：超过该时长未使用即失效，每次成功刷新后重新计时。 */
        @NotNull(message = "app.security.refresh.idle-ttl 不能为空")
        private Duration idleTtl = Duration.ofDays(7);

        /** 绝对期限：自登录时刻起算的硬上限，轮换不会延长。 */
        @NotNull(message = "app.security.refresh.absolute-ttl 不能为空")
        private Duration absoluteTtl = Duration.ofDays(30);

        /**
         * 轮换宽限期。
         *
         * <p>前端并发 401 只应触发一次刷新，但网络重试或两个标签页同时刷新时，
         * 第二个请求会出示刚被轮换的旧令牌。宽限期内的这种「重放」按并发冲突处理，
         * 只拒绝该请求、不撤销整族，避免正常用户被动下线。</p>
         */
        @NotNull(message = "app.security.refresh.rotation-grace 不能为空")
        private Duration rotationGrace = Duration.ofSeconds(60);

        /**
         * 校验两个期限的关系。
         *
         * @return 闲置期限不超过绝对期限时为 {@code true}
         */
        @AssertTrue(message = "app.security.refresh.idle-ttl 必须不大于 absolute-ttl")
        public boolean isIdleWithinAbsolute() {
            if (idleTtl == null || absoluteTtl == null) {
                return true;
            }
            return idleTtl.compareTo(absoluteTtl) <= 0;
        }
    }

    /**
     * Refresh Cookie 配置。
     *
     * <p>本地是 http 环境，浏览器不会保存 {@code Secure} Cookie，因此默认关闭；
     * 生产 profile 由 {@code ProdConfigGuard} 强制为 {@code true}，环境变量无法关闭。</p>
     */
    @Getter
    @Setter
    public static class Cookie {

        private boolean secure = false;
    }

    /**
     * 引导账号：首次启动时若用户名不存在则创建。
     *
     * <p>口令留空表示不创建该账号，便于生产只保留必要的管理账号。</p>
     */
    @Getter
    @Setter
    public static class BootstrapUser {

        @NotBlank(message = "app.security.bootstrap-users[].username 不能为空")
        private String username;

        private String password;

        private List<String> roles = List.of("USER");
    }
}
