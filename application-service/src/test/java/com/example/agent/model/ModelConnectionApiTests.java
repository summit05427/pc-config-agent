package com.example.agent.model;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.model.infrastructure.GatewayCredentialProbe;
import com.example.agent.model.infrastructure.HostResolver;
import com.jayway.jsonpath.JsonPath;
import java.net.InetAddress;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * BYOK 连接接口集成测试：真实 PostgreSQL + 完整安全过滤器链。
 *
 * <p>重点验证三件事：任何响应都不回显明文与密文、连接归属不可越权、删除后不可再使用。</p>
 */
@SpringBootTest(properties = {
        "spring.flyway.enabled=true",
        "app.model.runtime-enabled=true",
        "app.model.byok-enabled=true",
        "app.model.credential.master-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "app.model.internal-auth.client-secret=test-only-internal-secret"
})
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Testcontainers
class ModelConnectionApiTests {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    private static final String LOGIN_PATH = "/api/v1/auth/login";

    private static final String CONNECTIONS_PATH = "/api/v1/model-connections";

    private static final String V2_CONNECTIONS_PATH = "/api/v2/model-connections";

    private static final String ADMIN_USERNAME = "admin";

    private static final String ADMIN_PASSWORD = "test-only-password";

    private static final String DEMO_USERNAME = "demo";

    private static final String DEMO_PASSWORD = "test-only-demo-password";

    private static final String SECRET = "sk-test-1234567890";

    private static final String ROTATED_SECRET = "sk-rotated-abcdef123456";

    private static final String MASKED_HINT = "sk-****7890";

    private static final String ROTATED_MASKED_HINT = "sk-****3456";

    private static final List<String> OWNED_USERNAMES = List.of(ADMIN_USERNAME, DEMO_USERNAME);

    private final MockMvc mockMvc;

    private final JdbcTemplate jdbcTemplate;

    /**
     * 接口测试不验证出站探测细节：桩掉探测与 DNS，保证用例不依赖外网与真实域名解析。
     */
    @MockitoBean
    private HostResolver hostResolver;

    @MockitoBean
    private GatewayCredentialProbe gatewayCredentialProbe;

    @Autowired
    ModelConnectionApiTests(MockMvc mockMvc, JdbcTemplate jdbcTemplate) {
        this.mockMvc = mockMvc;
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * 共享容器内按用户清理连接，保证各用例相互独立；凭证先删，满足外键顺序。
     */
    @BeforeEach
    void resetConnections() throws Exception {
        when(hostResolver.resolve(anyString()))
                .thenReturn(List.of(InetAddress.getByName("8.8.8.8")));
        // 默认按「Provider 拒绝凭证」处理：创建后的自动验证保持 UNVERIFIED
        when(gatewayCredentialProbe.probe(anyString(), anyString(), anyString()))
                .thenReturn(GatewayCredentialProbe.Outcome.REJECTED);
        jdbcTemplate.update("""
                DELETE FROM provider_credentials
                WHERE user_public_id IN (SELECT public_id FROM users WHERE username = ? OR username = ?)
                """, OWNED_USERNAMES.toArray());
        jdbcTemplate.update("""
                DELETE FROM provider_connections
                WHERE user_public_id IN (SELECT public_id FROM users WHERE username = ? OR username = ?)
                """, OWNED_USERNAMES.toArray());
    }

    @Test
    void create_shouldReturnMaskedCredentialAndNeverEchoPlaintext() throws Exception {
        mockMvc.perform(post(CONNECTIONS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("openai", null, SECRET)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.provider").value("openai"))
                // 未填地址就原样存空，由网关使用 Provider 官方默认地址
                .andExpect(jsonPath("$.data.baseUrl").value(""))
                .andExpect(jsonPath("$.data.status").value("ACTIVE"))
                .andExpect(jsonPath("$.data.credential.maskedHint").value(MASKED_HINT))
                .andExpect(jsonPath("$.data.credential.status").value("UNVERIFIED"))
                // 明文、密文、回读端点都不存在
                .andExpect(jsonPath("$.data.apiKey").doesNotExist())
                .andExpect(jsonPath("$.data.credential.ciphertext").doesNotExist())
                .andExpect(content().string(not(containsString(SECRET))));
    }

    @Test
    void create_shouldRejectDuplicateProviderConnection() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);

        createConnection(token, "openai", null, SECRET);

        mockMvc.perform(post(CONNECTIONS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("openai", null, SECRET)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(40212))
                .andExpect(jsonPath("$.errorType").value("connection_exists"));
    }

    @Test
    void create_shouldRejectUnsupportedProviderAndInvalidBaseUrl() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);

        mockMvc.perform(post(CONNECTIONS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("unknown", null, SECRET)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40211))
                .andExpect(jsonPath("$.errorType").value("provider_not_supported"));

        mockMvc.perform(post(CONNECTIONS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody("openai", "ftp://example.com", SECRET)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40214))
                .andExpect(jsonPath("$.errorType").value("base_url_invalid"));
    }

