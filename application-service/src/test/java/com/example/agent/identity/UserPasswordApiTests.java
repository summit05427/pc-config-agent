package com.example.agent.identity;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import jakarta.servlet.http.Cookie;
import java.util.List;
import java.util.UUID;
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
 * 修改口令接口集成测试：走完整过滤器链，用户源与会话仓储均为内存实现。
 *
 * <p>每个用例都新建独立用户，避免改密污染同上下文里其他用例依赖的 admin 账号。
 * 覆盖成功、旧口令错误、新旧相同、参数非法与未认证五种分支。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({InMemoryUserDirectoryConfig.class, InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class})
class UserPasswordApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String REFRESH_PATH = "/api/v1/auth/refresh";
    private static final String PASSWORD_PATH = "/api/v1/users/me/password";
    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final String CURRENT_PASSWORD = "old-password";

    private final MockMvc mockMvc;

    private final UserDirectory userDirectory;

    private final PasswordEncoder passwordEncoder;

    @Autowired
    UserPasswordApiTests(MockMvc mockMvc, UserDirectory userDirectory, PasswordEncoder passwordEncoder) {
        this.mockMvc = mockMvc;
        this.userDirectory = userDirectory;
        this.passwordEncoder = passwordEncoder;
    }

    @Test
    void changePassword_shouldKeepCurrentDeviceAndRevokeOthers() throws Exception {
        UserAccount account = createUser();
        LoginResult currentDevice = login(account.username(), CURRENT_PASSWORD);
        LoginResult otherDevice = login(account.username(), CURRENT_PASSWORD);

        mockMvc.perform(put(PASSWORD_PATH)
                        .header(HttpHeaders.AUTHORIZATION, currentDevice.bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"old-password","newPassword":"new-password"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data").doesNotExist());

        // 当前设备所属令牌族保留：Cookie 仍能轮换出新令牌
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie("agent_refresh", currentDevice.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk());

        // 其他设备整族撤销：刷新即失效，必须重新登录
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie("agent_refresh", otherDevice.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());

        // 新口令生效，旧口令不能再登录
        mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(account.username(), "new-password")))
                .andExpect(status().isOk());
        mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(account.username(), CURRENT_PASSWORD)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void changePassword_shouldRejectWrongCurrentPasswordWithoutLoggingOut() throws Exception {
        UserAccount account = createUser();
        LoginResult device = login(account.username(), CURRENT_PASSWORD);

        mockMvc.perform(put(PASSWORD_PATH)
                        .header(HttpHeaders.AUTHORIZATION, device.bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"wrong-password","newPassword":"new-password"}
                                """))
                // 400 而不是 401：前端不会把它当成登录失效而跳转登录页
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40102));

        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie("agent_refresh", device.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk());
    }

    @Test
    void changePassword_shouldRejectSamePassword() throws Exception {
        UserAccount account = createUser();
        LoginResult device = login(account.username(), CURRENT_PASSWORD);

        mockMvc.perform(put(PASSWORD_PATH)
                        .header(HttpHeaders.AUTHORIZATION, device.bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"old-password","newPassword":"old-password"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40103));
    }

    @Test
    void changePassword_shouldRejectTooShortNewPassword() throws Exception {
        UserAccount account = createUser();
        LoginResult device = login(account.username(), CURRENT_PASSWORD);

        mockMvc.perform(put(PASSWORD_PATH)
                        .header(HttpHeaders.AUTHORIZATION, device.bearerToken())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"old-password","newPassword":"short"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void changePassword_shouldReturnUnauthorized_whenAccessTokenIsMissing() throws Exception {
        mockMvc.perform(put(PASSWORD_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"currentPassword":"old-password","newPassword":"new-password"}
                                """))
                .andExpect(status().isUnauthorized());
    }

    private UserAccount createUser() {
        String username = "password-user-" + UUID.randomUUID();
        return userDirectory.create(username, passwordEncoder.encode(CURRENT_PASSWORD), List.of("USER"));
    }

    private LoginResult login(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(username, password)))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return new LoginResult("Bearer " + accessToken, extractRefreshToken(result));
    }

    private static String loginBody(String username, String password) {
        return "{\"username\":\"" + username + "\",\"password\":\"" + password + "\"}";
    }

    /** 从 Set-Cookie 头里取出 Cookie 值；MockMvc 不会自动把 ResponseCookie 解析为 Cookie 对象。 */
    private static String extractRefreshToken(MvcResult result) {
        String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);
        if (setCookie == null) {
            throw new IllegalStateException("登录响应缺少刷新 Cookie");
        }
        int nameEnd = setCookie.indexOf('=');
        int valueEnd = setCookie.indexOf(';');
        return setCookie.substring(nameEnd + 1, valueEnd);
    }

    /**
     * 一次登录的凭证：访问令牌用于请求头，刷新令牌用于模拟浏览器 Cookie。
     */
    private record LoginResult(String bearerToken, String refreshToken) {
    }
}
