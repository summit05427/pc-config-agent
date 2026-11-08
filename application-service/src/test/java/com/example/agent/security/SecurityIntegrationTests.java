package com.example.agent.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.config.AppSecurityProperties;
import com.example.agent.shared.web.RequestIdFilter;
import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 认证鉴权集成测试：真实走完整安全过滤器链。
 *
 * <p>测试接口通过 {@link TestEndpoints} 临时注册，避免把演示接口写进生产代码。
 * 用户源由 {@link InMemoryUserDirectoryConfig} 提供，引导账号由 {@code BootstrapUserSeeder} 播种。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({
        InMemoryUserDirectoryConfig.class,
        InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class,
        SecurityIntegrationTests.TestEndpoints.class
})
class SecurityIntegrationTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String ME_PATH = "/api/v1/auth/me";
    private static final String SECURE_PATH = "/api/v1/test/secure";
    private static final String ADMIN_PATH = "/api/v1/admin/test";
    private static final String VALID_USERNAME = "admin";
    private static final String VALID_PASSWORD = "test-only-password";
    private static final String DEMO_USERNAME = "demo";
    private static final String DEMO_PASSWORD = "test-only-demo-password";
    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final String CLAIM_TOKEN_USE = "token_use";

    private final MockMvc mockMvc;

    private final JwtDecoder jwtDecoder;

    private final JwtEncoder jwtEncoder;

    private final AppSecurityProperties properties;

    @Autowired
    SecurityIntegrationTests(MockMvc mockMvc,
            JwtDecoder jwtDecoder,
            JwtEncoder jwtEncoder,
            AppSecurityProperties properties) {
        this.mockMvc = mockMvc;
        this.jwtDecoder = jwtDecoder;
        this.jwtEncoder = jwtEncoder;
        this.properties = properties;
    }

    @Test
    void login_shouldReturnTokenWithRs256AndPublicSubject_whenCredentialsAreValid() throws Exception {
        String token = loginAndGetToken(VALID_USERNAME, VALID_PASSWORD);
        Jwt decoded = jwtDecoder.decode(token);

        assertThat(decoded.getHeaders()).containsEntry("alg", "RS256");
        assertThat(decoded.getHeaders()).containsEntry("kid", properties.getJwt().getKid());
        assertThat(decoded.getSubject()).isNotEqualTo(VALID_USERNAME);
        // 主体必须是合法 UUID：内部 BIGINT 主键与登录名都不允许出现在令牌里
        assertThat(UUID.fromString(decoded.getSubject())).isNotNull();
        assertThat(decoded.getAudience()).containsExactly(properties.getJwt().getAudience());
        assertThat(decoded.getClaimAsString(CLAIM_TOKEN_USE)).isEqualTo("access");
        assertThat(decoded.getId()).isNotBlank();
        assertThat(decoded.getClaimAsStringList("roles")).containsExactly("ADMIN");
    }

    @Test
    void login_shouldReturnBearerEnvelope() throws Exception {
        mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(VALID_USERNAME, VALID_PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiResponse.SUCCESS_CODE))
                .andExpect(jsonPath("$.data.accessToken").isNotEmpty())
                .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.data.expiresIn").value(600))
                // 登录响应同时带回用户信息，前端无需再额外请求一次 /me
                .andExpect(jsonPath("$.data.user.username").value(VALID_USERNAME))
                .andExpect(jsonPath("$.data.user.roles[0]").value("ADMIN"));
    }

    @Test
    void login_shouldReturnUnauthorized_whenPasswordIsWrong() throws Exception {
        mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(VALID_USERNAME, "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001))
                .andExpect(jsonPath("$.requestId").isNotEmpty());
    }

    @Test
    void login_shouldReturnUnauthorized_whenUsernameDoesNotExist() throws Exception {
        mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody("missing-user", VALID_PASSWORD)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001));
    }

    @Test
    void me_shouldReturnPublicIdAndUsername_whenTokenIsValid() throws Exception {
        String token = loginAndGetToken(VALID_USERNAME, VALID_PASSWORD);

        mockMvc.perform(get(ME_PATH).header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiResponse.SUCCESS_CODE))
                .andExpect(jsonPath("$.data.publicId").value(jwtDecoder.decode(token).getSubject()))
                .andExpect(jsonPath("$.data.username").value(VALID_USERNAME))
                .andExpect(jsonPath("$.data.roles[0]").value("ADMIN"));
    }

    @Test
    void me_shouldReturnUnauthorized_whenTokenMissing() throws Exception {
        mockMvc.perform(get(ME_PATH))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001));
    }

    @Test
    void protectedEndpoint_shouldReturnUnauthorized_whenTokenExpired() throws Exception {
        // 签发时间与过期时间都落在过去，避免构造器拒绝 expiresAt 早于 issuedAt
        Instant pastIssuedAt = Instant.now().minusSeconds(600);
        String expiredToken = signToken(buildClaims()
                .issuedAt(pastIssuedAt)
                .expiresAt(pastIssuedAt.plusSeconds(60))
                .build());
        assertUnauthorized(SECURE_PATH, expiredToken);
    }

    @Test
    void protectedEndpoint_shouldReturnUnauthorized_whenAudienceMismatch() throws Exception {
        String wrongAudienceToken = signToken(buildClaims().audience(List.of("other-client")).build());
        assertUnauthorized(SECURE_PATH, wrongAudienceToken);
    }

    @Test
    void protectedEndpoint_shouldReturnUnauthorized_whenSignatureComesFromAnotherKey() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair foreignKeyPair = generator.generateKeyPair();
        RSAKey foreignKey = new RSAKey.Builder((RSAPublicKey) foreignKeyPair.getPublic())
                .privateKey(foreignKeyPair.getPrivate())
                // 故意复用同一个 kid：验证拒绝来自签名本身，而不是 kid 选择
                .keyID(properties.getJwt().getKid())
                .algorithm(JWSAlgorithm.RS256)
                .build();
        JwtEncoder foreignEncoder = new NimbusJwtEncoder(new ImmutableJWKSet<>(new JWKSet(foreignKey)));
        String foreignToken = foreignEncoder.encode(JwtEncoderParameters.from(
                JwsHeader.with(SignatureAlgorithm.RS256).keyId(properties.getJwt().getKid()).build(),
                buildClaims().build())).getTokenValue();
        assertUnauthorized(SECURE_PATH, foreignToken);
    }

    @Test
    void protectedEndpoint_shouldReturnUnauthorized_whenTokenMissing() throws Exception {
        MvcResult result = mockMvc.perform(get(SECURE_PATH))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001))
                .andExpect(jsonPath("$.requestId").isNotEmpty())
                .andExpect(header().exists(RequestIdFilter.REQUEST_ID_HEADER))
                .andReturn();

        String bodyRequestId = JsonPath.read(result.getResponse().getContentAsString(), "$.requestId");
        assertThat(bodyRequestId).isEqualTo(result.getResponse().getHeader(RequestIdFilter.REQUEST_ID_HEADER));
    }

    @Test
    void protectedEndpoint_shouldReturnUnauthorized_whenTokenInvalid() throws Exception {
        mockMvc.perform(get(SECURE_PATH).header("Authorization", "Bearer invalid.token.value"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001));
    }

    @Test
    void protectedEndpoint_shouldReturnOk_whenTokenValid() throws Exception {
        mockMvc.perform(get(SECURE_PATH).header("Authorization", "Bearer " + loginAndGetToken(VALID_USERNAME, VALID_PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ApiResponse.SUCCESS_CODE))
                .andExpect(jsonPath("$.data").value("ok"));
    }

    @Test
    void adminEndpoint_shouldReturnOk_whenUserHasAdminRole() throws Exception {
        mockMvc.perform(get(ADMIN_PATH).header("Authorization", "Bearer " + loginAndGetToken(VALID_USERNAME, VALID_PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").value("admin ok"));
    }

    @Test
    void adminEndpoint_shouldReturnForbidden_whenUserLacksAdminRole() throws Exception {
        String demoToken = loginAndGetToken(DEMO_USERNAME, DEMO_PASSWORD);

        mockMvc.perform(get(ADMIN_PATH).header("Authorization", "Bearer " + demoToken))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(20002))
                .andExpect(jsonPath("$.requestId").isNotEmpty());
    }

    @Test
    void apiDocs_shouldBeAccessible_whenAnonymous() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.openapi").exists())
                .andExpect(jsonPath("$.components.securitySchemes.bearerAuth").exists())
                .andExpect(jsonPath("$.paths['/api/v1/auth/login']").exists());
    }

    @Test
    void corsPreflight_shouldReturnOk_whenOriginIsAllowed() throws Exception {
        mockMvc.perform(options(SECURE_PATH)
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN));
    }

    private void assertUnauthorized(String path, String token) throws Exception {
        mockMvc.perform(get(path).header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001));
    }

    /** 构造与正式签发一致、但允许覆盖过期时间与受众的 Claims。 */
    private JwtClaimsSet.Builder buildClaims() {
        Instant issuedAt = Instant.now();
        return JwtClaimsSet.builder()
                .issuer(properties.getJwt().getIssuer())
                .issuedAt(issuedAt)
                .expiresAt(issuedAt.plusSeconds(600))
                .subject(UUID.randomUUID().toString())
                .audience(List.of(properties.getJwt().getAudience()))
                .id(UUID.randomUUID().toString())
                .claim("roles", List.of("ADMIN"))
                .claim(CLAIM_TOKEN_USE, "access");
    }

    private String signToken(JwtClaimsSet claims) {
        return jwtEncoder.encode(JwtEncoderParameters.from(
                JwsHeader.with(SignatureAlgorithm.RS256).keyId(properties.getJwt().getKid()).build(),
                claims)).getTokenValue();
    }

    private String loginAndGetToken(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, password)))
                .andExpect(status().isOk())
                .andReturn();
        return JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
    }

    private String loginBody(String username, String password) {
        return "{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}";
    }

    /**
     * 显式注册测试专用接口。
     *
     * <p>控制器类不能声明为 {@code TestEndpoints} 的成员类：{@code @Import} 会把配置类的
     * 成员类再次注册为配置候选，与 {@code @Bean} 一起造成映射重复（Ambiguous mapping）。</p>
     */
    @TestConfiguration
    static class TestEndpoints {

        @Bean
        TestSecurityController testSecurityController() {
            return new TestSecurityController();
        }
    }

    @RestController
    static class TestSecurityController {

        @GetMapping(SECURE_PATH)
        ApiResponse<String> secure() {
            return ApiResponse.success("ok");
        }

        @GetMapping(ADMIN_PATH)
        ApiResponse<String> admin() {
            return ApiResponse.success("admin ok");
        }
    }
}
