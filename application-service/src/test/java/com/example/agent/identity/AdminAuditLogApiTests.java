package com.example.agent.identity;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.agent.identity.application.UserDirectory;
import com.example.agent.identity.domain.UserAccount;
import com.example.agent.support.InMemoryAuthAuditLogConfig;
import com.example.agent.support.InMemoryAuthAuditQuery;
import com.example.agent.support.InMemoryAuthAuditQueryConfig;
import com.example.agent.support.InMemoryRefreshSessionStoreConfig;
import com.example.agent.support.InMemoryUserDirectoryConfig;
import com.jayway.jsonpath.JsonPath;
import java.time.Instant;
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
 * 管理端审计查询接口集成测试。
 *
 * <p>查询侧使用 {@link InMemoryAuthAuditQuery} 预置数据，登录本身仍写入
 * {@code InMemoryAuthAuditLog}，两者在生产中对应同一张表的不同端口。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({
        InMemoryUserDirectoryConfig.class,
        InMemoryRefreshSessionStoreConfig.class,
        InMemoryAuthAuditLogConfig.class,
        InMemoryAuthAuditQueryConfig.class
})
class AdminAuditLogApiTests {

    private static final String LOGIN_PATH = "/api/v1/auth/login";
    private static final String AUDIT_LOGS_PATH = "/api/v1/admin/audit-logs";
    private static final String ADMIN_USERNAME = "admin";
    private static final String ADMIN_PASSWORD = "test-only-password";

    private final MockMvc mockMvc;
    private final UserDirectory userDirectory;
    private final PasswordEncoder passwordEncoder;
    private final InMemoryAuthAuditQuery auditQuery;

    @Autowired
    AdminAuditLogApiTests(
            MockMvc mockMvc,
            UserDirectory userDirectory,
            PasswordEncoder passwordEncoder,
            InMemoryAuthAuditQuery auditQuery) {
        this.mockMvc = mockMvc;
        this.userDirectory = userDirectory;
        this.passwordEncoder = passwordEncoder;
        this.auditQuery = auditQuery;
    }

    @BeforeEach
    void clearAuditQuery() {
        auditQuery.clear();
    }

    @Test
    void listAuditLogs_shouldReturnEmptyPage_whenNoRecordExists() throws Exception {
        mockMvc.perform(get(AUDIT_LOGS_PATH).header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.total").value(0))
                .andExpect(jsonPath("$.data.list").isEmpty());
    }

    @Test
    void listAuditLogs_shouldReturnNewestFirstWithPagination() throws Exception {
        auditQuery.add("login_success", "alice", "10.0.0.1", Instant.parse("2026-10-30T08:00:00Z"));
        auditQuery.add("login_failure", "bob", "10.0.0.2", Instant.parse("2026-10-30T09:00:00Z"));
        auditQuery.add("logout", "alice", "10.0.0.3", Instant.parse("2026-10-30T10:00:00Z"));

        mockMvc.perform(get(AUDIT_LOGS_PATH)
                        .param("page", "1")
                        .param("size", "2")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(3))
                .andExpect(jsonPath("$.data.list[0].event").value("logout"))
                .andExpect(jsonPath("$.data.list[1].event").value("login_failure"));
    }

    @Test
    void listAuditLogs_shouldFilterByEventAndUsername() throws Exception {
        auditQuery.add("login_success", "alice", "10.0.0.1", Instant.parse("2026-10-30T08:00:00Z"));
        auditQuery.add("login_failure", "alice", "10.0.0.2", Instant.parse("2026-10-30T09:00:00Z"));
        auditQuery.add("login_failure", "bob", "10.0.0.3", Instant.parse("2026-10-30T10:00:00Z"));

        mockMvc.perform(get(AUDIT_LOGS_PATH)
                        .param("event", "login_failure")
                        .param("username", "alice")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").value(1))
                .andExpect(jsonPath("$.data.list[0].username").value("alice"))
                .andExpect(jsonPath("$.data.list[0].ip").value("10.0.0.2"));
    }

    @Test
    void listAuditLogs_shouldRejectUnknownEvent() throws Exception {
        mockMvc.perform(get(AUDIT_LOGS_PATH)
                        .param("event", "unknown_event")
                        .header(HttpHeaders.AUTHORIZATION, adminToken()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(10001));
    }

    @Test
    void listAuditLogs_shouldForbidNonAdmin() throws Exception {
        UserAccount account = userDirectory.create(
                "audit-permission-user", passwordEncoder.encode("user-password"), List.of("USER"));

        mockMvc.perform(get(AUDIT_LOGS_PATH)
                        .header(HttpHeaders.AUTHORIZATION, tokenFor(account.username(), "user-password")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value(20002));
    }

    private String adminToken() throws Exception {
        return tokenFor(ADMIN_USERNAME, ADMIN_PASSWORD);
    }

    private String tokenFor(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(post(LOGIN_PATH)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"%s","password":"%s"}
                                """.formatted(username, password)))
                .andExpect(status().isOk())
                .andReturn();
        String accessToken = JsonPath.read(result.getResponse().getContentAsString(), "$.data.accessToken");
        return "Bearer " + accessToken;
    }
}
