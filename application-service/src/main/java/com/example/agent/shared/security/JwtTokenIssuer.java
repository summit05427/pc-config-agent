package com.example.agent.shared.security;

import com.example.agent.shared.config.AppSecurityProperties;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Component;

/**
 * 共享 JWT 签发器。
 *
 * <p>用户访问令牌与服务令牌使用同一套密钥、受众与 Header 约定，此前 identity 与 model
 * 各写一份组装逻辑，新增 claim 或轮换 {@code kid} 时容易只改一处。这里只收敛「如何签发」，
 * 不读取业务配置、不取时钟：TTL 与签发时刻由调用方决定。</p>
 */
@Component
@RequiredArgsConstructor
public class JwtTokenIssuer {

    private final JwtEncoder jwtEncoder;
    private final AppSecurityProperties properties;

    /**
     * 按给定输入签发令牌。
     *
     * @param spec     业务输入
     * @param issuedAt 签发时刻，由调用方提供以保持各自的时间语义
     * @return 令牌值与有效期秒数
     */
    public IssuedToken issue(TokenSpec spec, Instant issuedAt) {
        AppSecurityProperties.Jwt jwt = properties.getJwt();
        Instant expiresAt = issuedAt.plus(spec.ttl());
        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
                .issuer(jwt.getIssuer())
                .issuedAt(issuedAt)
                .expiresAt(expiresAt)
                .subject(spec.subject())
                .audience(List.of(jwt.getAudience()))
                .id(UUID.randomUUID().toString())
                .claim(TokenClaims.TOKEN_USE_CLAIM, spec.tokenUse());
        spec.extraClaims().forEach(claims::claim);
        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
                .keyId(jwt.getKid())
                .build();
        String token = jwtEncoder.encode(JwtEncoderParameters.from(header, claims.build())).getTokenValue();
        return new IssuedToken(token, Duration.between(issuedAt, expiresAt).toSeconds());
    }
}
