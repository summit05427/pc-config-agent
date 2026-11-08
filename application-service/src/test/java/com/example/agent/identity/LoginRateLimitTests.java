package com.example.agent.identity;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/**
 * 登录限流的 HTTP 行为。
 *
 * <p>限流是进程内单例，测试之间会用不同 IP 隔离计数；
 * 这里只验证对外可见的 429 语义与成功登录清零，窗口过期由单元测试覆盖。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({InMemoryUserDirectoryConfig.class, InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class})
class LoginRateLimitTests {

    private static final int MAX_ATTEMPTS = 5;

    private static final String WRONG_PASSWORD_BODY = """
            {"username":"admin","password":"wrong-password"}
            """;

    private static final String CORRECT_BODY = """
            {"username":"admin","password":"test-only-password"}
            """;

    private final MockMvc mockMvc;

    @Autowired
    LoginRateLimitTests(MockMvc mockMvc) {
        this.mockMvc = mockMvc;
    }

    @Test
    void sixthFailedLogin_shouldReturnTooManyRequests() throws Exception {
        String clientIp = "10.20.30.40";

        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            mockMvc.perform(login(WRONG_PASSWORD_BODY, clientIp))
                    .andExpect(status().isUnauthorized());
        }

        mockMvc.perform(login(WRONG_PASSWORD_BODY, clientIp))
                .andExpect(status().isTooManyRequests())
                .andExpect(jsonPath("$.code").value(10007));
    }

    @Test
    void successfulLogin_shouldResetFailureCounter() throws Exception {
        String clientIp = "10.20.30.41";

        for (int attempt = 0; attempt < 3; attempt++) {
            mockMvc.perform(login(WRONG_PASSWORD_BODY, clientIp))
                    .andExpect(status().isUnauthorized());
        }
        mockMvc.perform(login(CORRECT_BODY, clientIp)).andExpect(status().isOk());

        // 成功登录已清零：随后的 5 次失败仍逐次返回 401，而不是立刻被拦
        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            mockMvc.perform(login(WRONG_PASSWORD_BODY, clientIp))
                    .andExpect(status().isUnauthorized());
        }
        mockMvc.perform(login(WRONG_PASSWORD_BODY, clientIp))
                .andExpect(status().isTooManyRequests());
    }

    @Test
    void otherClientIp_shouldNotBeBlocked() throws Exception {
        String blockedIp = "10.20.30.42";
        String otherIp = "10.20.30.43";

        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            mockMvc.perform(login(WRONG_PASSWORD_BODY, blockedIp))
                    .andExpect(status().isUnauthorized());
        }
        mockMvc.perform(login(WRONG_PASSWORD_BODY, blockedIp))
                .andExpect(status().isTooManyRequests());

        mockMvc.perform(login(WRONG_PASSWORD_BODY, otherIp))
                .andExpect(status().isUnauthorized());
    }

    private static MockHttpServletRequestBuilder login(String body, String clientIp) {
        return post("/api/v1/auth/login")
                .with(request -> {
                    request.setRemoteAddr(clientIp);
                    return request;
                })
                .contentType(MediaType.APPLICATION_JSON)
                .content(body);
    }
}
