package com.example.agent.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
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
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 登录设备接口集成测试：走完整过滤器链，用户源与会话仓储均为内存实现。
 *
 * <p>每个用例新建独立用户，保证设备列表只包含本用例自己登录出来的会话。
 * 当前设备通过解析访问令牌的 {@code sid} claim 独立核对，避免「服务端自证」。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({InMemoryUserDirectoryConfig.class, InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class})
class UserSessionApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String REFRESH_PATH = "/api/v1/auth/refresh";
    private static final String LOGOUT_ALL_PATH = "/api/v1/auth/logout-all";
    private static final String SESSIONS_PATH = "/api/v1/users/me/sessions";
    private static final String COOKIE_NAME = "agent_refresh";
    private static final String ALLOWED_ORIGIN = "http://localhost:5173";
    private static final String PASSWORD = "session-password";

    private final MockMvc mockMvc;

    private final UserDirectory userDirectory;

    private final PasswordEncoder passwordEncoder;

    private final JwtDecoder jwtDecoder;

    @Autowired
    UserSessionApiTests(MockMvc mockMvc,
            UserDirectory userDirectory,
            PasswordEncoder passwordEncoder,
            JwtDecoder jwtDecoder) {
        this.mockMvc = mockMvc;
        this.userDirectory = userDirectory;
        this.passwordEncoder = passwordEncoder;
        this.jwtDecoder = jwtDecoder;
    }

    @Test
    void listSessions_shouldMarkExactlyTheDeviceMatchingAccessToken() throws Exception {
        UserAccount account = createUser();
        LoginResult currentDevice = login(account.username());
        login(account.username());

        MvcResult result = mockMvc.perform(get(SESSIONS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, currentDevice.bearerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.total").value(2))
                .andExpect(jsonPath("$.data.page").value(1))
                .andExpect(jsonPath("$.data.size").value(20))
                .andReturn();

        List<Map<String, Object>> sessions =
                JsonPath.read(result.getResponse().getContentAsString(), "$.data.list");
        assertThat(sessions).hasSize(2);
        List<String> currentFamilies = sessions.stream()
                .filter(session -> Boolean.TRUE.equals(session.get("current")))
                .map(session -> (String) session.get("familyId"))
                .toList();
        // 恰好一台被标记为当前设备，且与令牌 sid 一致
        assertThat(currentFamilies).containsExactly(familyIdOf(currentDevice.bearerToken()));
    }

    @Test
    void listSessions_shouldRejectTooLargePageSize() throws Exception {
        LoginResult device = login(createUser().username());

        mockMvc.perform(get(SESSIONS_PATH)
                        .param("size", "101")
                        .header(HttpHeaders.AUTHORIZATION, device.bearerToken()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void listSessions_shouldReturnUnauthorized_whenAccessTokenIsMissing() throws Exception {
        mockMvc.perform(get(SESSIONS_PATH)).andExpect(status().isUnauthorized());
    }

    @Test
    void deleteSession_shouldRejectCurrentDevice() throws Exception {
        LoginResult device = login(createUser().username());
        String currentFamilyId = familyIdOf(device.bearerToken());

        mockMvc.perform(delete(SESSIONS_PATH + "/" + currentFamilyId)
                        .header(HttpHeaders.AUTHORIZATION, device.bearerToken()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value(30002));
    }

    @Test
    void deleteSession_shouldReturnNotFound_whenFamilyBelongsToAnotherUser() throws Exception {
        LoginResult userADevice = login(createUser().username());
        LoginResult userBDevice = login(createUser().username());
        String familyOfUserB = familyIdOf(userBDevice.bearerToken());

        mockMvc.perform(delete(SESSIONS_PATH + "/" + familyOfUserB)
                        .header(HttpHeaders.AUTHORIZATION, userADevice.bearerToken()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value(40105));
    }

    @Test
    void deleteSession_shouldRevokeOtherDeviceButKeepCurrentOne() throws Exception {
        UserAccount account = createUser();
        LoginResult currentDevice = login(account.username());
        LoginResult otherDevice = login(account.username());
        String otherFamilyId = familyIdOf(otherDevice.bearerToken());

        mockMvc.perform(delete(SESSIONS_PATH + "/" + otherFamilyId)
                        .header(HttpHeaders.AUTHORIZATION, currentDevice.bearerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data").doesNotExist());

        // 被踢设备的下一次刷新失效
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie(COOKIE_NAME, otherDevice.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());
        // 当前设备会话保留，照常轮换
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie(COOKIE_NAME, currentDevice.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isOk());
    }

    @Test
    void deleteSession_shouldRejectMalformedFamilyId() throws Exception {
        LoginResult device = login(createUser().username());

        mockMvc.perform(delete(SESSIONS_PATH + "/not-a-uuid")
                        .header(HttpHeaders.AUTHORIZATION, device.bearerToken()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void logoutAll_shouldRevokeEveryDeviceAndClearCookie() throws Exception {
        UserAccount account = createUser();
        LoginResult firstDevice = login(account.username());
        LoginResult secondDevice = login(account.username());

        MvcResult result = mockMvc.perform(post(LOGOUT_ALL_PATH)
                        .header(HttpHeaders.AUTHORIZATION, firstDevice.bearerToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data").doesNotExist())
                .andExpect(header().string(HttpHeaders.SET_COOKIE, containsString(COOKIE_NAME)))
                .andReturn();
        // 响应必须下发清除指令，否则浏览器会保留已失效的刷新令牌
        assertThat(result.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");

        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie(COOKIE_NAME, firstDevice.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(post(REFRESH_PATH)
                        .cookie(new Cookie(COOKIE_NAME, secondDevice.refreshToken()))
                        .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void logoutAll_shouldReturnUnauthorized_whenAccessTokenIsMissing() throws Exception {
        mockMvc.perform(post(LOGOUT_ALL_PATH)).andExpect(status().isUnauthorized());
    }

    private UserAccount createUser() {
        String username = "session-user-" + UUID.randomUUID();
        return userDirectory.create(username, passwordEncoder.encode(PASSWORD), List.of("USER"));
    }

    private LoginResult login(String username) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"" + username + "\",\"password\":\"" + PASSWORD + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return new LoginResult("Bearer " + accessToken, extractRefreshToken(result));
    }

    /** 直接从令牌取值核对当前设备，避免只依赖服务端返回的 current 字段。 */
    private String familyIdOf(String bearerToken) {
        return jwtDecoder.decode(bearerToken.substring("Bearer ".length())).getClaimAsString("sid");
    }

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
