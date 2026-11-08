package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.identity.application.AuthAuditEntry;
import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.AuthAuditEvent;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.support.InMemoryAuthAuditLog;
import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import jakarta.servlet.http.Cookie;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 认证审计写入的集成测试。
 *
 * <p>用户源、刷新会话与审计写入全部使用内存实现，只验证「业务动作是否产生
 * 正确的审计事件与定位信息」。宽限期置 0，让旧刷新令牌的第二次使用
 * 立即落入真实重放分支，便于覆盖 {@code refresh_replay}。</p>
 *
 * <p>{@code user_disabled} 与 {@code role_changed} 由管理端接口产生，
 * 接口级覆盖见 {@code AdminUserApiTests}。</p>
 */
@SpringBootTest(properties = "app.security.refresh.rotation-grace=0s")
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({
        InMemoryUserDirectoryConfig.class,
        InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class
})
class AuthAuditLogTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String REFRESH_PATH = "/api/v1/auth/refresh";
    private static final String LOGOUT_PATH = "/api/v1/auth/logout";
    private static final String LOGOUT_ALL_PATH = "/api/v1/auth/logout-all";
    private static final String PASSWORD_PATH = "/api/v1/users/me/password";
    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final String CLIENT_IP = "10.30.40.50";
    private static final String USER_AGENT = "audit-test-agent";

    private final MockMvc mockMvc;
    private final UserDirectory userDirectory;
    private final PasswordEncoder passwordEncoder;
    private final InMemoryAuthAuditLog auditLog;

    @Autowired
    AuthAuditLogTests(
            MockMvc mockMvc,
            UserDirectory userDirectory,
            PasswordEncoder passwordEncoder,
            InMemoryAuthAuditLog auditLog) {
        this.mockMvc = mockMvc;
        this.userDirectory = userDirectory;
        this.passwordEncoder = passwordEncoder;
        this.auditLog = auditLog;
    }

    @BeforeEach
    void clearAuditLog() {
        auditLog.clear();
    }

    @Test
    void loginSuccess_shouldAppendEventWithClientMetadata() throws Exception {
        login("admin", "test-only-password");

        AuthAuditEntry entry = single(AuthAuditEvent.LOGIN_SUCCESS);
        assertThat(entry.username()).isEqualTo("admin");
        assertThat(entry.publicId()).isNotBlank();
        assertThat(entry.ip()).isEqualTo(CLIENT_IP);
        assertThat(entry.userAgent()).isEqualTo(USER_AGENT);
        assertThat(entry.requestId()).isNotBlank();
    }

    @Test
    void loginFailure_shouldAppendEventWithoutPublicId() throws Exception {
        mockMvc.perform(post(LOGIN_PATH)
                        .with(request -> {
                            request.setRemoteAddr(CLIENT_IP);
                            return request;
                        })
                        .header(HttpHeaders.USER_AGENT, USER_AGENT)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"admin","password":"wrong-password"}
                                """))
                .andExpect(status().isUnauthorized());

        AuthAuditEntry entry = single(AuthAuditEvent.LOGIN_FAILURE);
        assertThat(entry.username()).isEqualTo("admin");
        assertThat(entry.publicId()).isNull();
        assertThat(entry.ip()).isEqualTo(CLIENT_IP);
    }

    @Test
    void logout_shouldAppendLogoutEvent() throws Exception {
        String refreshToken = loginAndExtractRefreshToken("admin", "test-only-password");

        mockMvc.perform(post(LOGOUT_PATH)
                        .cookie(new Cookie("agent_refresh", refreshToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk());

        AuthAuditEntry entry = single(AuthAuditEvent.LOGOUT);
        assertThat(entry.username()).isEqualTo("admin");
        assertThat(entry.publicId()).isNotBlank();
    }

    @Test
    void logoutAll_shouldAppendLogoutAllEvent() throws Exception {
        String accessToken = loginAndExtractAccessToken("admin", "test-only-password");

        mockMvc.perform(post(LOGOUT_ALL_PATH).header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken))
                .andExpect(status().isOk());

        AuthAuditEntry entry = single(AuthAuditEvent.LOGOUT_ALL);
        assertThat(entry.username()).isEqualTo("admin");
        assertThat(entry.publicId()).isNotBlank();
    }

    @Test
    void passwordChange_shouldAppendPasswordChangeEvent() throws Exception {
        UserAccount account = createUser("audit-password-user", "old-password");
        String accessToken = loginAndExtractAccessToken(account.username(), "old-password");

        mockMvc.perform(put(PASSWORD_PATH)
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"old-password","newPassword":"new-password"}
                                """))
                .andExpect(status().isOk());

        AuthAuditEntry entry = single(AuthAuditEvent.PASSWORD_CHANGE);
        assertThat(entry.username()).isEqualTo(account.username());
        assertThat(entry.publicId()).isEqualTo(account.publicId());
    }

    @Test
    void reusedRefreshToken_shouldAppendReplayEvent() throws Exception {
        String refreshToken = loginAndExtractRefreshToken("admin", "test-only-password");
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie("agent_refresh", refreshToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk());

        // 宽限期为 0：旧令牌第二次出现立即判定为重放
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie("agent_refresh", refreshToken))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());

        AuthAuditEntry entry = single(AuthAuditEvent.REFRESH_REPLAY);
        assertThat(entry.username()).isEqualTo("admin");
        assertThat(entry.publicId()).isNotBlank();
    }

    private UserAccount createUser(String username, String rawPassword) {
        return userDirectory.create(username, passwordEncoder.encode(rawPassword), List.of("USER"));
    }

    private String loginAndExtractRefreshToken(String username, String password) throws Exception {
        MvcResult result = login(username, password);
        String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);
        assertThat(setCookie).isNotNull();
        return setCookie.substring(setCookie.indexOf('=') + 1, setCookie.indexOf(';'));
    }

    private String loginAndExtractAccessToken(String username, String password) throws Exception {
        MvcResult result = login(username, password);
        return JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
    }

    private MvcResult login(String username, String password) throws Exception {
        return mockMvc.perform(post(LOGIN_PATH)
                        .with(request -> {
                            request.setRemoteAddr(CLIENT_IP);
                            return request;
                        })
                        .header(HttpHeaders.USER_AGENT, USER_AGENT)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"%s"}
                                """.formatted(username, password)))
                .andExpect(status().isOk())
                .andReturn();
    }

    private AuthAuditEntry single(AuthAuditEvent event) {
        return auditLog.findAll().stream()
                .filter(entry -> entry.event() == event)
                .findFirst()
                .orElseThrow(() -> new AssertionError("未记录审计事件 " + event.value()));
    }
}
