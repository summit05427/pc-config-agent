package com.example.agent.identity;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

/**
 * 用户偏好接口集成测试：真实 PostgreSQL + 完整安全过滤器链。
 *
 * <p>必须连真实数据库：V5 迁移、{@code INSERT ... SELECT ... ON CONFLICT} 的 upsert
 * 语义与 {@code ::uuid} 参数转换都无法用内存实现等价验证。</p>
 */
@SpringBootTest(properties = "spring.flyway.enabled=true")
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Testcontainers
class UserPreferenceApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String PREFERENCES_PATH = "/api/v1/users/me/preferences";
    private static final String ADMIN_USERNAME = "admin";
    private static final String ADMIN_PASSWORD = "test-only-password";
    private static final String DEMO_USERNAME = "demo";
    private static final String DEMO_PASSWORD = "test-only-demo-password";

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:18-alpine");

    @DynamicPropertySource
    static void registerDatasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    private final MockMvc mockMvc;

    @Autowired
    UserPreferenceApiTests(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void getPreferences_shouldReturnDefaults_whenNothingSaved() throws Exception {
        mockMvc.perform(get(PREFERENCES_PATH).header(HttpHeaders.AUTHORIZATION,
                        bearerToken(DEMO_USERNAME, DEMO_PASSWORD)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.instructions").value(nullValue()))
                .andExpect(jsonPath("$.data.replyLanguage").value("auto"))
                .andExpect(jsonPath("$.data.responseStyle").value("balanced"))
                .andExpect(jsonPath("$.data.useHistory").value(true))
                // 未保存过时不伪造保存时间
                .andExpect(jsonPath("$.data.updatedAt").value(nullValue()));
    }

    @Test
    void updatePreferences_shouldPersistAndBeReadableBack() throws Exception {
        String token = bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD);

        mockMvc.perform(put(PREFERENCES_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"instructions":"回答尽量简短","replyLanguage":"zh-CN",
                                 "responseStyle":"concise","useHistory":false}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.instructions").value("回答尽量简短"))
                .andExpect(jsonPath("$.data.replyLanguage").value("zh-CN"))
                .andExpect(jsonPath("$.data.responseStyle").value("concise"))
                .andExpect(jsonPath("$.data.useHistory").value(false))
                .andExpect(jsonPath("$.data.updatedAt").isNotEmpty());

        mockMvc.perform(get(PREFERENCES_PATH).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.instructions").value("回答尽量简短"))
                .andExpect(jsonPath("$.data.replyLanguage").value("zh-CN"))
                .andExpect(jsonPath("$.data.responseStyle").value("concise"))
                .andExpect(jsonPath("$.data.useHistory").value(false));
    }

    @Test
    void updatePreferences_shouldRejectUnknownReplyLanguage() throws Exception {
        mockMvc.perform(put(PREFERENCES_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"instructions":null,"replyLanguage":"fr-FR","responseStyle":"balanced","useHistory":true}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001))
                .andExpect(jsonPath("$.data[0].field").value("replyLanguage"));
    }

    @Test
    void updatePreferences_shouldRejectInstructionsLongerThanLimit() throws Exception {
        String tooLongInstructions = "x".repeat(1001);

        mockMvc.perform(put(PREFERENCES_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken(ADMIN_USERNAME, ADMIN_PASSWORD))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"instructions":"%s","replyLanguage":"auto","responseStyle":"balanced","useHistory":true}
                                """.formatted(tooLongInstructions)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001))
                .andExpect(jsonPath("$.data[0].field").value("instructions"));
    }

    @Test
    void getPreferences_shouldReturnUnauthorized_whenTokenIsMissing() throws Exception {
        mockMvc.perform(get(PREFERENCES_PATH)).andExpect(status().isUnauthorized());
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
