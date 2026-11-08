package com.example.agent.identity.infrastructure;

import com.example.agent.identity.domain.AuthenticatedUser;
import com.example.agent.shared.config.AppSecurityProperties;
import com.example.agent.shared.security.IssuedToken;
import com.example.agent.shared.security.JwtTokenIssuer;
import com.example.agent.shared.security.TokenClaims;
import com.example.agent.shared.security.TokenSpec;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

/**
 * 用户访问令牌签发服务。
 *
 * <p>只签发访问令牌，不提供刷新令牌。令牌主体使用 {@code publicId} 而不是内部
 * 自增主键或登录名：前者不可对外枚举，后者会随改名漂移。Header 携带
 * {@code kid} 的约定统一由 {@link JwtTokenIssuer} 负责。</p>
 */
@Service
@RequiredArgsConstructor
public class JwtTokenService {

    /**
     * 会话标识 claim，值为签发时所在 {@code refresh_sessions.family_id}。
     *
     * <p>只用于设备列表标记「当前会话」，不参与任何鉴权判断；Agent 验签只
     * 校验固定 claims，多出的该字段会被忽略。</p>
     */
    public static final String SESSION_CLAIM = "sid";

    private static final String ROLES_CLAIM = "roles";

    private final JwtTokenIssuer jwtTokenIssuer;
    private final AppSecurityProperties properties;

    /**
     * 为已认证用户签发访问令牌。
     *
     * @param user     认证主体，提供公开 ID 与业务角色
     * @param familyId 签发时所在刷新令牌族，写入 {@code sid} claim
     * @return 令牌值与有效期秒数
     */
    public IssuedToken issue(AuthenticatedUser user, UUID familyId) {
        return jwtTokenIssuer.issue(new TokenSpec(
                user.publicId(),
                TokenClaims.TOKEN_USE_ACCESS,
                properties.getJwt().getAccessTokenTtl(),
                Map.of(ROLES_CLAIM, user.roles(), SESSION_CLAIM, familyId.toString())), Instant.now());
    }
}
