package com.example.agent.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.agent.shared.config.AppSecurityProperties;
import com.example.agent.shared.security.IssuedToken;
import com.example.agent.shared.security.JwtTokenIssuer;
import com.example.agent.shared.security.TokenClaims;
import com.example.agent.shared.security.TokenSpec;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

/**
 * 共享签发器：用户令牌与服务令牌都应带齐同一套基础 claims，附加 claim 原样写入。
 */
class JwtTokenIssuerTests {

    private static final String KID = "test-kid";
    private static final String ISSUER = "agent-application-service";
    private static final String AUDIENCE = "agent-clients";
    private static final RSAKey RSA_KEY;

    static {
        try {
            RSA_KEY = new RSAKeyGenerator(2048).keyID(KID).generate();
        } catch (Exception ex) {
            throw new IllegalStateException("测试密钥生成失败", ex);
        }
    }

    private JwtTokenIssuer issuer;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        AppSecurityProperties properties = new AppSecurityProperties();
        AppSecurityProperties.Jwt jwt = properties.getJwt();
        jwt.setKid(KID);
        jwt.setIssuer(ISSUER);
        jwt.setAudience(AUDIENCE);
        issuer = new JwtTokenIssuer(
                new NimbusJwtEncoder(new ImmutableJWKSet<>(new JWKSet(RSA_KEY))), properties);
        decoder = NimbusJwtDecoder.withPublicKey(RSA_KEY.toRSAPublicKey()).build();
    }

    @Test
    void serviceTokenShouldCarrySharedClaimsAndScope() {
        Instant issuedAt = Instant.now();
        IssuedToken issued = issuer.issue(new TokenSpec(
                "agent-service", TokenClaims.TOKEN_USE_SERVICE, Duration.ofMinutes(5),
                Map.of(TokenClaims.SCOPE_CLAIM, List.of("model-runtime:read"))), issuedAt);

        assertThat(issued.expiresInSeconds()).isEqualTo(300);
        Jwt decoded = decoder.decode(issued.value());
        assertThat(decoded.getSubject()).isEqualTo("agent-service");
        assertThat(decoded.getClaimAsString("iss")).isEqualTo(ISSUER);
        assertThat(decoded.getAudience()).containsExactly(AUDIENCE);
        assertThat(decoded.getClaimAsString(TokenClaims.TOKEN_USE_CLAIM))
                .isEqualTo(TokenClaims.TOKEN_USE_SERVICE);
        assertThat(decoded.getClaimAsStringList(TokenClaims.SCOPE_CLAIM))
                .containsExactly("model-runtime:read");
        assertThat(decoded.getId()).isNotBlank();
        assertThat(decoded.getExpiresAt())
                .isEqualTo(issuedAt.truncatedTo(ChronoUnit.SECONDS).plus(Duration.ofMinutes(5)));
        assertThat(decoded.getHeaders()).containsEntry("kid", KID);
    }

    @Test
    void accessTokenShouldKeepBusinessClaims() {
        Instant issuedAt = Instant.now();
        IssuedToken issued = issuer.issue(new TokenSpec(
                "user-public-id", TokenClaims.TOKEN_USE_ACCESS, Duration.ofMinutes(10),
                Map.of("roles", List.of("ROLE_USER"), "sid", "family-id")), issuedAt);

        Jwt decoded = decoder.decode(issued.value());
        assertThat(decoded.getClaimAsString(TokenClaims.TOKEN_USE_CLAIM))
                .isEqualTo(TokenClaims.TOKEN_USE_ACCESS);
        assertThat(decoded.getClaimAsStringList("roles")).containsExactly("ROLE_USER");
        assertThat(decoded.getClaimAsString("sid")).isEqualTo("family-id");
        assertThat(issued.expiresInSeconds()).isEqualTo(600);
    }
}
