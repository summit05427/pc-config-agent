package com.example.agent.shared.config;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

/**
 * {@link ProdConfigGuard} 单元测试，不启动 Spring 容器。
 *
 * <p>密钥在测试运行时生成，避免把 PEM 字面量散落在多个测试文件里造成漂移。</p>
 */
class ProdConfigGuardTests {

    private static final String PRIVATE_KEY_PROPERTY = "app.security.jwt.private-key";
    private static final String PUBLIC_KEY_PROPERTY = "app.security.jwt.public-key";
    private static final String AUDIENCE_PROPERTY = "app.security.jwt.audience";
    private static final String VALID_PASSWORD = "S3cure-Prod-Passw0rd!";
    private static final String VALID_URL = "jdbc:postgresql://db:5432/agent";
    private static final String VALID_AUDIENCE = "agent-clients";

    private static String privateKeyPem;
    private static String publicKeyPem;
    private static String foreignPublicKeyPem;

    @BeforeAll
    static void generateKeyMaterial() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keyPair = generator.generateKeyPair();
        privateKeyPem = toPem("PRIVATE KEY", keyPair.getPrivate().getEncoded());
        publicKeyPem = toPem("PUBLIC KEY", keyPair.getPublic().getEncoded());
        foreignPublicKeyPem = toPem("PUBLIC KEY", generator.generateKeyPair().getPublic().getEncoded());
    }

    @Test
    void validate_shouldThrow_whenDebugEnabledInProd() {
        StandardEnvironment environment = prodEnvironment(
                "debug", "true");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("debug=true 禁止开启");
    }

    @Test
    void validate_shouldThrow_whenPrivateKeyMissing() {
        StandardEnvironment environment = prodEnvironment(
                PRIVATE_KEY_PROPERTY, "");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining(PRIVATE_KEY_PROPERTY + " 不能为空");
    }

    @Test
    void validate_shouldThrow_whenPrivateKeyIsDefaultPlaceholder() {
        StandardEnvironment environment = prodEnvironment(
                PRIVATE_KEY_PROPERTY, "replace-with-pem-private-key");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining(PRIVATE_KEY_PROPERTY + " 仍是默认占位符");
    }

    @Test
    void validate_shouldThrow_whenPrivateKeyIsNotValidPem() {
        StandardEnvironment environment = prodEnvironment(
                PRIVATE_KEY_PROPERTY, "-----BEGIN PRIVATE KEY----- broken -----END PRIVATE KEY-----");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining(PRIVATE_KEY_PROPERTY + " 不是合法的 PKCS#8 PEM 私钥");
    }

    @Test
    void validate_shouldThrow_whenPublicKeyDoesNotMatchPrivateKey() {
        StandardEnvironment environment = prodEnvironment(
                PUBLIC_KEY_PROPERTY, foreignPublicKeyPem);

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("不是一对匹配的 RSA 密钥");
    }

    @Test
    void validate_shouldThrow_whenAudienceMissing() {
        StandardEnvironment environment = prodEnvironment(
                AUDIENCE_PROPERTY, "");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining(AUDIENCE_PROPERTY + " 不能为空");
    }

    @Test
    void validate_shouldThrow_whenDatasourcePasswordIsDefaultPlaceholder() {
        StandardEnvironment environment = prodEnvironment(
                "spring.datasource.password", "postgres");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("spring.datasource.password 仍是默认占位符");
    }

    @Test
    void validate_shouldThrow_whenInternalSecretIsDefaultPlaceholder() {
        StandardEnvironment environment = prodEnvironment(
                "app.model.runtime-enabled", "true",
                "app.model.internal-auth.client-secret", "replace-with-strong-internal-client-secret");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("app.model.internal-auth.client-secret 不能为空或仍是占位符");
    }

    @Test
    void validate_shouldThrow_whenInternalSecretIsTooShort() {
        StandardEnvironment environment = prodEnvironment(
                "app.model.runtime-enabled", "true",
                "app.model.internal-auth.client-secret", "short-secret");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("长度必须不少于 16 个字符");
    }

    @Test
    void validate_shouldPass_whenRuntimeEnabledWithStrongInternalSecret() {
        StandardEnvironment environment = prodEnvironment(
                "app.model.runtime-enabled", "true",
                "app.model.internal-auth.client-secret", "internal-svc-9f3a7c21");

        assertThatCode(() -> ProdConfigGuard.validate(environment)).doesNotThrowAnyException();
    }

    @Test
    void validate_shouldThrow_whenRefreshCookieIsNotSecure() {
        StandardEnvironment environment = prodEnvironment(
                "app.security.cookie.secure", "false");

        assertThatThrownBy(() -> ProdConfigGuard.validate(environment))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("app.security.cookie.secure 必须为 true");
    }

    @Test
    void validate_shouldPass_whenProdConfigIsValid() {
        StandardEnvironment environment = prodEnvironment();

        assertThatCode(() -> ProdConfigGuard.validate(environment)).doesNotThrowAnyException();
    }

    @Test
    void validate_shouldPass_whenPrivateKeyUsesEscapedNewlines() {
        StandardEnvironment environment = prodEnvironment(
                PRIVATE_KEY_PROPERTY, privateKeyPem.replace("\n", "\\n"),
                PUBLIC_KEY_PROPERTY, publicKeyPem.replace("\n", "\\n"));

        assertThatCode(() -> ProdConfigGuard.validate(environment)).doesNotThrowAnyException();
    }

    @Test
    void validate_shouldSkip_whenProfileIsNotProd() {
        StandardEnvironment environment = environment("local", Map.of(
                "debug", "true",
                PRIVATE_KEY_PROPERTY, "change-me",
                "spring.datasource.password", "postgres"));

        assertThatCode(() -> ProdConfigGuard.validate(environment)).doesNotThrowAnyException();
    }

    /**
     * 构造完整的合法生产配置，允许用偶数个键值对覆盖默认项。
     */
    private static StandardEnvironment prodEnvironment(String... overrides) {
        Map<String, Object> properties = new HashMap<>();
        properties.put("debug", "false");
        properties.put(PRIVATE_KEY_PROPERTY, privateKeyPem);
        properties.put(PUBLIC_KEY_PROPERTY, publicKeyPem);
        properties.put(AUDIENCE_PROPERTY, VALID_AUDIENCE);
        // 生产必须走 HTTPS，刷新 Cookie 必须带 Secure
        properties.put("app.security.cookie.secure", "true");
        properties.put("spring.datasource.url", VALID_URL);
        properties.put("spring.datasource.password", VALID_PASSWORD);
        for (int index = 0; index < overrides.length; index += 2) {
            properties.put(overrides[index], overrides[index + 1]);
        }
        return environment("prod", properties);
    }

    /**
     * 构造隔离的测试环境：移除系统属性与系统环境变量，避免本机 JWT_* 等变量
     * 意外解析测试中的占位符，导致用例结果依赖运行机器。
     */
    private static StandardEnvironment environment(String profile, Map<String, Object> properties) {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().remove(StandardEnvironment.SYSTEM_PROPERTIES_PROPERTY_SOURCE_NAME);
        environment.getPropertySources().remove(StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME);
        environment.setActiveProfiles(profile);
        environment.getPropertySources().addFirst(new MapPropertySource("test", properties));
        return environment;
    }

    private static String toPem(String type, byte[] der) {
        String base64 = Base64.getMimeEncoder(64, new byte[] {'\n'}).encodeToString(der);
        return "-----BEGIN " + type + "-----\n" + base64 + "\n-----END " + type + "-----";
    }
}
