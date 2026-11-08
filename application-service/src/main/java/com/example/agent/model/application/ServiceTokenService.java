package com.example.agent.model.application;

import com.example.agent.model.domain.ModelErrorCode;
import com.example.agent.shared.config.ModelRuntimeProperties;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.security.IssuedToken;
import com.example.agent.shared.security.JwtTokenIssuer;
import com.example.agent.shared.security.TokenClaims;
import com.example.agent.shared.security.TokenSpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 服务令牌签发。
 *
 * <p>Agent 用 {@code client_credentials} 换取短生命周期令牌，令牌复用现有 RS256 密钥与受众，
 * 但 {@code token_use=service} 且只带 {@code scope}，由 {@code TokenUseFilter} 保证它无法
 * 调用用户接口；用户身份另行通过 {@code X-User-Token} 传入。签发机制由
 * {@link JwtTokenIssuer} 统一实现。</p>
 */
@Service
@RequiredArgsConstructor
public class ServiceTokenService {

    /** 读取模型目录、创建与读取运行时任务。 */
    public static final String SCOPE_MODEL_RUNTIME_READ = "model-runtime:read";

    /** 上报使用明细。 */
    public static final String SCOPE_MODEL_USAGE_WRITE = "model-usage:write";

    private static final List<String> SERVICE_SCOPES =
            List.of(SCOPE_MODEL_RUNTIME_READ, SCOPE_MODEL_USAGE_WRITE);

    private final JwtTokenIssuer jwtTokenIssuer;
    private final ModelRuntimeProperties modelProperties;
    private final ModelRuntimeGuard runtimeGuard;
    private final Clock modelRuntimeUtcClock;

    /**
     * 校验 client 凭据并签发服务令牌。
     *
     * @param clientId     调用方标识
     * @param clientSecret 调用方密钥，仅来自环境变量
     * @return 令牌与有效期秒数
     * @throws BusinessException 运行时未启用时 404；凭据不匹配时 401
     */
    public IssuedToken issue(String clientId, String clientSecret) {
        runtimeGuard.requireEnabled();
        ModelRuntimeProperties.InternalAuth internalAuth = modelProperties.getInternalAuth();
        if (!Objects.equals(internalAuth.getClientId(), clientId)
                || !isSecretMatched(internalAuth.getClientSecret(), clientSecret)) {
            throw new BusinessException(ModelErrorCode.SERVICE_TOKEN_INVALID);
        }
        return jwtTokenIssuer.issue(new TokenSpec(
                clientId,
                TokenClaims.TOKEN_USE_SERVICE,
                internalAuth.getTokenTtl(),
                Map.of(TokenClaims.SCOPE_CLAIM, SERVICE_SCOPES)), modelRuntimeUtcClock.instant());
    }

    /**
     * 定长比较，避免按字符逐位短路带来的时间侧信道。
     */
    private boolean isSecretMatched(String expected, String actual) {
        if (expected == null || actual == null) {
            return false;
        }
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8), actual.getBytes(StandardCharsets.UTF_8));
    }
}