    @Test
    void verify_shouldReturnBadGatewayAndKeepUnverified_whenProviderIsUnreachable() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);
        // .invalid 是永远无法解析的顶级域；DNS 已在测试中桩为公网地址，探测再桩为不可用
        when(gatewayCredentialProbe.probe(anyString(), anyString(), anyString()))
                .thenReturn(GatewayCredentialProbe.Outcome.UNAVAILABLE);
        String connectionId = createConnection(token, "openai", "https://verify-probe.invalid/v1", SECRET);

        mockMvc.perform(post(CONNECTIONS_PATH + "/" + connectionId + "/verify")
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value(40217))
                .andExpect(jsonPath("$.errorType").value("credential_verify_failed"))
                .andExpect(content().string(not(containsString(SECRET))));

        // 上游不可达属于临时故障，不能把凭证写成永久失败
        mockMvc.perform(get(CONNECTIONS_PATH).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].credential.status").value("UNVERIFIED"))
                .andExpect(jsonPath("$.data[0].lastVerifiedAt").value(org.hamcrest.Matchers.nullValue()));
    }

    @Test
    void update_shouldRotateCredentialAndNeverEchoPlaintext() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);
        String connectionId = createConnection(token, "openai", null, SECRET);

        mockMvc.perform(put(CONNECTIONS_PATH + "/" + connectionId)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"apiKey\":\"" + ROTATED_SECRET + "\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.credential.maskedHint").value(ROTATED_MASKED_HINT))
                .andExpect(jsonPath("$.data.credential.status").value("UNVERIFIED"))
                .andExpect(content().string(not(containsString(ROTATED_SECRET))));
    }

    @Test
    void update_shouldRequireApiKey() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);
        String connectionId = createConnection(token, "openai", null, SECRET);

        mockMvc.perform(put(CONNECTIONS_PATH + "/" + connectionId)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"apiKey\":\"\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void delete_shouldMakeConnectionUnusable() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);
        String connectionId = createConnection(token, "openai", null, SECRET);

        mockMvc.perform(delete(CONNECTIONS_PATH + "/" + connectionId)
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0));

        mockMvc.perform(get(CONNECTIONS_PATH).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").isEmpty());

        // 删除后凭证已撤销，再校验必须按「不存在」处理
        mockMvc.perform(post(CONNECTIONS_PATH + "/" + connectionId + "/verify")
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40210));
    }

    @Test
    void connections_shouldNotBeAccessibleByAnotherUser() throws Exception {
        String adminToken = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);
        String demoToken = bearerToken(DEMO_USERNAME, DEMO_PASSWORD);
        String connectionId = createConnection(adminToken, "openai", null, SECRET);

        mockMvc.perform(post(CONNECTIONS_PATH + "/" + connectionId + "/verify")
                        .header(HttpHeaders.AUTHORIZATION, demoToken))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40210));

        mockMvc.perform(delete(CONNECTIONS_PATH + "/" + connectionId)
                        .header(HttpHeaders.AUTHORIZATION, demoToken))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40210));
    }

    @Test
    void list_shouldRequireAuthentication() throws Exception {
        mockMvc.perform(get(CONNECTIONS_PATH)).andExpect(status().isUnauthorized());
        mockMvc.perform(get(V2_CONNECTIONS_PATH)).andExpect(status().isUnauthorized());
    }

    @Test
    void listV2_shouldReturnPagedEnvelopeWithTotal() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);
        createConnection(token, "openai", null, SECRET);

        mockMvc.perform(get(V2_CONNECTIONS_PATH)
                        .param("page", "1")
                        .param("size", "10")
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.page").value(1))
                .andExpect(jsonPath("$.data.size").value(10))
                .andExpect(jsonPath("$.data.list[0].provider").value("openai"))
                .andExpect(content().string(not(containsString(SECRET))));
    }

    @Test
    void listV2_shouldRejectTooLargePageSize() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);

        mockMvc.perform(get(V2_CONNECTIONS_PATH)
                        .param("size", "101")
                        .header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    private String createConnection(String token, String providerCode, String baseUrl, String apiKey)
            throws Exception {
        MvcResult result = mockMvc.perform(post(CONNECTIONS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createBody(providerCode, baseUrl, apiKey)))
                .andExpect(status().isOk())
                .andReturn();
        return JsonPath.read(result.getResponse().getContentAsString(), "$.data.id");
    }

    private static String createBody(String providerCode, String baseUrl, String apiKey) {
        String baseUrlJson = baseUrl == null ? "null" : "\"" + baseUrl + "\"";
        return "{\"providerCode\":\"" + providerCode + "\",\"baseUrl\":" + baseUrlJson
                + ",\"apiKey\":\"" + apiKey + "\"}";
    }

    private String bearerToken(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return "Bearer " + accessToken;
    }
}
