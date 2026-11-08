package com.example.agent.identity;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 个人资料接口集成测试：走完整安全过滤器链，用户源为内存实现。
 *
 * <p>覆盖成功、参数非法、未认证三种分支；用户不存在分支由
 * {@code UserProfileServiceTests} 用 Mockito 覆盖，避免在共享容器里删用户。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({InMemoryUserDirectoryConfig.class, InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class})
class UserProfileApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String PROFILE_PATH = "/api/v1/users/me/profile";
    private static final String ADMIN_USERNAME = "admin";
    private static final String ADMIN_PASSWORD = "test-only-password";

    private final MockMvc mockMvc;

    @Autowired
    UserProfileApiTests(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void getProfile_shouldReturnPublicFieldsWithoutInternalId() throws Exception {
        mockMvc.perform(get(PROFILE_PATH).header(HttpHeaders.AUTHORIZATION, bearerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.username").value(ADMIN_USERNAME))
                .andExpect(jsonPath("$.data.roles[0]").value("ADMIN"))
                .andExpect(jsonPath("$.data.status").value("ACTIVE"))
                // 内部自增主键与口令摘要绝不能出现在响应里
                .andExpect(jsonPath("$.data.id").doesNotExist())
                .andExpect(jsonPath("$.data.passwordHash").doesNotExist());
    }

    @Test
    void updateProfile_shouldPersistAndBeReadableBack() throws Exception {
        String token = bearerToken();

        mockMvc.perform(put(PROFILE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"displayName":"运营管理员","email":"admin@example.com","bio":"负责后台运营"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.displayName").value("运营管理员"))
                .andExpect(jsonPath("$.data.email").value("admin@example.com"));

        mockMvc.perform(get(PROFILE_PATH).header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.displayName").value("运营管理员"))
                .andExpect(jsonPath("$.data.bio").value("负责后台运营"));
    }

    @Test
    void updateProfile_shouldTreatBlankEmailAndBioAsUnset() throws Exception {
        mockMvc.perform(put(PROFILE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"displayName":" 运营管理员 ","email":"   ","bio":"   "}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.displayName").value("运营管理员"))
                // 纯空白按「未设置」处理，不能落成空串（email 有唯一约束）
                .andExpect(jsonPath("$.data.email").value(nullValue()))
                .andExpect(jsonPath("$.data.bio").value(nullValue()));
    }

    @Test
    void updateProfile_shouldRejectBlankDisplayName() throws Exception {
        mockMvc.perform(put(PROFILE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"displayName":"   ","email":null,"bio":null}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void updateProfile_shouldRejectMalformedEmail() throws Exception {
        mockMvc.perform(put(PROFILE_PATH)
                        .header(HttpHeaders.AUTHORIZATION, bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"displayName":"运营管理员","email":"not-an-email","bio":null}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void getProfile_shouldReturnUnauthorized_whenAccessTokenIsMissing() throws Exception {
        mockMvc.perform(get(PROFILE_PATH)).andExpect(status().isUnauthorized());
    }

    private String bearerToken() throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + ADMIN_USERNAME + "\",\"password\":\"" + ADMIN_PASSWORD + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return "Bearer " + accessToken;
    }
}
