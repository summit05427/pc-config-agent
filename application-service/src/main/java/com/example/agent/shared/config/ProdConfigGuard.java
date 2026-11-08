package com.example.agent.shared.config;

import com.example.agent.shared.security.JwtKeyLoader;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.Environment;

/**
 * 生产配置硬校验：在容器 refresh 之前拦截危险的默认配置。
 *
 * <p>通过 {@code META-INF/spring.factories} 注册为 {@link ApplicationContextInitializer}，
 * 执行时机早于 Bean 初始化、数据库连接与 Tomcat 启动，避免应用带着默认密钥或默认口令上线。</p>
 */
public class ProdConfigGuard implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    private static final String PROD_PROFILE = "prod";

    private static final String JWT_PRIVATE_KEY = "app.security.jwt.private-key";
    private static final String JWT_PUBLIC_KEY = "app.security.jwt.public-key";
    private static final String JWT_AUDIENCE = "app.security.jwt.audience";

    private static final String MODEL_RUNTIME_ENABLED = "app.model.runtime-enabled";
    private static final String INTERNAL_AUTH_CLIENT_SECRET = "app.model.internal-auth.client-secret";

    /** 服务令牌口令最短长度：过短的口令可被暴力猜测后伪造内部调用。 */
    private static final int MIN_INTERNAL_SECRET_LENGTH = 16;

    /** 占位符无法解析时 Spring 会直接抛异常，用该标记替代原始值，便于统一汇总错误。 */
    private static final String UNRESOLVED_PLACEHOLDER = "${unresolved}";

    /**
     * 生产环境禁止出现的默认占位符词根，大小写不敏感。
     *
     * <p>匹配规则是“完全相等”或“词根后紧跟非字母字符”，避免把
     * {@code my-secret-2026} 这类合法强口令误判为默认值。</p>
     */
    private static final Set<String> DEFAULT_PLACEHOLDER_WORDS = Set.of(
            "change-me", "changeme", "change_me",
            "replace-me", "replace_me", "replace-with",
            "your-secret", "your_secret", "your-password", "your_password",
            "password", "secret", "example", "test", "test-only",
            "dev", "local", "todo", "postgres");

    @Override
    public void initialize(ConfigurableApplicationContext applicationContext) {
        validate(applicationContext.getEnvironment());
    }

    /**
     * 校验生产环境关键配置，一次性收集全部问题后抛出异常。
     *
     * <p>错误信息只包含属性名与原因，不输出真实密钥或口令值。</p>
     *
     * @param environment Spring 环境，非 prod profile 时直接跳过
     * @throws IllegalStateException 存在任一非法配置时抛出
     */
    static void validate(Environment environment) {
        if (!isProdProfileActive(environment)) {
            return;
        }

        List<String> errors = new ArrayList<>();
        if (Boolean.TRUE.equals(environment.getProperty("debug", Boolean.class, false))) {
            errors.add("debug=true 禁止开启");
        }
        validateJwtKeys(environment, errors);
        validateJwtAudience(environment, errors);
        validateCookieSecure(environment, errors);
        validateDatasourceUrl(environment, errors);
        validateDatasourcePassword(environment, errors);
        validateInternalAuthSecret(environment, errors);

        if (!errors.isEmpty()) {
            throw new IllegalStateException("生产环境配置校验失败（prod）：" + String.join("；", errors));
        }
    }

    private static boolean isProdProfileActive(Environment environment) {
        for (String profile : environment.getActiveProfiles()) {
            if (PROD_PROFILE.equalsIgnoreCase(profile)) {
                return true;
            }
        }
        return false;
    }

    /**
     * 校验 RSA 密钥：必须存在、非占位符、可解析，且私钥与公钥成对。
     *
     * <p>只做字符串长度校验已经没有意义——RS256 的安全性来自密钥本身，
     * 一对错配的密钥会让签发的令牌全部验签失败。</p>
     */
    private static void validateJwtKeys(Environment environment, List<String> errors) {
        String privateKey = readRawValue(environment, JWT_PRIVATE_KEY);
        String publicKey = readRawValue(environment, JWT_PUBLIC_KEY);

        RSAPrivateKey parsedPrivateKey = validatePrivateKey(privateKey, errors);
        RSAPublicKey parsedPublicKey = validatePublicKey(publicKey, errors);

        if (parsedPrivateKey != null && parsedPublicKey != null
                && !parsedPrivateKey.getModulus().equals(parsedPublicKey.getModulus())) {
            errors.add(JWT_PRIVATE_KEY + " 与 " + JWT_PUBLIC_KEY + " 不是一对匹配的 RSA 密钥");
        }
    }

    private static RSAPrivateKey validatePrivateKey(String value, List<String> errors) {
        if (!hasUsableValue(JWT_PRIVATE_KEY, value, errors)) {
            return null;
        }
        try {
            return JwtKeyLoader.loadPrivateKey(value);
        } catch (IllegalArgumentException ex) {
            errors.add(JWT_PRIVATE_KEY + " 不是合法的 PKCS#8 PEM 私钥（解析失败）");
            return null;
        }
    }

    private static RSAPublicKey validatePublicKey(String value, List<String> errors) {
        if (!hasUsableValue(JWT_PUBLIC_KEY, value, errors)) {
            return null;
        }
        try {
            return JwtKeyLoader.loadPublicKey(value);
        } catch (IllegalArgumentException ex) {
            errors.add(JWT_PUBLIC_KEY + " 不是合法的 X.509 PEM 公钥（解析失败）");
            return null;
        }
    }

    /** 空值、未解析占位符与默认占位符统一视为不可用，并记录具体原因。 */
    private static boolean hasUsableValue(String propertyName, String value, List<String> errors) {
        if (isBlank(value) || isUnresolvedPlaceholder(value)) {
            errors.add(propertyName + " 不能为空或仍是未解析的占位符");
            return false;
        }
        if (isDefaultPlaceholder(value)) {
            errors.add(propertyName + " 仍是默认占位符");
            return false;
        }
        return true;
    }

    private static void validateJwtAudience(Environment environment, List<String> errors) {
        String audience = readRawValue(environment, JWT_AUDIENCE);
        if (isBlank(audience) || isUnresolvedPlaceholder(audience) || isDefaultPlaceholder(audience)) {
            errors.add(JWT_AUDIENCE + " 不能为空或仍是占位符");
        }
    }

    /**
     * 生产必须启用 Secure Cookie。
     *
     * <p>刷新令牌是长期凭证，一旦走明文 http 传输即可被同网段嗅探；
     * 允许用环境变量关闭等于把这条底线交给部署配置，因此在 prod 直接拒绝启动。</p>
     */
    private static void validateCookieSecure(Environment environment, List<String> errors) {
        Boolean isSecure = environment.getProperty("app.security.cookie.secure", Boolean.class, false);
        if (!Boolean.TRUE.equals(isSecure)) {
            errors.add("app.security.cookie.secure 必须为 true");
        }
    }

    private static void validateDatasourceUrl(Environment environment, List<String> errors) {
        String url = readRawValue(environment, "spring.datasource.url");
        if (isBlank(url) || isUnresolvedPlaceholder(url)) {
            errors.add("spring.datasource.url 不能为空或仍是未解析的占位符");
        }
    }

    private static void validateDatasourcePassword(Environment environment, List<String> errors) {
        String password = readRawValue(environment, "spring.datasource.password");
        if (isBlank(password)) {
            errors.add("spring.datasource.password 不能为空");
            return;
        }
        if (isUnresolvedPlaceholder(password)) {
            errors.add("spring.datasource.password 仍是未解析的占位符");
            return;
        }
        if (isDefaultPlaceholder(password)) {
            errors.add("spring.datasource.password 仍是默认占位符");
        }
    }

    /**
     * 启用模型运行时后必须配置非占位的服务间口令。
     *
     * <p>该口令用于 Agent 换取服务令牌、进而访问 {@code /internal/v1/**}；沿用
     * {@code .env.example} 的占位值上线，等于把内部接口暴露给任何读过仓库的人。</p>
     */
    private static void validateInternalAuthSecret(Environment environment, List<String> errors) {
        Boolean isRuntimeEnabled = environment.getProperty(MODEL_RUNTIME_ENABLED, Boolean.class, false);
        if (!Boolean.TRUE.equals(isRuntimeEnabled)) {
            return;
        }
        String secret = readRawValue(environment, INTERNAL_AUTH_CLIENT_SECRET);
        if (isBlank(secret) || isUnresolvedPlaceholder(secret) || isDefaultPlaceholder(secret)) {
            errors.add(INTERNAL_AUTH_CLIENT_SECRET + " 不能为空或仍是占位符");
            return;
        }
        if (secret.trim().length() < MIN_INTERNAL_SECRET_LENGTH) {
            errors.add(INTERNAL_AUTH_CLIENT_SECRET + " 长度必须不少于 " + MIN_INTERNAL_SECRET_LENGTH + " 个字符");
        }
    }

    private static String readRawValue(Environment environment, String key) {
        try {
            return environment.getProperty(key);
        } catch (IllegalArgumentException exception) {
            return UNRESOLVED_PLACEHOLDER;
        }
    }

    private static boolean isUnresolvedPlaceholder(String value) {
        return UNRESOLVED_PLACEHOLDER.equals(value) || (value.startsWith("${") && value.endsWith("}"));
    }

    private static boolean isDefaultPlaceholder(String value) {
        String normalized = value.toLowerCase(Locale.ROOT);
        return DEFAULT_PLACEHOLDER_WORDS.stream().anyMatch(word -> matchesPlaceholderWord(normalized, word));
    }

    /**
     * 词根完全相等，或词根后紧跟分隔符/数字时判定为占位符。
     * 例如 password123、change-me-please 命中；my-secret-2026 不命中。
     */
    private static boolean matchesPlaceholderWord(String normalized, String word) {
        if (normalized.equals(word)) {
            return true;
        }
        if (!normalized.startsWith(word) || normalized.length() == word.length()) {
            return false;
        }
        return !Character.isLetter(normalized.charAt(word.length()));
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
