package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryRefreshSessionStore;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import jakarta.servlet.http.Cookie;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
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
 * 登录 / 刷新 / 退出 的 HTTP 流程测试。
 *
 * <p>覆盖 Cookie 属性、令牌轮换、非法来源与重复使用旧令牌。
 * 用户源与刷新会话都用内存实现，保证测试不依赖数据库。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({InMemoryUserDirectoryConfig.class, InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class})
class RefreshFlowTests {

    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final long ABSOLUTE_TTL_SECONDS = 30L * 24 * 60 * 60;
    private static final Pattern MAX_AGE_PATTERN = Pattern.compile("Max-Age=(\\d+)");
    private static final String LOGIN_BODY = """
            {"username":"admin","password":"test-only-password"}
            """;

    private final MockMvc mockMvc;

    private final InMemoryRefreshSessionStore refreshSessionStore;

    @Autowired
    RefreshFlowTests(MockMvc mockMvc, InMemoryRefreshSessionStore refreshSessionStore) {
        this.mockMvc = mockMvc;
        this.refreshSessionStore = refreshSessionStore;
    }

    @Test
    void login_shouldIssueAccessTokenAndHttpOnlyRefreshCookie() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(LOGIN_BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.accessToken").isNotEmpty())
                .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
                .andExpect(jsonPath("$.data.user.username").value("admin"))
                .andExpect(jsonPath("$.data.user.publicId").isNotEmpty())
                // 旧字段必须消失：刷新令牌只允许出现在 Cookie 里
                .andExpect(jsonPath("$.data.token").doesNotExist())
                .andReturn();

        String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);
        assertThat(setCookie)
                .contains("agent_refresh=")
                .contains("HttpOnly")
                .contains("SameSite=Strict")
                .contains("Path=/api/v1/auth");
        // Max-Age 由「绝对过期时间 - 当前时刻」换算，秒级截断最多少 1 秒，用区间而非精确值断言
        assertThat(extractMaxAgeSeconds(setCookie))
                .isBetween(ABSOLUTE_TTL_SECONDS - 1, ABSOLUTE_TTL_SECONDS);
    }

    @Test
    void refresh_shouldRotateCookieAndReturnUsableAccessToken() throws Exception {
        String oldToken = loginAndExtractRefreshToken();

        MvcResult refreshed = mockMvc.perform(post("/api/v1/auth/refresh")
                        .cookie(new Cookie("agent_refresh", oldToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.accessToken").isNotEmpty())
                .andReturn();

        String newToken = extractRefreshToken(refreshed.getResponse().getHeader(HttpHeaders.SET_COOKIE));
        assertThat(newToken).isNotEqualTo(oldToken);

        String accessToken = JsonPath.read(refreshed.getResponse().getContentAsString(), "$.data.accessToken");
        mockMvc.perform(get("/api/v1/auth/me").header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.username").value("admin"));
    }

    @Test
    void refresh_shouldReject_whenCookieIsMissing() throws Exception {
        mockMvc.perform(post("/api/v1/auth/refresh").header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(20001));
    }

    @Test
    void refresh_shouldReject_whenOriginIsUntrusted() throws Exception {
        String refreshToken = loginAndExtractRefreshToken();

        mockMvc.perform(post("/api/v1/auth/refresh")
                        .cookie(new Cookie("agent_refresh", refreshToken))
                        .header(HttpHeaders.ORIGIN, "http://evil.example"))
                // 未在白名单内的 Origin 在 CORS 阶段就被拒，响应体不含业务码
                .andExpect(status().isForbidden());

        // 完全不带 Origin 的请求能进到控制器，由来源校验返回统一的错误信封
        mockMvc.perform(post("/api/v1/auth/refresh")
                        .cookie(new Cookie("agent_refresh", refreshToken)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(20002));
    }

    @Test
    void refresh_shouldRejectReusedTokenWithoutRevokingFamily_whenWithinGrace() throws Exception {
        String oldToken = loginAndExtractRefreshToken();
        mockMvc.perform(post("/api/v1/auth/refresh")
                        .cookie(new Cookie("agent_refresh", oldToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk());

        // 旧令牌立刻再次出现：按并发冲突拒绝，不牵连整族
        mockMvc.perform(post("/api/v1/auth/refresh")
                        .cookie(new Cookie("agent_refresh", oldToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());

        assertThat(refreshSessionStore.findAll()).noneMatch(session -> "replay".equals(session.revokedReason()));
    }

    @Test
    void logout_shouldRevokeSessionAndClearCookie() throws Exception {
        String refreshToken = loginAndExtractRefreshToken();

        MvcResult result = mockMvc.perform(post("/api/v1/auth/logout")
                        .cookie(new Cookie("agent_refresh", refreshToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk())
                .andReturn();
        assertThat(result.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");

        mockMvc.perform(post("/api/v1/auth/refresh")
                        .cookie(new Cookie("agent_refresh", refreshToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logout_shouldSucceed_whenNotLoggedIn() throws Exception {
        mockMvc.perform(post("/api/v1/auth/logout").header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0));
    }

    private String loginAndExtractRefreshToken() throws Exception {
        MvcResult result = mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(LOGIN_BODY))
                .andExpect(status().isOk())
                .andReturn();
        return extractRefreshToken(result.getResponse().getHeader(HttpHeaders.SET_COOKIE));
    }

    /** 从 Set-Cookie 头里取出 Cookie 值；MockMvc 不会自动解析 ResponseCookie 为 Cookie 对象。 */
    private static String extractRefreshToken(String setCookieHeader) {
        assertThat(setCookieHeader).isNotNull();
        int nameEnd = setCookieHeader.indexOf('=');
        int valueEnd = setCookieHeader.indexOf(';');
        return setCookieHeader.substring(nameEnd + 1, valueEnd);
    }

    /** 取出 Max-Age 秒数，避免依赖字符串拼接顺序。 */
    private static long extractMaxAgeSeconds(String setCookieHeader) {
        Matcher matcher = MAX_AGE_PATTERN.matcher(setCookieHeader);
        assertThat(matcher.find()).isTrue();
        return Long.parseLong(matcher.group(1));
    }
}
